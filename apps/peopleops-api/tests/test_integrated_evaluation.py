import json
from pathlib import Path

import pytest

from peopleops_api.evaluation_runner import (
    LAYERS,
    compare_baseline,
    evaluate,
    load_cases,
    load_observations,
)

ROOT = Path(__file__).parents[3]
DATASET = ROOT / "evaluation/cases/integrated_v1.jsonl"
BASELINE = ROOT / "evaluation/baselines/slice16-integrated.json"


def test_integrated_runner_covers_all_required_layers_and_correlates_cases():
    result = evaluate(load_cases(DATASET), run_id="run-test")
    assert result["schema_version"] == "slice16.integrated.v1"
    assert set(result["metrics"]) == set(LAYERS)
    assert all(value == 1.0 for value in result["metrics"].values())
    assert len(result["request_ids"]) == result["case_count"]


def test_integrated_baseline_is_deterministic_and_regression_checked():
    cases = load_cases(DATASET)
    assert (
        evaluate(cases, run_id="same-run")["metrics"]
        == evaluate(cases, run_id="same-run")["metrics"]
    )
    assert compare_baseline(evaluate(cases, run_id="same-run"), json.loads(BASELINE.read_text()))[
        "passed"
    ]


def test_evaluator_detects_unsupported_claim_and_does_not_hide_it():
    target = next(case for case in load_cases(DATASET) if case.layer == "final_answer")
    observed = dict(target.observed, unsupported_claim_rate=0.2)
    modified = [
        target.__class__(target.case_id, target.layer, target.expected, observed, target.scenario)
    ]
    assert evaluate(modified, run_id="negative-run")["metrics"]["final_answer"] == 0.0


def test_runner_accepts_external_observations_and_rejects_partial_input(tmp_path):
    cases = load_cases(DATASET)
    observations = {case.case_id: case.observed for case in cases}
    path = tmp_path / "observations.json"
    path.write_text(json.dumps(observations), encoding="utf-8")
    result = evaluate(cases, observations=load_observations(path), run_id="external")
    assert result["case_count"] == 7
    with pytest.raises(ValueError, match="exactly match"):
        evaluate(cases, observations={cases[0].case_id: cases[0].observed})


def test_runner_requires_non_empty_citations_when_citation_fields_are_expected():
    cases = load_cases(DATASET)
    target = next(case for case in cases if case.layer == "policy_rag")
    observed = dict(target.observed, citations=[])
    modified = [
        target.__class__(target.case_id, target.layer, target.expected, observed, target.scenario)
    ]
    assert evaluate(modified, run_id="missing-citation")["metrics"]["policy_rag"] == 0.0
