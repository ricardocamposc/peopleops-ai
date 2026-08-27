import ast
import json
import re
from pathlib import Path

from peopleops_api.analysis_contracts import AnalysisPlan, SemanticRequest, StructuredAnswer
from peopleops_api.multilingual_evaluation import (
    MultilingualPrediction,
    evaluate_predictions,
    load_cases,
)
from peopleops_api.query_contracts import ConceptualQuery, QueryMetric


DATASET = (
    Path(__file__).parents[3] / "evaluation" / "cases" / "multilingual_antihardcoding_v1.jsonl"
)
RUNTIME_ROOTS = [
    Path(__file__).parents[1] / "src",
    Path(__file__).parents[2] / "reference-mcp-server" / "src",
]


def _prediction(case):
    semantic = SemanticRequest(
        goal=case.scenario,
        required_capabilities=list(case.expected_capabilities),
        entities=list(case.expected_entities),
        requires_structured_data=case.requires_structured_data,
        requires_policy=case.requires_policy,
        policy_query="vacation approval" if case.requires_policy else None,
        policy_as_of="2026-11-01" if case.requires_policy else None,
    )
    queries = [
        {
            "purpose": "case capability composition",
            "query": ConceptualQuery(
                entities=list(entities),
                metrics=[QueryMetric(function="count")],
            ),
        }
        for entities in case.expected_query_entity_sets
    ]
    plan = AnalysisPlan(
        goal=case.scenario,
        queries=queries,
        policy={"query": "vacation approval", "as_of": "2026-11-01"}
        if case.requires_policy
        else None,
    )
    facts = [{"type": "structured_data", **dict(case.expected_fact_assertions)}]
    return MultilingualPrediction(
        semantic_request=semantic,
        plan=plan,
        response=StructuredAnswer(
            answer="Deterministic evaluation fixture response.",
            facts=facts,
            status=case.expected_status,
        ),
    )


def test_multilingual_dataset_has_equivalent_es_en_pt_groups_and_negatives():
    cases = load_cases(DATASET)
    assert len(cases) == 12
    for group in {case.equivalence_group for case in cases}:
        languages = {case.language for case in cases if case.equivalence_group == group}
        assert languages == {"es", "en", "pt"}
    assert {case.scenario for case in cases} >= {
        "policy-aware",
        "payroll-cross-domain",
        "cross-domain",
        "negative-insufficient",
    }


def test_deterministic_evaluation_proves_semantic_and_composition_equivalence():
    cases = load_cases(DATASET)
    result = evaluate_predictions(cases, {case.case_id: _prediction(case) for case in cases})
    assert result["metrics"] == {
        "semantic_correctness": 1.0,
        "plan_composition_correctness": 1.0,
        "outcome_correctness": 1.0,
        "multilingual_consistency": 1.0,
    }
    assert all(case["passed"] for case in result["cases"])


def test_evaluation_detects_wrong_typed_semantics_without_phrase_fallback():
    cases = load_cases(DATASET)
    predictions = {case.case_id: _prediction(case) for case in cases}
    wrong = cases[1]
    predictions[wrong.case_id] = _prediction(wrong)
    predictions[wrong.case_id].semantic_request.required_capabilities[:] = ["workforce"]
    result = evaluate_predictions(cases, predictions)
    assert result["metrics"]["semantic_correctness"] < 1.0
    assert not result["cases"][1]["passed"]


def test_runtime_has_no_string_membership_or_language_phrase_routing():
    forbidden = re.compile(
        r"(?:question|user_question|prompt|message|wording|instructions)\s*\.?(?:lower|casefold)\s*\(|"
        r"(?:[\"'][^\"']+[\"'])\s+in\s+(?:question|user_question|prompt|message|wording|instructions)"
    )
    for root in RUNTIME_ROOTS:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert not forbidden.search(source), f"possible semantic routing in {path}"
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare) and any(isinstance(op, ast.In) for op in node.ops):
                    assert not (
                        isinstance(node.left, ast.Constant)
                        and isinstance(node.left.value, str)
                        and any(
                            isinstance(comparator, ast.Name)
                            and comparator.id in {"question", "prompt", "message", "wording"}
                            for comparator in node.comparators
                        )
                    ), f"possible semantic routing in {path}:{node.lineno}"


def test_dataset_is_versioned_jsonl_with_deterministic_ground_truth():
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        assert record["expected"]["status"] in {"completed", "insufficient_data"}
        assert isinstance(record["expected"]["query_entity_sets"], list)
