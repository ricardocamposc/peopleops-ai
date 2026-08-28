"""Deterministic Policy RAG evaluation with separate expected and observed data."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from peopleops_api.policy_retrieval import (
    PolicyKnowledgeProvider,
    PolicyRetrievalFilters,
    PolicyRetrievalStatus,
)


@dataclass(frozen=True)
class PolicyEvaluationCase:
    case_id: str
    query: str
    as_of: date
    expected_status: PolicyRetrievalStatus
    expected_workflow_status: str | None = None
    language: str = "en"
    expected_document_key: str | None = None
    expected_version: str | None = None
    expected_document_keys: tuple[str, ...] = field(default_factory=tuple)
    expected_versions: tuple[str, ...] = field(default_factory=tuple)
    expected_pages: tuple[int, ...] = field(default_factory=tuple)
    expected_sections: tuple[str, ...] = field(default_factory=tuple)
    expected_answerable: bool | None = None
    expected_policy_facts: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    filters: PolicyRetrievalFilters | None = None
    pdd_section: str | None = None
    capability: str | None = None
    expected_sources: tuple[str, ...] = field(default_factory=tuple)
    expected_behavior: str | None = None

    def __post_init__(self) -> None:
        if self.expected_document_key and not self.expected_document_keys:
            object.__setattr__(self, "expected_document_keys", (self.expected_document_key,))
        if self.expected_version and not self.expected_versions:
            object.__setattr__(self, "expected_versions", (self.expected_version,))


def load_cases(path: str | Path) -> list[PolicyEvaluationCase]:
    cases: list[PolicyEvaluationCase] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        raw = json.loads(line)
        filters = raw.get("metadata_filters", raw.get("filters"))
        cases.append(
            PolicyEvaluationCase(
                case_id=raw["case_id"],
                query=raw.get("question", raw.get("query")),
                language=raw.get("language", "en"),
                as_of=date.fromisoformat(raw["as_of_date"] if "as_of_date" in raw else raw["as_of"]),
                expected_status=PolicyRetrievalStatus(raw["expected_status"]),
                expected_workflow_status=raw.get("expected_workflow_status"),
                expected_document_key=raw.get("expected_document_key"),
                expected_version=raw.get("expected_version"),
                expected_document_keys=tuple(raw.get("expected_document_ids", raw.get("expected_document_keys", []))),
                expected_versions=tuple(raw.get("expected_policy_versions", raw.get("expected_versions", []))),
                expected_pages=tuple(raw.get("expected_pages", [])),
                expected_sections=tuple(raw.get("expected_sections", [])),
                expected_answerable=raw.get(
                    "expected_answerable",
                    raw.get("expected_status") == PolicyRetrievalStatus.COMPLETED.value,
                ),
                expected_policy_facts=tuple(raw.get("expected_policy_facts", [])),
                tags=tuple(raw.get("tags", [])),
                filters=PolicyRetrievalFilters(**filters) if filters else None,
                pdd_section=raw.get("pdd_section"),
                capability=raw.get("capability"),
                expected_sources=tuple(raw.get("expected_sources", [])),
                expected_behavior=raw.get("expected_behavior"),
            )
        )
    return cases


def load_predictions(path: str | Path) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            predictions.append(json.loads(line))
    return predictions


def _observed_document_keys(prediction: dict[str, Any]) -> set[str]:
    items = prediction.get("retrieved_policy_documents")
    if items is None:
        items = prediction.get("policy_documents", prediction.get("policy_sources", []))
    if not items and prediction.get("retrieved_evidence"):
        items = prediction["retrieved_evidence"]
    return {
        str(item.get("document_key") or item.get("document_id"))
        for item in items
        if item.get("document_key") or item.get("document_id")
    }


def _observed_versions(prediction: dict[str, Any]) -> set[str]:
    items = prediction.get("retrieved_evidence") or prediction.get("policy_versions", [])
    return {str(item.get("version")) for item in items if item.get("version") is not None}


def _observed_evidence(prediction: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in prediction.get("evidence", []) if item.get("type", "policy") == "policy"]


def _tokens(value: Any) -> set[str]:
    """Language-neutral tokenization used only for diagnostic metrics."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return set(re.findall(r"[\w]+", normalized, flags=re.UNICODE))


def _evidence_text(evidence: list[dict[str, Any]]) -> str:
    return " ".join(
        str(item.get("text") or item.get("content") or item.get("fragment") or "")
        for item in evidence
    )


def _lexical_metrics(case: PolicyEvaluationCase, prediction: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[float, float]:
    evidence_tokens = _tokens(_evidence_text(evidence))
    query_tokens = _tokens(case.query)
    answer_tokens = _tokens(prediction.get("answer"))
    groundedness = (
        len(answer_tokens & evidence_tokens) / len(answer_tokens) if answer_tokens else 0.0
    )
    relevance = (
        len(query_tokens & evidence_tokens) / len(query_tokens) if query_tokens else 0.0
    )
    return groundedness, relevance


def _filter_precision(case: PolicyEvaluationCase, prediction: dict[str, Any]) -> float | None:
    if case.filters is None:
        return None
    items = prediction.get("policy_documents") or _observed_evidence(prediction)
    if not items:
        return 0.0
    checks: list[bool] = []
    for item in items:
        valid = True
        for key in ("document_key", "document_type", "department", "confidentiality"):
            expected = getattr(case.filters, key, None)
            if expected is not None and item.get(key) != expected:
                valid = False
        checks.append(valid)
    return sum(checks) / len(checks)


def _document_precision(expected: set[str], observed: set[str]) -> float | None:
    """Measure retrieval precision, including unwanted documents as errors."""
    if not expected and not observed:
        return 1.0
    if not observed:
        return 0.0 if expected else 1.0
    return len(expected & observed) / len(observed)


def _promoted_document_precision(expected: set[str], promoted: set[str]) -> float | None:
    """Measure precision of documents actually exposed as answer evidence."""
    if not promoted:
        return None
    return len(expected & promoted) / len(promoted)


def evaluate_predictions(
    dataset: Iterable[PolicyEvaluationCase], predictions: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    cases = list(dataset)
    predictions = list(predictions)
    by_id = {item.get("case_id"): item for item in predictions}
    results: list[dict[str, Any]] = []
    counters: dict[str, list[float]] = {}

    def add(metric: str, value: float, applicable: bool = True) -> None:
        if applicable:
            counters.setdefault(metric, []).append(value)

    for case in cases:
        prediction = by_id.get(case.case_id)
        if prediction is None:
            results.append({"case_id": case.case_id, "error": "prediction missing", "failed_layer": "runner"})
            continue
        observed_status = prediction.get("status")
        verification = prediction.get("evidence_verification") or {}
        observed_answerable = prediction.get("answerable")
        if observed_answerable is None:
            observed_answerable = verification.get("answerable")
        if observed_answerable is None:
            observed_answerable = observed_status in {
                PolicyRetrievalStatus.COMPLETED.value,
                "PENDING_HUMAN_REVIEW",
            }
        expected_docs = set(case.expected_document_keys)
        observed_docs = _observed_document_keys(prediction)
        expected_versions = set(case.expected_versions)
        observed_versions = _observed_versions(prediction)
        evidence = _observed_evidence(prediction)
        promoted_docs = {
            str(item.get("document_key") or item.get("document_id"))
            for item in evidence
            if item.get("document_key") or item.get("document_id")
        }
        lexical_groundedness, lexical_relevance = _lexical_metrics(case, prediction, evidence)
        expected_answerable = case.expected_answerable
        if expected_answerable is None:
            expected_answerable = case.expected_status is PolicyRetrievalStatus.COMPLETED

        doc_recall = (
            len(expected_docs & observed_docs) / len(expected_docs) if expected_docs else None
        )
        doc_precision = _document_precision(expected_docs, observed_docs)
        promoted_doc_precision = _promoted_document_precision(expected_docs, promoted_docs)
        retrieval_noise_rate = 1.0 - doc_precision if doc_precision is not None else None
        version_accuracy = (
            len(expected_versions & observed_versions) / len(expected_versions)
            if expected_versions
            else None
        )
        page_or_section_recall = None
        if case.expected_pages:
            pages = {item.get("page") for item in evidence}
            page_or_section_recall = len(set(case.expected_pages) & pages) / len(set(case.expected_pages))
        elif case.expected_sections:
            sections = {item.get("section") for item in evidence}
            page_or_section_recall = len(set(case.expected_sections) & sections) / len(set(case.expected_sections))

        filter_precision = prediction.get("filter_precision")
        if filter_precision is None:
            filter_precision = _filter_precision(case, prediction)
        citation_valid = bool(prediction.get("citations_valid", prediction.get("citation_valid", False)))
        verification_answerable = verification.get("answerable")
        expected_observed_status = case.expected_workflow_status or case.expected_status.value
        status_match = observed_status == expected_observed_status
        answerability_match = bool(observed_answerable) == bool(expected_answerable)
        abstention_match = (not bool(observed_answerable)) == (not bool(expected_answerable))
        case_result = {
            "case_id": case.case_id,
            "pdd_section": case.pdd_section,
            "capability": case.capability or "policy_rag",
            "expected_sources": list(case.expected_sources),
            "expected_behavior": case.expected_behavior,
            "status": observed_status,
            "expected_status": case.expected_status.value,
            "expected_workflow_status": case.expected_workflow_status,
            "answerable": bool(observed_answerable),
            "expected_answerable": bool(expected_answerable),
            "status_match": status_match,
            "answerability_match": answerability_match,
            "abstention_match": abstention_match,
            "document_recall": doc_recall,
            "document_precision": doc_precision,
            "promoted_document_precision": promoted_doc_precision,
            "retrieval_noise_rate": retrieval_noise_rate,
            "policy_version_accuracy": version_accuracy,
            "page_or_section_recall": page_or_section_recall,
            "filter_precision": filter_precision,
            "citation_validity": citation_valid,
            "lexical_groundedness": lexical_groundedness,
            "lexical_relevance": lexical_relevance,
            "evidence_verification_accuracy": (
                bool(verification_answerable) == bool(expected_answerable)
                if verification_answerable is not None
                else None
            ),
            "failed_layer": _failed_layer(case, prediction, status_match, answerability_match),
        }
        add("document_hit_rate", float(bool(expected_docs & observed_docs)), bool(expected_docs))
        add("document_recall", doc_recall or 0.0, doc_recall is not None)
        add("document_precision", doc_precision or 0.0, doc_precision is not None)
        add(
            "promoted_document_precision",
            promoted_doc_precision or 0.0,
            promoted_doc_precision is not None,
        )
        add("retrieval_noise_rate", retrieval_noise_rate or 0.0, retrieval_noise_rate is not None)
        add("policy_version_accuracy", version_accuracy or 0.0, version_accuracy is not None)
        add("page_or_section_recall", page_or_section_recall or 0.0, page_or_section_recall is not None)
        if filter_precision is not None:
            add("filter_precision", float(filter_precision))
        add("answerability_accuracy", float(answerability_match))
        add("abstention_accuracy", float(abstention_match))
        add("citation_validity", float(citation_valid))
        add("lexical_groundedness", lexical_groundedness)
        add("lexical_relevance", lexical_relevance)
        add("evidence_verification_accuracy", case_result["evidence_verification_accuracy"] or 0.0, case_result["evidence_verification_accuracy"] is not None)
        results.append(case_result)

    metric_names = (
        "document_hit_rate",
        "document_recall",
        "document_precision",
        "promoted_document_precision",
        "retrieval_noise_rate",
        "policy_version_accuracy",
        "page_or_section_recall",
        "filter_precision",
        "answerability_accuracy",
        "abstention_accuracy",
        "citation_validity",
        "lexical_groundedness",
        "lexical_relevance",
        "evidence_verification_accuracy",
    )
    summary = {
        metric: sum(counters[metric]) / len(counters[metric]) if counters.get(metric) else None
        for metric in metric_names
    }
    return {
        "dataset": "policy_rag_v1",
        "case_count": len(cases),
        "prediction_count": len(predictions),
        "metrics": summary,
        "cases": results,
        "failed_cases": [item for item in results if item.get("failed_layer")],
    }


def _failed_layer(
    case: PolicyEvaluationCase,
    prediction: dict[str, Any],
    status_match: bool,
    answerability_match: bool,
) -> str | None:
    if prediction.get("error"):
        return str(prediction.get("failed_layer") or "runner")
    if prediction.get("ingestion_status") not in (None, "completed", "ready"):
        return "ingestion"
    if not status_match and case.expected_status in {
        PolicyRetrievalStatus.POLICY_NOT_FOUND,
        PolicyRetrievalStatus.POLICY_CONFLICT,
    }:
        return "policy_version_selection"
    if case.filters is not None and prediction.get("filters_match") is False:
        return "metadata_filter"
    verification = prediction.get("evidence_verification") or {}
    if not answerability_match and verification:
        return "evidence_verification"
    if not answerability_match:
        return "final_synthesis"
    if prediction.get("citations_valid") is False:
        return "citation_validation"
    return None


def evaluate_cases(
    provider: PolicyKnowledgeProvider, cases: list[PolicyEvaluationCase]
) -> dict[str, Any]:
    """Compatibility helper for provider-level unit tests; not the baseline runner."""
    predictions: list[dict[str, Any]] = []
    for case in cases:
        result = provider.retrieve(case.query, as_of=case.as_of, filters=case.filters)
        evidence = [item.as_dict() for item in result.evidence]
        predictions.append(
            {
                "case_id": case.case_id,
                "status": result.status.value,
                "answerable": result.status is PolicyRetrievalStatus.COMPLETED,
                "policy_sources": [
                    {"document_key": item["document_key"], "document_id": item["document_id"]}
                    for item in evidence
                ],
                "policy_versions": [{"version": item["version"]} for item in evidence],
                "evidence": evidence,
                "citations_valid": all(item.get("verified") is True for item in evidence)
                if result.status is PolicyRetrievalStatus.COMPLETED
                else True,
                "evidence_verification": {
                    "answerable": result.status is PolicyRetrievalStatus.COMPLETED
                },
            }
        )
    return evaluate_predictions(cases, predictions)


def write_artifact(result: dict[str, Any], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def run_from_files(
    provider: PolicyKnowledgeProvider,
    dataset_path: str | Path,
    artifact_path: str | Path,
) -> dict[str, Any]:
    result = evaluate_cases(provider, load_cases(dataset_path))
    write_artifact(result, artifact_path)
    return result
