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


def _case(case_id: str, *, answerable: bool, fact: bool = False):
    return PolicyEvaluationCase(
        case_id=case_id,
        query="What is the rule?",
        as_of=date(2026, 1, 1),
        expected_status=(
            PolicyRetrievalStatus.COMPLETED
            if answerable
            else PolicyRetrievalStatus.INSUFFICIENT_DATA
        ),
        expected_answerable=answerable,
        expected_document_key="policy-a" if answerable else None,
        expected_policy_facts=("manager approval",) if fact else (),
    )


def _prediction(case_id: str, *, answerable: bool, fact: bool = False):
    evidence = (
        [{"type": "policy", "document_key": "policy-a", "fragment": "Manager approval is required."}]
        if answerable
        else []
    )
    return {
        "case_id": case_id,
        "status": "COMPLETED" if answerable else "INSUFFICIENT_DATA",
        "answerable": answerable,
        "retrieved_policy_documents": [{"document_key": "policy-a"}] if answerable else [],
        "evidence": evidence,
        "answer": "Manager approval is required." if fact else "The rule is documented.",
        "citations_valid": True,
    }


def test_abstention_accuracy_uses_only_negative_denominator():
    cases = [_case("positive", answerable=True), _case("negative", answerable=False)]
    result = evaluate_predictions(cases, [_prediction("positive", answerable=True), _prediction("negative", answerable=False)])
    assert result["metrics"]["answerability_accuracy"] == 1.0
    assert result["metrics"]["abstention_accuracy"] == 1.0

    answered_negative = evaluate_predictions(
        cases, [_prediction("positive", answerable=True), _prediction("negative", answerable=True)]
    )
    assert answered_negative["metrics"]["answerability_accuracy"] == 0.5
    assert answered_negative["metrics"]["abstention_accuracy"] == 0.0


def test_policy_fact_coverage_is_deterministic_and_excludes_na():
    cases = [_case("with-fact", answerable=True, fact=True), _case("without-fact", answerable=True)]
    result = evaluate_predictions(cases, [_prediction("with-fact", answerable=True, fact=True), _prediction("without-fact", answerable=True)])
    item = result["cases"][0]
    assert item["expected_policy_facts"] == ["manager approval"]
    assert item["supported_facts"] == ["manager approval"]
    assert item["policy_fact_coverage"] == 1.0
    assert result["metrics"]["policy_fact_coverage"] == 1.0


def test_failed_layer_retrieval_is_reported_before_semantic_verification():
    case = _case("retrieval", answerable=True)
    prediction = _prediction("retrieval", answerable=False)
    prediction["evidence_verification"] = {"answerable": False}
    result = evaluate_predictions([case], [prediction])
    assert result["cases"][0]["failed_layer"] == "retrieval"


def test_failed_layer_semantic_verifier_is_reported_after_correct_retrieval():
    case = _case("semantic", answerable=True)
    prediction = _prediction("semantic", answerable=False)
    prediction["retrieved_policy_documents"] = [{"document_key": "policy-a"}]
    prediction["retrieved_evidence"] = [
        {
            "document_id": "doc-a",
            "policy_version_id": "version-a",
            "chunk_id": "chunk-a",
            "version": "1",
            "fragment": "Manager approval is required.",
            "verified": True,
            "document_key": "policy-a",
        }
    ]
    prediction["evidence_verification"] = {"answerable": False}
    result = evaluate_predictions([case], [prediction])
    assert result["cases"][0]["failed_layer"] == "semantic_evidence_verification"


def test_failed_layer_version_selection_is_reported():
    case = PolicyEvaluationCase(
        case_id="version",
        query="What is the rule?",
        as_of=date(2026, 1, 1),
        expected_status=PolicyRetrievalStatus.COMPLETED,
        expected_answerable=True,
        expected_document_key="policy-a",
        expected_version="2",
    )
    prediction = _prediction("version", answerable=True)
    prediction["retrieved_evidence"] = [{"document_key": "policy-a", "version": "1"}]
    prediction["evidence_verification"] = {"answerable": True}
    result = evaluate_predictions([case], [prediction])
    assert result["cases"][0]["failed_layer"] == "policy_version_selection"
