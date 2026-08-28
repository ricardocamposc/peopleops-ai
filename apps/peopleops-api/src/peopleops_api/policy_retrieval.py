"""PeopleOps-owned policy retrieval with auditable, verified evidence.

LlamaIndex owns the query/embedding representation. PostgreSQL/pgvector owns
the durable vector search because PolicyChunk is the PeopleOps persistence
contract established by Slice 07.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from llama_index.core.schema import QueryBundle, TextNode
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from peopleops_api.models import PolicyChunk, PolicyVersion


class PolicyRetrievalStatus(StrEnum):
    COMPLETED = "COMPLETED"
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    POLICY_CONFLICT = "POLICY_CONFLICT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class QueryEmbeddingModel(Protocol):
    def get_query_embedding(self, query: str) -> list[float]: ...


class PolicyRetrievalFilters:
    """Provider-neutral business filters; physical schema stays in this adapter."""

    def __init__(
        self,
        *,
        document_key: str | None = None,
        document_type: str | None = None,
        department: str | None = None,
        confidentiality: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.document_key = document_key
        self.document_type = document_type
        self.department = department
        self.confidentiality = confidentiality
        self.metadata = metadata or {}


class PolicyEvidence:
    def __init__(
        self,
        *,
        document_id: UUID,
        document_key: str,
        title: str,
        policy_version_id: UUID,
        version: str,
        effective_from: date,
        effective_to: date | None,
        page: int | None,
        section: str | None,
        chunk_id: UUID,
        chunk_index: int,
        fragment: str,
        score: float,
        document_type: str = "policy",
        department: str | None = None,
        confidentiality: str = "internal",
        synthetic: bool = False,
    ) -> None:
        self.document_id = document_id
        self.document_key = document_key
        self.title = title
        self.document_type = document_type
        self.department = department
        self.confidentiality = confidentiality
        self.policy_version_id = policy_version_id
        self.version = version
        self.effective_from = effective_from
        self.effective_to = effective_to
        self.page = page
        self.section = section
        self.chunk_id = chunk_id
        self.chunk_index = chunk_index
        self.fragment = fragment
        self.score = score
        self.verified = True
        self.synthetic = synthetic

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "document_key": self.document_key,
            "title": self.title,
            "document_type": self.document_type,
            "department": self.department,
            "confidentiality": self.confidentiality,
            "policy_version_id": str(self.policy_version_id),
            "version": self.version,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "page": self.page,
            "section": self.section,
            "chunk_id": str(self.chunk_id),
            "chunk_index": self.chunk_index,
            "fragment": self.fragment,
            "score": self.score,
            "verified": self.verified,
            "synthetic": self.synthetic,
        }


class PolicyRetrievalResult:
    def __init__(
        self,
        *,
        status: PolicyRetrievalStatus,
        evidence: list[PolicyEvidence] | None = None,
        reason: str | None = None,
    ) -> None:
        self.status = status
        self.evidence = evidence or []
        self.reason = reason

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "evidence": [item.as_dict() for item in self.evidence],
        }


class PolicyKnowledgeProvider:
    """Retrieve only current, metadata-matching and verifiable policy chunks."""

    def __init__(
        self,
        session: Session,
        embedding_model: QueryEmbeddingModel,
        *,
        minimum_score: float = 0.30,
    ) -> None:
        self.session = session
        self.embedding_model = embedding_model
        self.minimum_score = minimum_score

    def retrieve(
        self,
        query: str,
        *,
        as_of: date,
        filters: PolicyRetrievalFilters | None = None,
        top_k: int = 5,
    ) -> PolicyRetrievalResult:
        if not query.strip() or top_k < 1:
            return PolicyRetrievalResult(
                status=PolicyRetrievalStatus.INSUFFICIENT_DATA,
                reason="a non-empty query and positive top_k are required",
            )

        top_k = min(top_k, 20)
        selected_versions, conflict = self._select_versions(as_of, filters)
        if conflict:
            return PolicyRetrievalResult(
                status=PolicyRetrievalStatus.POLICY_CONFLICT,
                reason="multiple applicable policy versions have the same effective date",
            )
        if not selected_versions:
            future_match = self._has_future_match(as_of, filters)
            return PolicyRetrievalResult(
                status=PolicyRetrievalStatus.POLICY_NOT_FOUND,
                reason=(
                    "a matching policy exists but is not effective on the requested date"
                    if future_match
                    else "no active policy version is applicable to the requested date"
                ),
            )

        query_bundle = QueryBundle(query_str=query)
        query_embedding = self.embedding_model.get_query_embedding(query_bundle.query_str)
        distance = PolicyChunk.embedding.cosine_distance(query_embedding)
        statement = (
            select(PolicyChunk, distance.label("distance"))
            .options(joinedload(PolicyChunk.policy_version).joinedload(PolicyVersion.document))
            .where(PolicyChunk.policy_version_id.in_(selected_versions))
            .order_by(distance)
            .limit(top_k)
        )
        rows = self.session.execute(statement).unique().all()
        evidence: list[PolicyEvidence] = []
        for chunk, raw_distance in rows:
            score = max(0.0, min(1.0, 1.0 - float(raw_distance)))
            if score < self.minimum_score:
                continue
            verified = self._verify_chunk(chunk, selected_versions, as_of, score)
            if verified:
                evidence.append(verified)

        if not evidence:
            return PolicyRetrievalResult(
                status=PolicyRetrievalStatus.INSUFFICIENT_DATA,
                reason="retrieved chunks did not meet the evidence verification threshold",
            )
        return PolicyRetrievalResult(status=PolicyRetrievalStatus.COMPLETED, evidence=evidence)

    def _has_future_match(self, as_of: date, filters: PolicyRetrievalFilters | None) -> bool:
        statement = self._base_versions(filters).where(
            PolicyVersion.status == "active",
            PolicyVersion.effective_from > as_of,
        )
        return self.session.execute(statement.limit(1)).first() is not None

    def _base_versions(self, filters: PolicyRetrievalFilters | None) -> Select[Any]:
        statement = select(PolicyVersion).options(joinedload(PolicyVersion.document))
        if filters:
            if filters.document_key:
                statement = statement.where(
                    PolicyVersion.document.has(document_key=filters.document_key)
                )
            if filters.document_type:
                statement = statement.where(
                    PolicyVersion.document.has(document_type=filters.document_type)
                )
            if filters.department:
                statement = statement.where(
                    PolicyVersion.document.has(department=filters.department)
                )
            if filters.confidentiality:
                statement = statement.where(
                    PolicyVersion.document.has(confidentiality=filters.confidentiality)
                )
            if filters.metadata:
                statement = statement.where(PolicyVersion.metadata_.contains(filters.metadata))
        return statement

    def _select_versions(
        self, as_of: date, filters: PolicyRetrievalFilters | None
    ) -> tuple[list[UUID], bool]:
        statement = self._base_versions(filters).where(
            PolicyVersion.status == "active",
            PolicyVersion.effective_from <= as_of,
            (PolicyVersion.effective_to.is_(None) | (PolicyVersion.effective_to >= as_of)),
        )
        versions = self.session.scalars(statement).unique().all()
        by_document: dict[UUID, list[PolicyVersion]] = defaultdict(list)
        for version in versions:
            by_document[version.policy_document_id].append(version)
        selected: list[UUID] = []
        for candidates in by_document.values():
            candidates.sort(key=lambda item: (item.effective_from, item.version), reverse=True)
            if len(candidates) > 1 and candidates[0].effective_from == candidates[1].effective_from:
                return [], True
            selected.append(candidates[0].id)
        return selected, False

    @staticmethod
    def _verify_chunk(
        chunk: PolicyChunk, selected_versions: list[UUID], as_of: date, score: float
    ) -> PolicyEvidence | None:
        version = chunk.policy_version
        document = version.document
        if (
            not chunk.text.strip()
            or chunk.policy_version_id not in selected_versions
            or version.status != "active"
            or version.effective_from > as_of
            or (version.effective_to is not None and version.effective_to < as_of)
            or document is None
        ):
            return None
        # Constructing a TextNode ensures the cited fragment is the indexed content,
        # rather than free-form text supplied by a caller or a model.
        node = TextNode(text=chunk.text)
        return PolicyEvidence(
            document_id=document.id,
            document_key=document.document_key,
            title=document.title,
            document_type=document.document_type,
            department=document.department,
            confidentiality=document.confidentiality,
            policy_version_id=version.id,
            version=version.version,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            page=chunk.page,
            section=chunk.section,
            chunk_id=chunk.id,
            chunk_index=chunk.chunk_index,
            fragment=node.get_content(),
            score=score,
            synthetic=version.metadata_.get("synthetic") is True,
        )
