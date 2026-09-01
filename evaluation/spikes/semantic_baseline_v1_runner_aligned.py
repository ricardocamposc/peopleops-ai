"""Semantic Understanding & Comparison Baseline v1 runner.

This runner freezes the validated measurement instrument and executes the 48-case
baseline without modifying Semantic Understanding, canonicalization, compiler, or
normalization semantics. It supports inspection (1 repetition) and reliability
runs (N repetitions) over the same dataset/oracle.
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

import semantic_comparison_baseline_evaluator_v1 as baseline_evaluator
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

EVALUATOR_NAME = "semantic_comparison_baseline_evaluator_v1"
RUNNER_VERSION = "semantic-baseline-v1-aligned"


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _dump_list(items: list[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(exclude_none=True) for item in items]


def _expected_measure(expected: dict[str, Any]) -> dict[str, Any] | None:
    measure = expected.get("measure")
    if measure is None:
        return None
    return {key: value for key, value in measure.items() if value is not None}


def _actual_measure(value: phase343.SemanticUnderstandingV343) -> dict[str, Any] | None:
    if value.measure is None:
        return None
    return value.measure.model_dump(exclude_none=True)


def _expected_breakdowns(expected: dict[str, Any]) -> list[dict[str, Any]]:
    return expected.get("breakdowns") or []


def _actual_breakdowns(value: phase343.SemanticUnderstandingV343) -> list[dict[str, Any]]:
    return _dump_list(value.breakdowns)


def _expected_calendar(expected: dict[str, Any]) -> list[dict[str, Any]]:
    return expected.get("calendar_conditions") or []


def _actual_calendar(value: phase343.SemanticUnderstandingV343) -> list[dict[str, Any]]:
    return _dump_list(value.calendar_conditions)


def _expected_order(expected: dict[str, Any]) -> list[dict[str, Any]]:
    return expected.get("order_by") or []


def _actual_order(value: phase343.SemanticUnderstandingV343) -> list[dict[str, Any]]:
    return _dump_list(value.order_by)


def _comparison_core_from_expected(expected: dict[str, Any]) -> dict[str, Any] | None:
    comparison = expected.get("comparison")
    if comparison is None:
        return None
    return {
        "left": phase343_runner.operand_core(comparison["left"]),
        "right": phase343_runner.operand_core(comparison["right"]),
        "alignment": expected.get("alignment"),
        "operation": expected.get("operation"),
    }


def _comparison_core_from_actual(
    value: phase343.SemanticUnderstandingV343,
) -> dict[str, Any] | None:
    if value.comparison is None:
        return None
    return {
        "left": phase343_runner.operand_core(value.comparison.left.model_dump()),
        "right": phase343_runner.operand_core(value.comparison.right.model_dump()),
        "alignment": value.comparison.alignment,
        "operation": value.comparison.operation,
    }


def understanding_differences(
    expected: dict[str, Any],
    value: phase343.SemanticUnderstandingV343,
) -> list[str]:
    """Compare raw/canonical Semantic Understanding against the dataset oracle."""
    differences: list[str] = []
    if phase343_runner.answerability(value) != expected["answerability"]:
        differences.append("ANSWERABILITY_MISMATCH")

    if value.requested_fields != (expected.get("requested_fields") or []):
        differences.append("RESULT_FIELDS_MISMATCH")
    if _actual_measure(value) != _expected_measure(expected):
        differences.append("MEASURE_MISMATCH")
    if _actual_breakdowns(value) != _expected_breakdowns(expected):
        differences.append("BREAKDOWN_MISMATCH")
    if _actual_calendar(value) != _expected_calendar(expected):
        differences.append("CALENDAR_CONDITION_MISMATCH")
    if _actual_order(value) != _expected_order(expected):
        differences.append("ORDER_BY_MISMATCH")
    if value.limit != expected.get("limit"):
        differences.append("LIMIT_MISMATCH")

    expected_comparison = _comparison_core_from_expected(expected)
    actual_comparison = _comparison_core_from_actual(value)
    if expected_comparison != actual_comparison:
        differences.append("COMPARISON_MISMATCH")

    if expected_comparison is None:
        expected_temporal = (
            phase343_runner.operand_core(expected["temporal"])
            if expected.get("temporal")
            else None
        )
        actual_temporal = (
            phase343_runner.operand_core(value.temporal.model_dump())
            if value.temporal
            else None
        )
        if actual_temporal != expected_temporal:
            differences.append("TEMPORAL_MISMATCH")
    elif value.temporal is not None:
        differences.append("UNEXPECTED_SIMPLE_TEMPORAL")

    if expected["answerability"] != "UNDERSTOOD_AND_EXECUTABLE":
        executable = bool(
            value.requested_fields
            or value.measure is not None
            or value.temporal is not None
            or value.comparison is not None
            or value.breakdowns
            or value.calendar_conditions
            or value.order_by
            or value.limit is not None
        )
        if executable:
            differences.append("NON_EXECUTABLE_UNDERSTANDING_CONTENT_PRESENT")

    return differences


def _expected_capabilities(case: dict[str, Any]) -> set[str] | None:
    values = case.get("expected", {}).get("capabilities")
    return set(values) if values else None


def _effective_capabilities(
    selected: list[str],
    canonical: phase343.SemanticUnderstandingV343,
) -> list[str]:
    """Use the existing structural capability closure without reimplementing it."""
    return phase32.effective_capabilities(selected, canonical)


def _fingerprint(value: phase343.SemanticUnderstandingV343) -> str:
    payload = value.model_dump(exclude={"goal"}, exclude_none=True)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _failure_cluster(differences: list[str]) -> str:
    if not differences:
        return "FULL_SUCCESS"
    first = differences[0]
    mapping = {
        "ANSWERABILITY": "ANSWERABILITY",
        "TEMPORAL": "TEMPORAL",
        "COMPARISON": "COMPARISON",
        "CALENDAR": "CALENDAR",
        "BREAKDOWN": "GROUPING",
        "GROUP_BY": "GROUPING",
        "RESULT_FIELDS": "PROJECTION",
        "MEASURE": "MEASURE",
        "ORDER_BY": "ORDER",
        "CAPABILITY": "SCOPE",
        "NORMALIZED": "NORMALIZATION",
    }
    for needle, cluster in mapping.items():
        if needle in first:
            return cluster
    return "OTHER"


def _percent(num: int, den: int) -> float | None:
    return None if den == 0 else round(num * 100.0 / den, 2)


def _aggregate(rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    raw_success = sum(row["raw_success"] for row in rows)
    canonical_success = sum(row["canonical_success"] for row in rows)
    compiled_success = sum(row["compiled_success"] for row in rows)
    compiler_valid = [row for row in rows if row["canonical_success"]]
    comparison_rows = [row for row in rows if row["expected"].get("comparison")]
    simple_rows = [row for row in rows if not row["expected"].get("comparison")]

    group_metrics: dict[str, dict[str, Any]] = {}
    for group in sorted({case.get("group", "?") for case in cases}):
        group_rows = [row for row in rows if row.get("group") == group]
        group_metrics[group] = {
            "executions": len(group_rows),
            "raw_success": sum(row["raw_success"] for row in group_rows),
            "canonical_success": sum(row["canonical_success"] for row in group_rows),
            "compiled_success": sum(row["compiled_success"] for row in group_rows),
            "compiled_success_pct": _percent(
                sum(row["compiled_success"] for row in group_rows), len(group_rows)
            ),
        }

    language_metrics: dict[str, dict[str, Any]] = {}
    for language in sorted({case.get("language", "?") for case in cases}):
        lang_rows = [row for row in rows if row.get("language") == language]
        language_metrics[language] = {
            "executions": len(lang_rows),
            "canonical_success": sum(row["canonical_success"] for row in lang_rows),
            "compiled_success": sum(row["compiled_success"] for row in lang_rows),
            "compiled_success_pct": _percent(
                sum(row["compiled_success"] for row in lang_rows), len(lang_rows)
            ),
        }

    case_fingerprints: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        case_fingerprints[row["id"]][row["canonical_fingerprint"]] += 1
    fingerprint_consistency = {
        case_id: {
            "modal_count": counts.most_common(1)[0][1],
            "executions": sum(counts.values()),
            "consistency": round(counts.most_common(1)[0][1] / sum(counts.values()), 4),
        }
        for case_id, counts in case_fingerprints.items()
    }

    clusters = Counter(row["failure_cluster"] for row in rows)
    return {
        "cases": len(cases),
        "executions": total,
        "structured_output_success": total,
        "raw_understanding_success": raw_success,
        "raw_understanding_success_pct": _percent(raw_success, total),
        "canonical_understanding_success": canonical_success,
        "canonical_understanding_success_pct": _percent(canonical_success, total),
        "compiled_semantic_success": compiled_success,
        "compiled_semantic_success_pct": _percent(compiled_success, total),
        "simple_executions": len(simple_rows),
        "simple_compiled_success": sum(row["compiled_success"] for row in simple_rows),
        "simple_compiled_success_pct": _percent(
            sum(row["compiled_success"] for row in simple_rows), len(simple_rows)
        ),
        "comparison_executions": len(comparison_rows),
        "comparison_compiled_success": sum(
            row["compiled_success"] for row in comparison_rows
        ),
        "comparison_compiled_success_pct": _percent(
            sum(row["compiled_success"] for row in comparison_rows),
            len(comparison_rows),
        ),
        "compiler_valid_input_cases": len(compiler_valid),
        "compiler_success_given_valid_input": sum(
            row["compiler_success"] for row in compiler_valid
        ),
        "compiler_success_given_valid_input_pct": _percent(
            sum(row["compiler_success"] for row in compiler_valid), len(compiler_valid)
        ),
        "normalization_errors": sum(row["normalization_error"] is not None for row in rows),
        "group_metrics": group_metrics,
        "language_metrics": language_metrics,
        "failure_clusters": dict(clusters),
        "fingerprint_consistency": fingerprint_consistency,
        "mean_fingerprint_consistency": round(
            sum(item["consistency"] for item in fingerprint_consistency.values())
            / len(fingerprint_consistency),
            4,
        ) if fingerprint_consistency else None,
        "measurement_evaluator": EVALUATOR_NAME,
    }


def run(
    cases_path: Path,
    output_dir: Path,
    model: str,
    repetitions: int,
) -> None:
    cases = load_cases(cases_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    llm = OpenAIStructuredModel(
        api_key=os.environ["OPENAI_API_KEY"],
        model=model,
        max_retries=0,
    )
    rows: list[dict[str, Any]] = []

    for repetition in range(1, repetitions + 1):
        for case in cases:
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
            catalog = scoped_catalog(selected)
            instructions = (
                f"{phase343.UNDERSTANDING_PROMPT_V343}\n\nQuestion:\n{case['question']}\n\n"
                f"Source date: {SOURCE_DATE.isoformat()}\nTimezone: {SOURCE_TIMEZONE}\n"
                f"Scoped catalog:\n{json.dumps(catalog)}"
            )
            raw = llm.parse(
                purpose="semantic-baseline-v1-understanding",
                instructions=instructions,
                output_model=phase343.SemanticUnderstandingV343,
            )
            canonical = phase343_runner.canonicalize(raw)
            compiled = phase343.compile_comparison(canonical)
            expected = case["expected"]

            raw_diff = understanding_differences(expected, raw)
            canonical_diff = understanding_differences(expected, canonical)
            compiler_diff = baseline_evaluator.compiler_differences(
                expected, canonical, compiled
            )
            raw_success = not raw_diff
            canonical_success = not canonical_diff
            compiler_success = not compiler_diff
            compiled_success = canonical_success and compiler_success

            selected_expected = _expected_capabilities(case)
            effective = _effective_capabilities(selected, canonical)
            selected_scope_success = (
                None if selected_expected is None else set(selected) == selected_expected
            )
            effective_scope_success = (
                None if selected_expected is None else set(effective) == selected_expected
            )

            normalization_error: str | None = None
            try:
                compiled_core = phase343_runner.compiled_plan_core(compiled)
            except (TypeError, ValueError, AttributeError) as exc:
                compiled_core = {"error": str(exc)}
                normalization_error = f"{type(exc).__name__}: {exc}"

            rows.append(
                {
                    "id": case["id"],
                    "language": case.get("language"),
                    "group": case.get("group"),
                    "category": case.get("category"),
                    "critical": bool(case.get("critical")),
                    "repetition": repetition,
                    "question": case["question"],
                    "expected": expected,
                    "scope": scope.model_dump(),
                    "selected_capabilities": selected,
                    "effective_capabilities": effective,
                    "selected_scope_success": selected_scope_success,
                    "effective_scope_success": effective_scope_success,
                    "scoped_catalog": catalog,
                    "raw_understanding": raw.model_dump(),
                    "canonical_understanding": canonical.model_dump(),
                    "canonical_fingerprint": _fingerprint(canonical),
                    "compiled": compiled.model_dump(),
                    "compiled_plan_core": compiled_core,
                    "raw_differences": raw_diff,
                    "canonical_differences": canonical_diff,
                    "compiler_differences": compiler_diff,
                    "raw_success": raw_success,
                    "canonical_success": canonical_success,
                    "compiler_success": compiler_success,
                    "compiled_success": compiled_success,
                    "normalization_error": normalization_error,
                    "failure_cluster": _failure_cluster(
                        canonical_diff or compiler_diff or raw_diff
                    ),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )

    metrics = _aggregate(rows, cases)
    manifest = {
        "baseline": "Semantic Understanding & Comparison Baseline v1",
        "runner_version": RUNNER_VERSION,
        "dataset": str(cases_path),
        "case_count": len(cases),
        "repetitions": repetitions,
        "expected_executions": len(cases) * repetitions,
        "actual_executions": len(rows),
        "model": model,
        "source_date": SOURCE_DATE.isoformat(),
        "timezone": SOURCE_TIMEZONE,
        "retries": 0,
        "measurement_evaluator": EVALUATOR_NAME,
        "semantic_prompt": "UNDERSTANDING_PROMPT_V343",
        "canonicalizer": "semantic_understanding_phase343_runner.canonicalize",
        "compiler": "semantic_understanding_phase343.compile_comparison",
        "mcp_executed": False,
        "sql_executed": False,
        "eloquent_executed": False,
    }

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be >= 1")
    phase343.assert_phase343_contract()
    baseline_evaluator.assert_evaluator_contract()
    run(args.cases, args.output_dir, args.model, args.repetitions)


if __name__ == "__main__":
    main()
