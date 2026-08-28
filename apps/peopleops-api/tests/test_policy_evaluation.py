from datetime import date
from pathlib import Path

from peopleops_api.policy_evaluation import (
    PolicyEvaluationCase,
    evaluate_predictions,
    load_cases,
)
from peopleops_api.policy_retrieval import PolicyRetrievalStatus


def test_policy_dataset_contains_only_expected_values():
    cases = load_cases(Path(__file__).parents[3] / "evaluation" / "cases" / "policy_rag_v1.jsonl")

    assert len(cases) == 12
    assert {case.language for case in cases} == {"en", "es", "pt"}
    assert all(not hasattr(case, "observed") for case in cases)


def test_evaluator_keeps_non_applicable_metrics_out_of_denominators():
    cases = [
        PolicyEvaluationCase(
            case_id="positive",
            query="What is the rule?",
            as_of=date(2026, 1, 1),
            expected_status=PolicyRetrievalStatus.COMPLETED,
            expected_answerable=True,
            expected_document_key="policy-a",
            expected_version="1",
        ),
        PolicyEvaluationCase(
            case_id="negative",
            query="What is absent?",
            as_of=date(2026, 1, 1),
            expected_status=PolicyRetrievalStatus.POLICY_NOT_FOUND,
            expected_answerable=False,
        ),
    ]
    result = evaluate_predictions(
        cases,
        [
            {
                "case_id": "positive",
                "status": "COMPLETED",
                "answerable": True,
                "policy_sources": [{"document_key": "policy-a"}],
                "policy_versions": [{"version": "1"}],
                "evidence": [],
                "citations_valid": True,
            },
            {
                "case_id": "negative",
                "status": "POLICY_NOT_FOUND",
                "answerable": False,
                "policy_sources": [],
                "policy_versions": [],
                "evidence": [],
                "citations_valid": True,
            },
        ],
    )

    assert result["metrics"]["document_recall"] == 1.0
    assert result["metrics"]["policy_version_accuracy"] == 1.0
    assert result["metrics"]["page_or_section_recall"] is None
    assert result["metrics"]["answerability_accuracy"] == 1.0


def test_evaluator_penalizes_irrelevant_retrieved_documents():
    case = PolicyEvaluationCase(
        case_id="precision",
        query="What is the rule?",
        as_of=date(2026, 1, 1),
        expected_status=PolicyRetrievalStatus.COMPLETED,
        expected_answerable=True,
        expected_document_keys=("policy-a",),
    )
    result = evaluate_predictions(
        [case],
        [
            {
                "case_id": "precision",
                "status": "COMPLETED",
                "answerable": True,
                "retrieved_policy_documents": [
                    {"document_key": "policy-a"},
                    {"document_key": "policy-noise"},
                ],
                "evidence": [],
                "citations_valid": True,
            }
        ],
    )

    case_result = result["cases"][0]
    assert case_result["document_recall"] == 1.0
    assert case_result["document_precision"] == 0.5
    assert case_result["retrieval_noise_rate"] == 0.5
    assert result["metrics"]["document_precision"] == 0.5


def test_evaluator_marks_unexpected_retrieval_for_no_evidence_case():
    case = PolicyEvaluationCase(
        case_id="negative",
        query="What is absent?",
        as_of=date(2026, 1, 1),
        expected_status=PolicyRetrievalStatus.INSUFFICIENT_DATA,
        expected_answerable=False,
    )
    result = evaluate_predictions(
        [case],
        [
            {
                "case_id": "negative",
                "status": "INSUFFICIENT_DATA",
                "answerable": False,
                "retrieved_policy_documents": [{"document_key": "unrelated"}],
                "evidence": [],
                "citations_valid": True,
            }
        ],
    )

    assert result["cases"][0]["document_precision"] == 0.0
    assert result["cases"][0]["retrieval_noise_rate"] == 1.0
