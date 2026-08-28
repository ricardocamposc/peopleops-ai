from datetime import date
from uuid import uuid4

from sqlalchemy import select

from peopleops_api.models import PolicyChunk, PolicyDocument, PolicyVersion
from peopleops_api.policy_evaluation import PolicyEvaluationCase, evaluate_cases
from peopleops_api.policy_retrieval import (
    PolicyKnowledgeProvider,
    PolicyRetrievalFilters,
    PolicyRetrievalStatus,
)


class DeterministicEmbedding:
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def get_query_embedding(self, query: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in query.lower().split():
            vector[sum(map(ord, token)) % self.dimension] += 1.0
        return vector


def vector_for(text: str) -> list[float]:
    return DeterministicEmbedding().get_query_embedding(text)


def add_policy(
    session,
    *,
    key: str,
    version: str,
    start: date,
    end: date | None,
    text: str,
    department: str | None = "People",
    metadata: dict | None = None,
) -> PolicyVersion:
    document = session.scalar(select(PolicyDocument).where(PolicyDocument.document_key == key))
    if document is None:
        document = PolicyDocument(
            document_key=key,
            title="Vacation policy",
            document_type="policy",
            department=department,
            confidentiality="internal",
            status="active",
        )
        session.add(document)
        session.flush()
    record = PolicyVersion(
        policy_document_id=document.id,
        version=version,
        effective_from=start,
        effective_to=end,
        status="active",
        original_filename=f"{key}-{version}.pdf",
        storage_uri=f"file://policies/{key}-{version}.pdf",
        checksum=uuid4().hex,
        metadata_=metadata or {},
    )
    session.add(record)
    session.flush()
    session.add(
        PolicyChunk(
            policy_version_id=record.id,
            text=text,
            page=2,
            section="Approvals",
            chunk_index=0,
            embedding=vector_for(text),
            metadata_={"untrusted_content": True},
        )
    )
    session.flush()
    return record


def test_retrieval_applies_metadata_and_returns_verified_provenance(db_session) -> None:
    add_policy(
        db_session,
        key="vacation-policy",
        version="2",
        start=date(2026, 1, 1),
        end=None,
        text="Vacation requests require manager approval.",
        metadata={"locale": "en-US"},
    )
    add_policy(
        db_session,
        key="remote-work-policy",
        version="1",
        start=date(2026, 1, 1),
        end=None,
        text="Remote work requires manager approval.",
        department="IT",
    )

    result = PolicyKnowledgeProvider(db_session, DeterministicEmbedding()).retrieve(
        "Vacation requests require manager approval",
        as_of=date(2026, 6, 1),
        filters=PolicyRetrievalFilters(document_type="policy", department="People"),
    )

    assert result.status == PolicyRetrievalStatus.COMPLETED
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.document_key == "vacation-policy"
    assert evidence.version == "2"
    assert evidence.page == 2
    assert evidence.section == "Approvals"
    assert evidence.fragment == "Vacation requests require manager approval."
    assert evidence.verified is True
    assert evidence.score >= 0.5


def test_retrieval_scenario_is_repeatable_after_rollback(db_session) -> None:
    for _ in range(2):
        add_policy(
            db_session,
            key="repeatable-policy",
            version="1",
            start=date(2026, 1, 1),
            end=None,
            text="Repeatable requests require manager approval.",
        )
        result = PolicyKnowledgeProvider(db_session, DeterministicEmbedding()).retrieve(
            "Repeatable requests require manager approval",
            as_of=date(2026, 6, 1),
        )
        assert result.status == PolicyRetrievalStatus.COMPLETED
        assert result.evidence[0].version == "1"
        db_session.rollback()


def test_retrieval_selects_historical_effective_version(db_session) -> None:
    add_policy(
        db_session,
        key="vacation-history",
        version="1",
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
        text="The first vacation rule requires supervisor approval.",
    )
    add_policy(
        db_session,
        key="vacation-history",
        version="2",
        start=date(2026, 1, 1),
        end=None,
        text="The second vacation rule requires manager approval.",
    )
    provider = PolicyKnowledgeProvider(db_session, DeterministicEmbedding())

    historical = provider.retrieve(
        "The first vacation rule requires supervisor approval",
        as_of=date(2025, 6, 1),
    )
    current = provider.retrieve(
        "The second vacation rule requires manager approval",
        as_of=date(2026, 6, 1),
    )

    assert historical.status == PolicyRetrievalStatus.COMPLETED
    assert historical.evidence[0].version == "1"
    assert current.status == PolicyRetrievalStatus.COMPLETED
    assert current.evidence[0].version == "2"


def test_retrieval_abstains_for_missing_or_weak_evidence(db_session) -> None:
    add_policy(
        db_session,
        key="attendance-policy",
        version="1",
        start=date(2026, 1, 1),
        end=None,
        text="Attendance incidents are reviewed monthly.",
    )
    provider = PolicyKnowledgeProvider(db_session, DeterministicEmbedding(), minimum_score=0.99)

    missing = provider.retrieve("Relocation allowance", as_of=date(2026, 6, 1))
    weak = provider.retrieve("Completely unrelated claim", as_of=date(2026, 6, 1))

    assert missing.status == PolicyRetrievalStatus.INSUFFICIENT_DATA
    assert weak.status == PolicyRetrievalStatus.INSUFFICIENT_DATA
    assert not missing.evidence
    assert not weak.evidence


def test_retrieval_rejects_an_invalid_persisted_fragment(db_session) -> None:
    version = add_policy(
        db_session,
        key="invalid-fragment-policy",
        version="1",
        start=date(2026, 1, 1),
        end=None,
        text="This fragment will be invalidated.",
    )
    chunk = version.chunks[0]
    chunk.text = "   "
    db_session.flush()

    result = PolicyKnowledgeProvider(db_session, DeterministicEmbedding()).retrieve(
        "This fragment will be invalidated", as_of=date(2026, 6, 1)
    )

    assert result.status == PolicyRetrievalStatus.INSUFFICIENT_DATA
    assert not result.evidence


def test_retrieval_distinguishes_policy_conflict_from_absence(db_session) -> None:
    add_policy(
        db_session,
        key="conflicting-policy",
        version="A",
        start=date(2026, 1, 1),
        end=None,
        text="Vacation approval is required.",
    )
    add_policy(
        db_session,
        key="conflicting-policy",
        version="B",
        start=date(2026, 1, 1),
        end=None,
        text="Vacation approval is not required.",
    )
    provider = PolicyKnowledgeProvider(db_session, DeterministicEmbedding())

    conflict = provider.retrieve("Vacation approval", as_of=date(2026, 6, 1))
    absent = provider.retrieve("Vacation approval", as_of=date(2024, 6, 1))

    assert conflict.status == PolicyRetrievalStatus.POLICY_CONFLICT
    assert absent.status == PolicyRetrievalStatus.POLICY_NOT_FOUND


def test_evaluation_is_deterministic_and_separate_from_analysis_interaction(db_session) -> None:
    add_policy(
        db_session,
        key="evaluated-policy",
        version="1",
        start=date(2026, 1, 1),
        end=None,
        text="Evaluated policy requires approval.",
    )
    cases = [
        PolicyEvaluationCase(
            case_id="hit",
            query="Evaluated policy requires approval",
            as_of=date(2026, 6, 1),
            expected_status=PolicyRetrievalStatus.COMPLETED,
            expected_document_key="evaluated-policy",
            expected_version="1",
        ),
        PolicyEvaluationCase(
            case_id="absent",
            query="Missing policy",
            as_of=date(2025, 6, 1),
            expected_status=PolicyRetrievalStatus.POLICY_NOT_FOUND,
        ),
    ]
    result = evaluate_cases(PolicyKnowledgeProvider(db_session, DeterministicEmbedding()), cases)

    assert result["dataset"] == "policy_rag_v1"
    assert result["case_count"] == 2
    assert result["metrics"]["citation_validity"] == 1.0
    assert "analysis_interaction" not in result
