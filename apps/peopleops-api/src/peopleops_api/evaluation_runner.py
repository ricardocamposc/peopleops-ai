"""Reproducible deterministic integrated evaluation runner for Slice 16."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from peopleops_api.observability import log_event

logger = logging.getLogger(__name__)
LAYERS = (
    "semantic",
    "conceptual_mcp",
    "structured_data",
    "policy_rag",
    "workflow",
    "hitl",
    "final_answer",
)


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    layer: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    scenario: str


def load_observations(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load runtime observations keyed by the stable dataset case id."""

    observations = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(observations, dict) or not all(
        isinstance(value, dict) for value in observations.values()
    ):
        raise ValueError("observations must be a JSON object keyed by case_id")
    return observations


def load_cases(path: str | Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        raw = json.loads(line)
        if raw["layer"] not in LAYERS:
            raise ValueError(f"unsupported evaluation layer: {raw['layer']}")
        if not isinstance(raw.get("expected"), dict) or not raw["expected"]:
            raise ValueError(f"case {raw.get('case_id', '<unknown>')} has no expected values")
        cases.append(
            EvaluationCase(
                raw["case_id"],
                raw["layer"],
                raw["expected"],
                raw["observed"],
                raw.get("scenario", "default"),
            )
        )
    if not cases:
        raise ValueError("evaluation dataset is empty")
    return cases


def _case_score(case: EvaluationCase) -> tuple[bool, dict[str, Any]]:
    checks: dict[str, bool] = {}
    for key, expected in case.expected.items():
        if key == "required_claims":
            checks[key] = set(expected).issubset(set(case.observed.get("supported_claims", [])))
        elif key == "forbidden_claims":
            checks[key] = not set(expected).intersection(case.observed.get("claims", []))
        elif key == "citation_fields":
            checks[key] = all(
                all(field in item for field in expected)
                for item in case.observed.get("citations", [])
            ) and bool(case.observed.get("citations"))
        else:
            checks[key] = expected == case.observed.get(key)
    return all(checks.values()), checks


def evaluate(
    cases: list[EvaluationCase],
    *,
    run_id: str | None = None,
    observations: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    case_ids = {case.case_id for case in cases}
    if len(case_ids) != len(cases):
        raise ValueError("evaluation case_id values must be unique")
    if observations is not None and set(observations) != case_ids:
        raise ValueError("observations keys must exactly match dataset case_ids")
    evaluated_cases = [
        EvaluationCase(
            case.case_id,
            case.layer,
            case.expected,
            observations[case.case_id] if observations is not None else case.observed,
            case.scenario,
        )
        for case in cases
    ]
    if run_id is None:
        fingerprint = json.dumps(
            [case.__dict__ for case in evaluated_cases], sort_keys=True, separators=(",", ":")
        ).encode()
        run_id = hashlib.sha256(fingerprint).hexdigest()[:16]
    grouped: dict[str, list[dict[str, Any]]] = {layer: [] for layer in LAYERS}
    request_ids = {}
    for case in evaluated_cases:
        request_id = case.observed.get("request_id", f"eval-{case.case_id}")
        request_ids[case.case_id] = request_id
        passed, checks = _case_score(case)
        grouped[case.layer].append(
            {
                "case_id": case.case_id,
                "scenario": case.scenario,
                "request_id": request_id,
                "passed": passed,
                "checks": checks,
            }
        )
        log_event(
            logger,
            "evaluation case completed",
            event="evaluation_case",
            run_id=run_id,
            case_id=case.case_id,
            stage=case.layer,
            status="passed" if passed else "failed",
        )
    layers = {}
    for layer in LAYERS:
        results = grouped[layer]
        passed = sum(item["passed"] for item in results)
        layers[layer] = {
            "case_count": len(results),
            "passed": passed,
            "pass_rate": passed / len(results) if results else 0.0,
            "cases": results,
        }
    return {
        "schema_version": "slice16.integrated.v1",
        "run_id": run_id,
        "dataset_version": "integrated_v1",
        "case_count": len(evaluated_cases),
        "request_ids": request_ids,
        "metrics": {layer: layers[layer]["pass_rate"] for layer in LAYERS},
        "layers": layers,
        "deterministic": True,
        "llm_judge": {"enabled": False, "reason": "optional and not part of baseline"},
    }


def compare_baseline(result: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    comparison = {}
    thresholds = baseline.get("thresholds", {})
    for layer in LAYERS:
        actual = result["metrics"].get(layer, 0.0)
        minimum = thresholds.get(layer, baseline.get("metrics", {}).get(layer, 0.0))
        comparison[layer] = {"actual": actual, "minimum": minimum, "passed": actual >= minimum}
    return {"passed": all(item["passed"] for item in comparison.values()), "layers": comparison}


def write_artifacts(
    result: dict[str, Any], output_dir: str | Path, comparison: dict[str, Any] | None
) -> None:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{result['run_id']}.json").write_text(
        json.dumps({**result, "baseline_comparison": comparison}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# Integrated evaluation {result['run_id']}",
        "",
        f"Dataset: `{result['dataset_version']}`",
        "",
        "| Layer | Cases | Passed | Pass rate |",
        "|---|---:|---:|---:|",
    ]
    for layer in LAYERS:
        item = result["layers"][layer]
        lines.append(
            f"| {layer} | {item['case_count']} | {item['passed']} | {item['pass_rate']:.2%} |"
        )
    if comparison:
        lines.extend(["", f"Baseline regression: **{'PASS' if comparison['passed'] else 'FAIL'}**"])
    (directory / f"{result['run_id']}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="evaluation/cases/integrated_v1.jsonl")
    parser.add_argument("--output-dir", default="evaluation/runs")
    parser.add_argument("--baseline", default="evaluation/baselines/slice16-integrated.json")
    parser.add_argument(
        "--observations",
        help="optional JSON object keyed by case_id; defaults to dataset observations",
    )
    args = parser.parse_args()
    cases = load_cases(args.dataset)
    observations = load_observations(args.observations) if args.observations else None
    result = evaluate(cases, observations=observations)
    baseline = Path(args.baseline)
    comparison = (
        compare_baseline(result, json.loads(baseline.read_text(encoding="utf-8")))
        if baseline.exists()
        else None
    )
    write_artifacts(result, args.output_dir, comparison)
    print(json.dumps({"run_id": result["run_id"], "metrics": result["metrics"]}, sort_keys=True))
    return 0 if comparison is None or comparison["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
