"""Semantic Understanding & Comparison Baseline v1 runner.

This runner evaluates the frozen Phase 3.4.3 pipeline with the repaired v1.1
measurement evaluator. It adapts the baseline dataset's ``expected`` schema
without changing the system under test or the independent measurement oracle.
No MCP, SQL, provider execution, or executable Eloquent is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import semantic_comparison_baseline_evaluator_v1_1 as evaluator
import semantic_understanding_phase3 as phase3
import semantic_understanding_phase32 as phase32
import semantic_understanding_phase343 as phase343
import semantic_understanding_phase343_runner as phase343_runner
from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import (
    CAPABILITIES,
    SOURCE_DATE,
    SOURCE_TIMEZONE,
    scoped_catalog,
)
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import capabilities


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _understanding_case(case: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    return {
        "understanding": {
            "requested_fields": expected.get("requested_fields", []),
            "measure": expected.get("measure"),
            "temporal": expected.get("temporal"),
            "breakdowns": expected.get("breakdowns", []),
            "calendar_conditions": expected.get("calendar_conditions", []),
            "order_by": expected.get("order_by", []),
            "limit": expected.get("limit"),
            "ambiguous": expected["answerability"] == "NEEDS_CLARIFICATION",
        }
    }


def understanding_differences(
    case: dict[str, Any], value: phase343.SemanticUnderstandingV343
) -> list[str]:
    expected = case["expected"]
    differences: list[str] = []
    if sorted(value.requested_fields) != sorted(expected.get("requested_fields", [])):
        differences.append("UNDERSTANDING_RESULT_FIELDS")
    actual_measure = None if value.measure is None else value.measure.model_dump()
    if actual_measure != expected.get("measure"):
        differences.append("UNDERSTANDING_MEASURE")
    if phase343_runner.actual_core(value) != phase343_runner.expected_core(case):
        differences.append("UNDERSTANDING_TEMPORAL")
    actual_breakdowns = [item.model_dump(exclude_none=True) for item in value.breakdowns]
    if actual_breakdowns != expected.get("breakdowns", []):
        differences.append("UNDERSTANDING_BREAKDOWN")
    actual_calendar = [item.model_dump(exclude_none=True) for item in value.calendar_conditions]
    if actual_calendar != expected.get("calendar_conditions", []):
        differences.append("UNDERSTANDING_CALENDAR")
    expected_comparison = expected.get("comparison")
    expected_shape = (
        {"alignment": expected.get("alignment"), "operation": expected.get("operation")}
        if expected_comparison is not None
        else None
    )
    if phase343_runner.comparison_shape(value) != expected_shape:
        differences.append("UNDERSTANDING_COMPARISON_SHAPE")
    expected_answerability = case["expected"]["answerability"]
    actual_answerability = phase343_runner.answerability(value)
    if actual_answerability != expected_answerability:
        differences.append("UNDERSTANDING_ANSWERABILITY")
    expected_unsupported = expected_answerability == "UNSUPPORTED_QUERY"
    if bool(value.unsupported_reasons) != expected_unsupported:
        differences.append("UNDERSTANDING_UNSUPPORTED")
    return sorted(set(differences))


def scope_differences(case: dict[str, Any], selected: list[str]) -> list[str]:
    if "capabilities" not in case["expected"]:
        return []
    expected = sorted(case["expected"]["capabilities"])
    return [] if sorted(selected) == expected else ["CAPABILITY_SCOPE_MISMATCH"]


def _expected_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def iter_compiled_intents(
    compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246,
) -> list[phase3.SemanticQueryIntentV246]:
    """Traverse compiled intent containers without changing their semantics."""
    if isinstance(compiled, phase343.ComparisonPlan):
        return [compiled.left, compiled.right]
    return [compiled]


def derived_entities_for_compiled(
    compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246,
) -> list[str]:
    """Derive the deterministic entity union for simple or comparison output."""
    return sorted(
        {
            entity
            for intent in iter_compiled_intents(compiled)
            for entity in phase3.derived_entities(intent)
        }
    )


def forbidden_constructs_for_compiled(
    compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246,
) -> list[str]:
    """Scan serialized inspection intents for forbidden executable constructs."""
    serialized = json.dumps(compiled.model_dump(), ensure_ascii=False).lower()
    tokens = (
        "select ",
        " where ",
        " where_raw",
        "selectraw",
        "orderbyraw",
        "db::raw",
    )
    return [token for token in tokens if token in serialized]


def instrumentation_snapshot(
    compiled: phase343.ComparisonPlan | phase3.SemanticQueryIntentV246,
) -> dict[str, Any]:
    """Collect structural artifacts for either compiled output shape."""
    return {
        "serialized": compiled.model_dump(),
        "entities": derived_entities_for_compiled(compiled),
        "compiled_plan_core": phase343_runner.compiled_plan_core(compiled),
        "forbidden_constructs": forbidden_constructs_for_compiled(compiled),
    }


def assert_runner_instrumentation() -> None:
    """Verify all structural instrumentation paths before model execution."""
    simple = phase3.SemanticQueryIntentV246(
        goal="overtime",
        measures=[{"field": "overtime.approved_minutes", "aggregation": "SUM"}],
    )
    assert instrumentation_snapshot(simple)["entities"] == ["overtime"]

    comparison = phase343.ComparisonPlan(
        left=simple,
        right=simple,
        alignment="SAME_PERIOD",
        operation="SIDE_BY_SIDE",
    )
    snapshot = instrumentation_snapshot(comparison)
    assert snapshot["entities"] == ["overtime"]
    assert snapshot["forbidden_constructs"] == []

    wrong = comparison.model_copy(update={"operation": "DELTA"})
    case = {
        "answerability": "UNDERSTOOD_AND_EXECUTABLE",
        "comparison": {
            "left": {
                "reference_frame": "CURRENT_MONTH",
                "relation": "EXACT",
                "unit": "MONTH",
            },
            "right": {
                "reference_frame": "CURRENT_MONTH",
                "relation": "PREVIOUS",
                "unit": "MONTH",
            },
        },
        "alignment": "SAME_PERIOD",
        "operation": "SIDE_BY_SIDE",
    }
    understanding = phase343.SemanticUnderstandingV343(
        goal="overtime",
        measure=phase3.SemanticMeasure(
            field="overtime.approved_minutes", aggregation="SUM"
        ),
        comparison=phase343.ComparisonMeaningV343(
            left=phase343.TemporalMeaningV343(
                reference_frame="CURRENT_MONTH", relation="EXACT", unit="MONTH"
            ),
            right=phase343.TemporalMeaningV343(
                reference_frame="CURRENT_MONTH", relation="PREVIOUS", unit="MONTH"
            ),
            alignment="SAME_PERIOD",
        ),
    )
    assert "COMPILED_OPERATION_MISMATCH" in evaluator.compiler_differences(
        case, understanding, wrong
    )
def _first_layer(
    selected_diff: list[str],
    canonical_diff: list[str],
    effective_diff: list[str],
    compiler_diff: list[str],
    normalization_error: str | None,
) -> str:
    if normalization_error:
        return "NORMALIZATION_FAILURE"
    if selected_diff and not effective_diff:
        return "SCOPE_FAILURE_RECOVERED"
    if effective_diff:
        return "SCOPE_FAILURE"
    if canonical_diff:
        return "RAW_OR_CANONICAL_UNDERSTANDING_FAILURE"
    if compiler_diff:
        return "COMPILER_FAILURE_WITH_VALID_INPUT"
    return "FULL_SUCCESS"


def evaluate_case(
    case: dict[str, Any],
    llm: OpenAIStructuredModel,
    repetition: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    scope_instructions = (
        f"{phase3.SCOPE_PROMPT}\n\nQuestion:\n{case['question']}\n\n"
        f"Capabilities:\n{json.dumps(CAPABILITIES)}"
    )
    scope = llm.parse(
        purpose="semantic-baseline-v1-capability-scope",
        instructions=scope_instructions,
        output_model=ScopeSelectionV243,
    )
    selected = capabilities(scope)
    selected_catalog = scoped_catalog(selected)
    understanding_instructions = (
        f"{phase343.UNDERSTANDING_PROMPT_V343}\n\nQuestion:\n{case['question']}\n\n"
        f"Source date: {SOURCE_DATE.isoformat()}\nTimezone: {SOURCE_TIMEZONE}\n"
        f"Scoped catalog:\n{json.dumps(selected_catalog)}"
    )
    raw = llm.parse(
        purpose="semantic-baseline-v1-understanding",
        instructions=understanding_instructions,
        output_model=phase343.SemanticUnderstandingV343,
    )
    canonical = phase343_runner.canonicalize(raw)
    selected_diff = scope_differences(case, selected)
    raw_diff = understanding_differences(case, raw)
    canonical_diff = understanding_differences(case, canonical)
    derived = phase32.derive_required_capabilities(canonical)
    effective = phase32.effective_capabilities(selected, canonical)
    effective_diff = scope_differences(case, effective)

    compiled = phase343.compile_comparison(canonical)
    normalization_error = None
    normalized = None
    try:
        if isinstance(compiled, phase343.ComparisonPlan):
            normalized = {
                "left": phase3.normalize_time_scope(compiled.left.time_scope),
                "right": phase3.normalize_time_scope(compiled.right.time_scope),
            }
        else:
            normalized = phase3.normalize_time_scope(compiled.time_scope)
    except (AttributeError, TypeError, ValueError, KeyError) as exc:
        normalization_error = f"{type(exc).__name__}: {exc}"

    compiler_diff = evaluator.compiler_differences(case["expected"], canonical, compiled)
    compiler_success = not compiler_diff
    compiled_success = not canonical_diff and compiler_success and not effective_diff
    compiled_instrumentation = instrumentation_snapshot(compiled)
    row = {
        "id": case["id"],
        "repetition": repetition,
        "question": case["question"],
        "language": case["language"],
        "group": case["group"],
        "category": case["category"],
        "expected": case["expected"],
        "scope": scope.model_dump(),
        "selected_capabilities": selected,
        "selected_scope_differences": selected_diff,
        "selected_scope_success": not selected_diff,
        "selected_scoped_catalog": selected_catalog,
        "raw_understanding": raw.model_dump(),
        "raw_understanding_differences": raw_diff,
        "raw_understanding_success": not raw_diff,
        "canonical_understanding": canonical.model_dump(),
        "canonical_understanding_differences": canonical_diff,
        "canonical_understanding_success": not canonical_diff,
        "canonicalization_changed": raw.model_dump() != canonical.model_dump(),
        "reference_fields": sorted(phase32.referenced_fields(canonical)),
        "derived_required_capabilities": derived,
        "effective_capabilities": effective,
        "effective_scope_differences": effective_diff,
        "effective_scope_success": not effective_diff,
        "compiled_intent": compiled.model_dump(),
        "compiled_plan_core": compiled_instrumentation["compiled_plan_core"],
        "derived_answerability": phase343_runner.compiled_answerability(compiled),
        "normalized_time_scope": normalized,
        "normalization_error": normalization_error,
        "compiled_differences": compiler_diff,
        "compiler_success": compiler_success,
        "compiled_semantic_success": compiled_success,
        "first_failing_layer": _first_layer(
            selected_diff,
            canonical_diff,
            effective_diff,
            compiler_diff,
            normalization_error,
        ),
        "derived_entities": compiled_instrumentation["entities"],
        "forbidden_constructs": compiled_instrumentation["forbidden_constructs"],
        "eloquent_like": (
            None
            if normalization_error
            else (
                phase3.eloquent_like(compiled.left, normalized["left"])
                if isinstance(compiled, phase343.ComparisonPlan)
                else phase3.eloquent_like(compiled, normalized)
            )
        ),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    return row


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    valid = [
        row
        for row in rows
        if row["effective_scope_success"] and row["canonical_understanding_success"]
    ]
    failures = Counter(row["first_failing_layer"] for row in rows)
    by_group: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    by_language: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    for row in rows:
        for target, key in ((by_group[row["group"]], "group"), (by_language[row["language"]], "language")):
            target["runs"] += 1
            target["compiled_success"] += int(row["compiled_semantic_success"])
            target["canonical_success"] += int(row["canonical_understanding_success"])
    return {
        "cases": len({row["id"] for row in rows}),
        "repetitions": total // max(1, len({row["id"] for row in rows})),
        "total_case_executions": total,
        "total_llm_calls": total * 2,
        "structured_output_success": total,
        "raw_understanding_success": sum(row["raw_understanding_success"] for row in rows),
        "canonical_understanding_success": sum(row["canonical_understanding_success"] for row in rows),
        "compiled_semantic_success": sum(row["compiled_semantic_success"] for row in rows),
        "selected_scope_success": sum(row["selected_scope_success"] for row in rows),
        "effective_scope_success": sum(row["effective_scope_success"] for row in rows),
        "compiler_valid_input_cases": len(valid),
        "compiler_success_given_valid_input": sum(row["compiler_success"] for row in valid),
        "normalization_errors": sum(bool(row["normalization_error"]) for row in rows),
        "first_failing_layer": dict(failures),
        "by_group": {key: dict(value) for key, value in by_group.items()},
        "by_language": {key: dict(value) for key, value in by_language.items()},
        "measurement_evaluator": "semantic_comparison_baseline_evaluator_v1_1",
    }


def run(cases_path: Path, output_dir: Path, model: str, repetitions: int) -> None:
    cases = load_cases(cases_path)
    llm = OpenAIStructuredModel(
        api_key=os.environ["OPENAI_API_KEY"],
        model=model,
        max_retries=0,
    )
    rows: list[dict[str, Any]] = []
    for repetition in range(1, repetitions + 1):
        for case in cases:
            rows.append(evaluate_case(case, llm, repetition))
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = aggregate(rows)
    manifest = {
        "baseline": "semantic-understanding-comparison-v1",
        "phase": "baseline-v1",
        "run_type": "measurement-evaluator-v1.1",
        "architecture_commit": "ac8410bdec7aa71ec0f6392f7c240c4032c058e8",
        "measurement_evaluator": "semantic_comparison_baseline_evaluator_v1_1",
        "dataset": str(cases_path),
        "dataset_sha256": _expected_hash(cases_path),
        "cases": len(cases),
        "repetitions": repetitions,
        "model": model,
        "source_date": SOURCE_DATE.isoformat(),
        "timezone": SOURCE_TIMEZONE,
        "retries": 0,
        "total_case_executions": len(rows),
        "total_llm_calls": len(rows) * 2,
        "mcp_execution": False,
        "sql_execution": False,
        "eloquent_execution": False,
        "gates": {
            "structured_output": 0.99,
            "canonical_understanding": 0.80,
            "compiled_semantic_success": 0.80,
            "compiler_valid_input": 0.98,
            "effective_scope": 0.98,
            "canonical_abstention_safety": 1.0,
            "compiled_abstention_safety": 1.0,
            "payroll_contamination": 0.0,
            "entity_derivation": 1.0,
            "passing_set_reliability": 0.90,
            "comparison_understanding": 0.75,
            "comparison_plan_semantic_success": 0.75,
            "comparison_compiler_valid_input": 0.98,
        },
    }
    summaries: dict[str, dict[str, Any]] = {}
    for row in rows:
        summary = summaries.setdefault(
            row["id"],
            {
                "id": row["id"],
                "question": row["question"],
                "runs": 0,
                "raw_success": 0,
                "canonical_success": 0,
                "compiled_success": 0,
                "first_failing_layers": Counter(),
            },
        )
        summary["runs"] += 1
        summary["raw_success"] += int(row["raw_understanding_success"])
        summary["canonical_success"] += int(row["canonical_understanding_success"])
        summary["compiled_success"] += int(row["compiled_semantic_success"])
        summary["first_failing_layers"][row["first_failing_layer"]] += 1
    failure_clusters = Counter(row["first_failing_layer"] for row in rows)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (output_dir / "case_summary.jsonl").write_text(
        "\n".join(
            json.dumps({**summary, "first_failing_layers": dict(summary["first_failing_layers"])}, ensure_ascii=False)
            for summary in summaries.values()
        ) + "\n",
        encoding="utf-8",
    )
    (output_dir / "failure_clusters.json").write_text(json.dumps(dict(failure_clusters), indent=2), encoding="utf-8")
    (output_dir / "baseline_report.md").write_text(
        "# Semantic Understanding & Comparison Baseline v1\n\n"
        f"- Cases: {len(cases)}\n- Repetitions: {repetitions}\n"
        f"- Total case executions: {len(rows)}\n- Total LLM calls: {len(rows) * 2}\n"
        f"- Measurement evaluator: semantic_comparison_baseline_evaluator_v1_1\n\n"
        "Metrics are persisted in `metrics.json`; complete per-execution evidence is in `raw_responses.jsonl`.\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    if args.repetitions != 5:
        raise ValueError("Baseline v1 requires exactly 5 repetitions")
    phase343.assert_phase343_contract()
    evaluator.assert_evaluator_contract()
    assert_runner_instrumentation()
    run(args.cases, args.output_dir, args.model, args.repetitions)


if __name__ == "__main__":
    main()
