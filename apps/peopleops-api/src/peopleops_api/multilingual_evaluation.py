"""Deterministic Slice 12 evaluation over the existing typed workflow contracts.

The evaluator deliberately consumes model-produced ``SemanticRequest``,
``AnalysisPlan`` and ``StructuredAnswer`` objects. It never interprets the
question text and therefore cannot become a language-specific router.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from peopleops_api.analysis_contracts import AnalysisPlan, SemanticRequest, StructuredAnswer


@dataclass(frozen=True)
class MultilingualEvaluationCase:
    case_id: str
    equivalence_group: str
    language: str
    question: str
    scenario: str
    expected_capabilities: tuple[str, ...]
    expected_entities: tuple[str, ...]
    requires_structured_data: bool
    requires_policy: bool
    expected_query_entity_sets: tuple[tuple[str, ...], ...]
    expected_status: str
    expected_fact_assertions: Mapping[str, Any]


@dataclass(frozen=True)
class MultilingualPrediction:
    semantic_request: SemanticRequest
    plan: AnalysisPlan
    response: StructuredAnswer


def load_cases(path: str | Path) -> list[MultilingualEvaluationCase]:
    cases: list[MultilingualEvaluationCase] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        raw = json.loads(line)
        expected = raw["expected"]
        cases.append(
            MultilingualEvaluationCase(
                case_id=raw["case_id"],
                equivalence_group=raw["equivalence_group"],
                language=raw["language"],
                question=raw["question"],
                scenario=raw["scenario"],
                expected_capabilities=tuple(expected["capabilities"]),
                expected_entities=tuple(expected["entities"]),
                requires_structured_data=expected["requires_structured_data"],
                requires_policy=expected["requires_policy"],
                expected_query_entity_sets=tuple(
                    tuple(query_entities) for query_entities in expected["query_entity_sets"]
                ),
                expected_status=expected["status"],
                expected_fact_assertions=expected.get("fact_assertions", {}),
            )
        )
    return cases


def evaluate_predictions(
    cases: Sequence[MultilingualEvaluationCase],
    predictions: Mapping[str, MultilingualPrediction],
) -> dict[str, Any]:
    """Return reproducible correctness and cross-language consistency metrics."""

    results: list[dict[str, Any]] = []
    semantic_hits = plan_hits = outcome_hits = 0
    signatures: dict[str, set[tuple[Any, ...]]] = {}
    for case in cases:
        prediction = predictions.get(case.case_id)
        if prediction is None:
            results.append({"case_id": case.case_id, "passed": False, "missing": True})
            continue
        semantic = prediction.semantic_request
        plan_entities = tuple(
            sorted(tuple(sorted(planned.query.entities)) for planned in prediction.plan.queries)
        )
        expected_plan_entities = tuple(
            sorted(tuple(sorted(entity_set)) for entity_set in case.expected_query_entity_sets)
        )
        semantic_match = (
            tuple(sorted(semantic.required_capabilities))
            == tuple(sorted(case.expected_capabilities))
            and tuple(sorted(semantic.entities)) == tuple(sorted(case.expected_entities))
            and semantic.requires_structured_data == case.requires_structured_data
            and semantic.requires_policy == case.requires_policy
        )
        plan_match = plan_entities == expected_plan_entities and (
            prediction.plan.policy is not None
        ) == (case.requires_policy)
        fact_match = all(
            _contains_assertion(prediction.response.facts, key, value)
            for key, value in case.expected_fact_assertions.items()
        )
        outcome_match = prediction.response.status == case.expected_status and fact_match
        semantic_hits += int(semantic_match)
        plan_hits += int(plan_match)
        outcome_hits += int(outcome_match)
        signature = (
            tuple(sorted(semantic.required_capabilities)),
            tuple(sorted(semantic.entities)),
            semantic.requires_structured_data,
            semantic.requires_policy,
            plan_entities,
            prediction.response.status,
        )
        signatures.setdefault(case.equivalence_group, set()).add(signature)
        results.append(
            {
                "case_id": case.case_id,
                "language": case.language,
                "semantic_match": semantic_match,
                "plan_match": plan_match,
                "outcome_match": outcome_match,
                "passed": semantic_match and plan_match and outcome_match,
            }
        )
    consistency_groups = sum(bool(values) and len(values) == 1 for values in signatures.values())
    total = len(cases)

    def denominator(value: int) -> float:
        return value / total if total else 0.0

    return {
        "dataset": "multilingual_antihardcoding_v1",
        "case_count": total,
        "equivalence_group_count": len(signatures),
        "metrics": {
            "semantic_correctness": denominator(semantic_hits),
            "plan_composition_correctness": denominator(plan_hits),
            "outcome_correctness": denominator(outcome_hits),
            "multilingual_consistency": (
                consistency_groups / len(signatures) if signatures else 0.0
            ),
        },
        "cases": results,
    }


def _contains_assertion(items: Any, key: str, expected: Any) -> bool:
    if isinstance(items, Mapping):
        return items.get(key) == expected or any(
            _contains_assertion(value, key, expected) for value in items.values()
        )
    if isinstance(items, list):
        return any(_contains_assertion(item, key, expected) for item in items)
    return False
