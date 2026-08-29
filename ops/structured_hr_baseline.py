"""Run structured HR ground truth cases against the real PeopleOps workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def _request(base_url: str, payload: dict, timeout: float, scopes: list[str] | None = None) -> dict:
    headers = {"Content-Type": "application/json", "X-Evaluation-Run": "structured-hr"}
    if scopes:
        headers["X-Security-Scopes"] = ",".join(scopes)
    request = Request(
        f"{base_url.rstrip('/')}/api/v1/analysis",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:500]}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"request failed: {type(exc).__name__}") from exc


def _load_cases(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [case.get("id") for case in cases]
    if not cases or any(not case_id for case_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("dataset must contain unique non-empty case ids")
    if any("observed" in case for case in cases):
        raise ValueError("structured dataset must contain ground truth only; observed is forbidden")
    return cases


def _query_parts(response: dict) -> dict[str, object]:
    semantic = response.get("semantic_request") or {}
    plan = response.get("query_plan") or response.get("analysis_plan") or {}
    entities = set(semantic.get("entities") or [])
    capabilities = set(semantic.get("required_capabilities") or [])
    metric_functions: set[str] = set()
    metric_fields: set[str] = set()
    dimensions: set[str] = set()
    queries: list[dict] = []
    for planned in plan.get("queries") or []:
        query = planned.get("query") or {}
        queries.append(query)
        entities.update(query.get("entities") or [])
        dimensions.update(query.get("dimensions") or [])
        for metric in query.get("metrics") or []:
            if metric.get("function"):
                metric_functions.add(str(metric["function"]))
            if metric.get("field"):
                metric_fields.add(str(metric["field"]))
    return {"entities": entities, "capabilities": capabilities,
            "metric_functions": metric_functions, "metric_fields": metric_fields,
            "dimensions": dimensions, "queries": queries}


def _set_recall(expected: list[str], observed: set[str]) -> float | None:
    if not expected:
        return None
    return len(set(expected) & observed) / len(set(expected))


def _observed_time_scopes(queries: list[dict]) -> set[str]:
    values: set[str] = set()
    for query in queries:
        scope = query.get("time_scope") or {}
        if scope.get("type") == "payroll_period" and scope.get("value"):
            values.add(str(scope["value"]))
        elif scope.get("type"):
            values.add(str(scope["type"]))
    return values


def _time_scope_matches(expected: dict | None, queries: list[dict], trace: dict | None = None) -> bool | None:
    if not expected:
        return None
    kind = expected.get("kind")
    scopes = [query.get("time_scope") or {} for query in queries]
    if kind == "explicit_period":
        return any(s.get("type") == "payroll_period" and s.get("value") == expected.get("value") for s in scopes)
    if kind == "latest_available":
        # The provider-neutral response does not expose the catalog's ordered
        # period set, so latest-available cannot be proven deterministically.
        return None
    if kind == "relative_window":
        ranges = [s for s in scopes if s.get("type") == "date_range" and s.get("start") and s.get("end")]
        if not ranges:
            return False
        if expected.get("days") is None:
            return True
        from datetime import date
        for scope in ranges:
            try:
                if (date.fromisoformat(str(scope["end"])) - date.fromisoformat(str(scope["start"]))).days + 1 == int(expected["days"]):
                    return True
            except (TypeError, ValueError):
                continue
        return False
    if kind == "period_comparison":
        executions = (trace or {}).get("provider_executions") or []
        distinct = {json.dumps(q.get("time_scope"), sort_keys=True) for q in queries}
        return len(queries) >= int(expected.get("expected_query_count", 2)) and len(distinct) >= 2 and len(executions) >= 2
    return False


def _authorization_check(case: dict, trace: dict) -> bool | None:
    expected = case.get("expected_authorization")
    return None if expected is None else trace.get("authorization", {}).get("decision") == expected


def _replan_check(trace: dict) -> bool | None:
    attempts = trace.get("planning_attempts") or []
    if len(attempts) < 2:
        return None
    validations = trace.get("provider_validations") or []
    return bool(any(not item.get("accepted") for item in validations) and trace.get("replan_count", 0) >= 1 and trace.get("final_validation_status") == "accepted")


def _evaluate(case: dict, response: dict) -> dict:
    parts = _query_parts(response)
    expected_answerable = case.get("expected_answerable")
    observed_answerable = response.get("status") in {"completed", "pending_human_review"}
    semantic = response.get("semantic_request") or {}
    expected_caps = set(case.get("expected_capabilities") or [])
    expected_entities = set(case.get("expected_entities") or [])
    legacy_metrics = set(case.get("expected_metrics") or [])
    expected_functions = set(case.get("expected_metric_functions") or []) | legacy_metrics.intersection({"count", "sum", "avg", "min", "max"})
    expected_fields = set(case.get("expected_metric_fields") or [])
    expected_fields.update(metric for metric in legacy_metrics if metric not in {"count", "sum", "avg", "min", "max"})
    expected_dimensions = set(case.get("expected_dimensions") or [])
    trace = response.get("evaluation_trace") or {}
    validations = trace.get("provider_validations") or []
    executions = trace.get("provider_executions") or []
    provider_valid = bool(validations) and all(item.get("accepted") is True for item in validations)
    provider_executed = bool(executions) and all(item.get("success") is True for item in executions)
    plan_generated = bool(parts["queries"])
    checks = {
        "capability_selection": expected_caps <= parts["capabilities"] if expected_caps else None,
        "entity_recall": expected_entities <= parts["entities"] if expected_entities else None,
        "metric_function_recall": expected_functions <= parts["metric_functions"] if expected_functions else None,
        "metric_field_recall": expected_fields <= parts["metric_fields"] if expected_fields else None,
        "dimension_accuracy": expected_dimensions <= parts["dimensions"] if expected_dimensions else None,
        "answerability": (
            observed_answerable is expected_answerable if expected_answerable is not None else None
        ),
        "plan_generated": plan_generated if expected_caps else None,
        "conceptual_query_validity": provider_valid if plan_generated else None,
        "workflow_execution_success": response.get("status") != "failed",
        "provider_execution_success": provider_executed if executions else None,
        "zero_result": (
            any(
                item.get("result_verification", {}).get("status") == "ZERO_ROWS"
                for item in response.get("evidence") or []
            )
            if "expected_zero_rows" in case
            else None
        ),
        "evidence_validity": provider_valid if validations else None,
        "time_scope": _time_scope_matches(case.get("expected_time_scope"), parts["queries"], trace),
        "authorization": _authorization_check(case, trace),
        "replan_success": _replan_check(trace),
    }
    return {
        "case_id": case["id"],
        "question": case["question"],
        "language": case.get("language"),
        "expected": {key: value for key, value in case.items() if key.startswith("expected_")},
        "observed": {
            "request_id": response.get("request_id"),
            "status": response.get("status"),
            "semantic_request": semantic,
            "analysis_plan": response.get("query_plan"),
            "structured_result": response.get("structured_result"),
            "evidence": response.get("evidence") or [],
            "validation": response.get("validation") or {},
            "warnings": response.get("warnings") or [],
            "response": response.get("response"),
            "latency_ms": response.get("latency_ms"),
            "model_name": response.get("model_name"),
            "evaluation_trace": trace,
        },
        "checks": checks,
        "diagnostics": {
            "expected_entities": sorted(expected_entities),
            "observed_entities": sorted(parts["entities"]),
            "expected_capabilities": sorted(expected_caps),
            "observed_capabilities": sorted(parts["capabilities"]),
            "expected_metric_functions": sorted(expected_functions),
            "observed_metric_functions": sorted(parts["metric_functions"]),
            "expected_metric_fields": sorted(expected_fields),
            "observed_metric_fields": sorted(parts["metric_fields"]),
            "expected_dimensions": sorted(expected_dimensions),
            "observed_dimensions": sorted(parts["dimensions"]),
            "provider_validation": validations,
            "provider_execution": executions,
            "failed_layer": _failed_layer(case, response, checks),
        },
    }


def _failed_layer(case: dict, response: dict, checks: dict) -> str | None:
    if response.get("status") == "failed" and not response.get("semantic_request"):
        return "UNDERSTANDING_DEFECT"
    for name, layer in (
        ("capability_selection", "UNDERSTANDING_DEFECT"),
        ("entity_recall", "PEOPLEOPS_PLAN_DEFECT"),
        ("metric_function_recall", "PEOPLEOPS_PLAN_DEFECT"),
        ("metric_field_recall", "PEOPLEOPS_PLAN_DEFECT"),
        ("dimension_accuracy", "PEOPLEOPS_PLAN_DEFECT"),
        ("plan_generated", "PEOPLEOPS_PLAN_DEFECT"),
        ("authorization", "AUTHORIZATION_DECISION"),
        ("conceptual_query_validity", "MCP_VALIDATION_DEFECT"),
        ("provider_execution_success", "PROVIDER_EXECUTION_DEFECT"),
        ("zero_result", "RESULT_VERIFICATION_DEFECT"),
        ("answerability", "SYNTHESIS_DEFECT"),
    ):
        if checks.get(name) is False:
            return layer
    return None


def _rate(records: list[dict], key: str) -> float | str:
    values = [item["checks"].get(key) for item in records]
    values = [value for value in values if value is not None]
    return sum(value is True for value in values) / len(values) if values else "N/A"


def _metric(records: list[dict], key: str) -> dict:
    values = [item["checks"].get(key) for item in records]
    values = [value for value in values if value is not None]
    return {
        "value": sum(value is True for value in values) / len(values) if values else "N/A",
        "successes": sum(value is True for value in values),
        "eligible_cases": len(values),
    }


def _recall_metric(records: list[dict], expected_key: str, observed_key: str) -> dict:
    values = []
    for item in records:
        score = _set_recall(item["diagnostics"].get(expected_key, []), set(item["diagnostics"].get(observed_key, [])))
        if score is not None:
            values.append(score)
    return {"value": sum(values) / len(values) if values else "N/A", "score_sum": sum(values), "eligible_cases": len(values)}


def run(dataset: Path, output: Path, base_url: str, timeout: float) -> dict:
    cases = _load_cases(dataset)
    output.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    records: list[dict] = []
    for index, case in enumerate(cases, 1):
        payload = {
            "question": case["question"],
            "metadata": {
                "evaluation_run_id": run_id,
                "evaluation_case_id": case["id"],
                "language": case.get("language"),
                "evaluation_structured_hr": True,
            },
        }
        started = time.monotonic()
        try:
            scopes = (case.get("evaluation_security") or {}).get("scopes") or []
            response = _request(base_url, payload, timeout, scopes=scopes)
            response.setdefault("latency_ms", round((time.monotonic() - started) * 1000))
            records.append(_evaluate(case, response))
        except Exception as exc:
            records.append({
                "case_id": case["id"], "question": case["question"], "language": case.get("language"),
                "expected": {key: value for key, value in case.items() if key.startswith("expected_")},
                "observed": {"error": str(exc)}, "checks": {"execution_success": False},
                "diagnostics": {"failed_layer": "runner"},
            })
            _write_predictions(output, records)
            raise RuntimeError(f"case {case['id']} failed: {exc}") from exc
        _write_predictions(output, records)
        print(f"[{index}/{len(cases)}] {case['id']}")
    metrics = {
        "semantic_goal_accuracy": {"value": "N/A", "successes": 0, "eligible_cases": 0},
        "capability_selection_accuracy": _metric(records, "capability_selection"),
        "plan_generated_rate": _metric(records, "plan_generated"),
        "conceptual_query_validity": _metric(records, "conceptual_query_validity"),
        "expected_entity_recall": _recall_metric(records, "expected_entities", "observed_entities"),
        "expected_metric_function_recall": _recall_metric(records, "expected_metric_functions", "observed_metric_functions"),
        "expected_metric_field_recall": _recall_metric(records, "expected_metric_fields", "observed_metric_fields"),
        "dimension_accuracy": _metric(records, "dimension_accuracy"),
        "filter_accuracy": {"value": "N/A", "successes": 0, "eligible_cases": 0},
        "time_scope_accuracy": _metric(records, "time_scope"),
        "workflow_execution_success_rate": _metric(records, "workflow_execution_success"),
        "provider_query_execution_success_rate": _metric(records, "provider_execution_success"),
        "zero_result_accuracy": _metric(records, "zero_result"),
        "evidence_validity": _metric(records, "evidence_validity"),
        "numeric_fact_accuracy": {"value": "N/A", "successes": 0, "eligible_cases": 0},
        "unsupported_quantitative_claim_rate": {"value": "N/A", "successes": 0, "eligible_cases": 0},
        "authorization_decision_accuracy": _metric(records, "authorization"),
        "answerability_accuracy": _metric(records, "answerability"),
        "abstention_accuracy": _negative_metric(records),
        "unnecessary_query_rate": {"value": "N/A", "successes": 0, "eligible_cases": 0},
        "replan_success_rate": _metric(records, "replan_success"),
    }
    manifest = {
        "run_id": run_id,
        "git_commit": _git_commit(),
        "timestamp": datetime.now(UTC).isoformat(),
        "dataset": str(dataset.resolve().relative_to(ROOT)),
        "dataset_case_count": len(cases),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "base_url": base_url,
        "execution": "real_peopleops_mcp_hris",
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "mcp_sdk": "mcp 2.1.1",
        "mcp_server": "reference-mcp-server",
        "catalog_version": "captured per response",
        "max_replans": int(os.getenv("MAX_REPLANS", "1")),
        "max_planning_attempts": 2,
        "max_execution_attempts": 2,
        "artifact_contract": ["manifest.json", "dataset.jsonl", "predictions.jsonl", "evidence.jsonl", "metrics.json", "report.md"],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "dataset.jsonl").write_text(dataset.read_text(encoding="utf-8"), encoding="utf-8")
    (output / "evidence.jsonl").write_text("".join(json.dumps(item["observed"], ensure_ascii=False) + "\n" for item in records), encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps({"metrics": metrics, "cases": records}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [item for item in records if any(value is False for value in item["checks"].values())]
    report = ["# Structured HR analysis evaluation", "", f"Run: `{run_id}`", f"Cases: {len(cases)}", "", "## Deterministic metrics", ""]
    report.extend(f"- `{key}`: {value}" for key, value in metrics.items())
    report.extend(["", "## Failed cases", ""])
    report.extend(f"- `{item['case_id']}`: failed_layer=`{item['diagnostics'].get('failed_layer')}`" for item in failed) or report.append("- None")
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return {"run_id": run_id, "metrics": metrics, "case_count": len(cases)}


def _write_predictions(output: Path, records: list[dict]) -> None:
    (output / "predictions.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), encoding="utf-8")


def _average_recall(records: list[dict], expected_key: str, observed_key: str) -> float | str:
    values = []
    for item in records:
        expected = item["diagnostics"].get(expected_key, [])
        observed = set(item["diagnostics"].get(observed_key, []))
        score = _set_recall(expected, observed)
        if score is not None:
            values.append(score)
    return sum(values) / len(values) if values else "N/A"


def _evidence_rate(records: list[dict]) -> float | str:
    applicable = [item for item in records if item["observed"].get("status") in {"completed", "pending_human_review"}]
    if not applicable:
        return "N/A"
    return sum(bool(item["observed"].get("evidence")) for item in applicable) / len(applicable)


def _negative_rate(records: list[dict]) -> float | str:
    values = [item["checks"].get("answerability") for item in records if item["expected"].get("expected_answerable") is False]
    return sum(value is True for value in values) / len(values) if values else "N/A"


def _negative_metric(records: list[dict]) -> dict:
    values = [item["checks"].get("answerability") for item in records if item["expected"].get("expected_answerable") is False]
    return {"value": sum(value is True for value in values) / len(values) if values else "N/A", "successes": sum(value is True for value in values), "eligible_cases": len(values)}


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/cases/structured_hr_analysis_v2.jsonl"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=os.getenv("PEOPLEOPS_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--request-timeout", type=float, default=180.0)
    args = parser.parse_args()
    print(json.dumps(run(args.dataset, args.output_dir, args.base_url, args.request_timeout), indent=2))


if __name__ == "__main__":
    main()
