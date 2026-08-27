"""Small deterministic Policy RAG evaluation harness.

Evaluation cases are versioned files and are deliberately independent from
AnalysisInteraction and from ingestion. A run fails loudly if its corpus is
not already available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

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
    expected_document_key: str | None = None
    expected_version: str | None = None
    filters: PolicyRetrievalFilters | None = None


def load_cases(path: str | Path) -> list[PolicyEvaluationCase]:
    cases: list[PolicyEvaluationCase] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        raw = json.loads(line)
        filters = raw.get("filters")
        cases.append(
            PolicyEvaluationCase(
                case_id=raw["case_id"],
                query=raw["query"],
                as_of=date.fromisoformat(raw["as_of"]),
                expected_status=PolicyRetrievalStatus(raw["expected_status"]),
                expected_document_key=raw.get("expected_document_key"),
                expected_version=raw.get("expected_version"),
                filters=PolicyRetrievalFilters(**filters) if filters else None,
            )
        )
    return cases


def evaluate_cases(
    provider: PolicyKnowledgeProvider, cases: list[PolicyEvaluationCase]
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    document_hits = 0
    version_hits = 0
    citation_validity = 0
    answerability_hits = 0
    abstention_hits = 0
    for case in cases:
        result = provider.retrieve(case.query, as_of=case.as_of, filters=case.filters)
        status_match = result.status == case.expected_status
        answerability_hits += int(status_match)
        is_abstention = result.status in {
            PolicyRetrievalStatus.POLICY_NOT_FOUND,
            PolicyRetrievalStatus.POLICY_CONFLICT,
            PolicyRetrievalStatus.INSUFFICIENT_DATA,
        }
        abstention_hits += int(
            is_abstention == (case.expected_status != PolicyRetrievalStatus.COMPLETED)
        )
        document_match = bool(
            case.expected_document_key
            and any(item.document_key == case.expected_document_key for item in result.evidence)
        )
        version_match = bool(
            case.expected_version
            and any(item.version == case.expected_version for item in result.evidence)
        )
        citation_match = result.status != PolicyRetrievalStatus.COMPLETED or all(
            item.verified and item.fragment.strip() and item.chunk_id and item.policy_version_id
            for item in result.evidence
        )
        document_hits += int(document_match)
        version_hits += int(version_match)
        citation_validity += int(citation_match)
        results.append(
            {
                "case_id": case.case_id,
                "status": result.status.value,
                "expected_status": case.expected_status.value,
                "status_match": status_match,
                "document_match": document_match,
                "version_match": version_match,
                "citation_valid": citation_match,
                "evidence": [item.as_dict() for item in result.evidence],
            }
        )
    total = len(cases)

    def denominator(value: int) -> float:
        return value / total if total else 0.0

    return {
        "dataset": "policy_rag_v1",
        "metrics": {
            "document_hit_recall": denominator(document_hits),
            "policy_version_accuracy": denominator(version_hits),
            "citation_validity": denominator(citation_validity),
            "answerability_accuracy": denominator(answerability_hits),
            "abstention_accuracy": denominator(abstention_hits),
        },
        "case_count": total,
        "cases": results,
    }


def write_artifact(result: dict[str, Any], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_from_files(
    provider: PolicyKnowledgeProvider,
    dataset_path: str | Path,
    artifact_path: str | Path,
) -> dict[str, Any]:
    result = evaluate_cases(provider, load_cases(dataset_path))
    write_artifact(result, artifact_path)
    return result
