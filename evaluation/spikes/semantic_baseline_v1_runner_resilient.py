"""Resilient Semantic Baseline v1 runner.

This runner keeps the validated baseline semantics/evaluator frozen while making
execution evidence-preserving. Model-boundary failures and compiler Pydantic
validation failures are recorded per execution instead of aborting the batch.
Unexpected runner/evaluator defects still fail fast.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

import semantic_baseline_v1_runner_aligned as base
import semantic_comparison_baseline_evaluator_v1 as baseline_evaluator
import semantic_understanding_phase3 as phase3
import semantic_understanding_phase343 as phase343
import semantic_understanding_phase343_runner as phase343_runner
from peopleops_api.analysis_workflow import OpenAIModelError, OpenAIStructuredModel
from semantic_query_dsl_phase242 import CAPABILITIES, SOURCE_DATE, SOURCE_TIMEZONE, scoped_catalog
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import capabilities

RUNNER_VERSION = "semantic-baseline-v1-resilient"
EVALUATOR_NAME = base.EVALUATOR_NAME


def _manifest(
    *, cases_path: Path, cases: list[dict[str, Any]], repetitions: int, model: str, actual: int
) -> dict[str, Any]:
    return {
        "baseline": "Semantic Understanding & Comparison Baseline v1",
        "runner_version": RUNNER_VERSION,
        "dataset": str(cases_path),
        "case_count": len(cases),
        "repetitions": repetitions,
        "expected_executions": len(cases) * repetitions,
        "actual_executions": actual,
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
        "evidence_preserving_failures": True,
    }


def _aggregate(rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = base._aggregate(rows, cases)
    structured = sum(bool(row.get("structured_output_success")) for row in rows)
    failures = Counter(
        row.get("technical_failure_class")
        for row in rows
        if row.get("technical_failure_class")
    )
    compiler_schema = sum(
        row.get("compiler_failure_class") == "COMPILER_SCHEMA_VALIDATION_ERROR"
        for row in rows
    )
    metrics.update(
        {
            "structured_output_success": structured,
            "structured_output_success_pct": base._percent(structured, len(rows)),
            "technical_failures": dict(failures),
            "technical_failure_count": sum(failures.values()),
            "compiler_schema_validation_errors": compiler_schema,
            "measurement_evaluator": EVALUATOR_NAME,
            "runner_version": RUNNER_VERSION,
        }
    )
    return metrics


def _write_checkpoint(
    *, output_dir: Path, rows: list[dict[str, Any]], cases_path: Path,
    cases: list[dict[str, Any]], repetitions: int, model: str
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(
        cases_path=cases_path,
        cases=cases,
        repetitions=repetitions,
        model=model,
        actual=len(rows),
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )
    metrics = _aggregate(rows, cases) if rows else {
        "cases": len(cases),
        "executions": 0,
        "structured_output_success": 0,
        "measurement_evaluator": EVALUATOR_NAME,
        "runner_version": RUNNER_VERSION,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _base_row(case: dict[str, Any], repetition: int, started: float) -> dict[str, Any]:
    return {
        "id": case["id"],
        "language": case.get("language"),
        "group": case.get("group"),
        "category": case.get("category"),
        "critical": bool(case.get("critical")),
        "repetition": repetition,
        "question": case["question"],
        "expected": case["expected"],
        "scope": None,
        "selected_capabilities": [],
        "effective_capabilities": [],
        "selected_scope_success": None,
        "effective_scope_success": None,
        "scoped_catalog": None,
        "raw_understanding": None,
        "canonical_understanding": None,
        "canonical_fingerprint": "TECHNICAL_FAILURE",
        "compiled": None,
        "compiled_plan_core": None,
        "raw_differences": ["STRUCTURED_OUTPUT_NOT_AVAILABLE"],
        "canonical_differences": ["CANONICAL_NOT_AVAILABLE"],
        "compiler_differences": ["COMPILER_NOT_AVAILABLE"],
        "raw_success": False,
        "canonical_success": False,
        "compiler_success": False,
        "compiled_success": False,
        "structured_output_success": False,
        "normalization_error": None,
        "failure_cluster": "TECHNICAL",
        "technical_failure_stage": None,
        "technical_failure_class": None,
        "compiler_failure_class": None,
        "failure_details": None,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _model_failure_row(
    *, row: dict[str, Any], llm: OpenAIStructuredModel, stage: str
) -> dict[str, Any]:
    row["technical_failure_stage"] = stage
    row["technical_failure_class"] = llm.last_failure_class or "OPENAI_MODEL_ERROR"
    row["failure_cluster"] = "STRUCTURED_OUTPUT"
    row["failure_details"] = {
        "diagnostics": llm.last_response_diagnostics,
    }
    row["duration_ms"] = row.get("duration_ms")
    return row


def run(cases_path: Path, output_dir: Path, model: str, repetitions: int) -> None:
    cases = base.load_cases(cases_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    llm = OpenAIStructuredModel(
        api_key=os.environ["OPENAI_API_KEY"], model=model, max_retries=0
    )
    rows: list[dict[str, Any]] = []
    _write_checkpoint(
        output_dir=output_dir,
        rows=rows,
        cases_path=cases_path,
        cases=cases,
        repetitions=repetitions,
        model=model,
    )

    for repetition in range(1, repetitions + 1):
        for case in cases:
            started = time.perf_counter()
            row = _base_row(case, repetition, started)
            scope_instructions = (
                f"{phase3.SCOPE_PROMPT}\n\nQuestion:\n{case['question']}\n\n"
                f"Capabilities:\n{json.dumps(CAPABILITIES)}"
            )
            try:
                scope = llm.parse(
                    purpose="semantic-baseline-v1-capability-scope",
                    instructions=scope_instructions,
                    output_model=ScopeSelectionV243,
                )
            except OpenAIModelError:
                row = _model_failure_row(row=row, llm=llm, stage="CAPABILITY_SCOPE")
                row["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
                rows.append(row)
                _write_checkpoint(
                    output_dir=output_dir, rows=rows, cases_path=cases_path,
                    cases=cases, repetitions=repetitions, model=model
                )
                continue

            selected = capabilities(scope)
            catalog = scoped_catalog(selected)
            row["scope"] = scope.model_dump()
            row["selected_capabilities"] = selected
            row["scoped_catalog"] = catalog
            instructions = (
                f"{phase343.UNDERSTANDING_PROMPT_V343}\n\nQuestion:\n{case['question']}\n\n"
                f"Source date: {SOURCE_DATE.isoformat()}\nTimezone: {SOURCE_TIMEZONE}\n"
                f"Scoped catalog:\n{json.dumps(catalog)}"
            )
            try:
                raw = llm.parse(
                    purpose="semantic-baseline-v1-understanding",
                    instructions=instructions,
                    output_model=phase343.SemanticUnderstandingV343,
                )
            except OpenAIModelError:
                row = _model_failure_row(row=row, llm=llm, stage="SEMANTIC_UNDERSTANDING")
                row["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
                rows.append(row)
                _write_checkpoint(
                    output_dir=output_dir, rows=rows, cases_path=cases_path,
                    cases=cases, repetitions=repetitions, model=model
                )
                continue

            row["structured_output_success"] = True
            canonical = phase343_runner.canonicalize(raw)
            expected = case["expected"]
            raw_diff = base.understanding_differences(expected, raw)
            canonical_diff = base.understanding_differences(expected, canonical)
            raw_success = not raw_diff
            canonical_success = not canonical_diff
            effective = base._effective_capabilities(selected, canonical)
            selected_expected = base._expected_capabilities(case)

            row.update(
                {
                    "raw_understanding": raw.model_dump(),
                    "canonical_understanding": canonical.model_dump(),
                    "canonical_fingerprint": base._fingerprint(canonical),
                    "raw_differences": raw_diff,
                    "canonical_differences": canonical_diff,
                    "raw_success": raw_success,
                    "canonical_success": canonical_success,
                    "effective_capabilities": effective,
                    "selected_scope_success": (
                        None if selected_expected is None else set(selected) == selected_expected
                    ),
                    "effective_scope_success": (
                        None if selected_expected is None else set(effective) == selected_expected
                    ),
                }
            )

            try:
                compiled = phase343.compile_comparison(canonical)
            except ValidationError as exc:
                row["compiler_differences"] = ["COMPILER_SCHEMA_VALIDATION_ERROR"]
                row["compiler_failure_class"] = "COMPILER_SCHEMA_VALIDATION_ERROR"
                row["failure_cluster"] = "COMPILER"
                row["failure_details"] = {"pydantic_errors": exc.errors(include_url=False)}
                row["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
                rows.append(row)
                _write_checkpoint(
                    output_dir=output_dir, rows=rows, cases_path=cases_path,
                    cases=cases, repetitions=repetitions, model=model
                )
                continue

            compiler_diff = baseline_evaluator.compiler_differences(
                expected, canonical, compiled
            )
            compiler_success = not compiler_diff
            compiled_success = canonical_success and compiler_success
            normalization_error: str | None = None
            try:
                compiled_core = phase343_runner.compiled_plan_core(compiled)
            except (TypeError, ValueError, AttributeError) as exc:
                compiled_core = {"error": str(exc)}
                normalization_error = f"{type(exc).__name__}: {exc}"

            row.update(
                {
                    "compiled": compiled.model_dump(),
                    "compiled_plan_core": compiled_core,
                    "compiler_differences": compiler_diff,
                    "compiler_success": compiler_success,
                    "compiled_success": compiled_success,
                    "normalization_error": normalization_error,
                    "failure_cluster": base._failure_cluster(
                        canonical_diff or compiler_diff or raw_diff
                    ),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
            rows.append(row)
            _write_checkpoint(
                output_dir=output_dir,
                rows=rows,
                cases_path=cases_path,
                cases=cases,
                repetitions=repetitions,
                model=model,
            )

    metrics = _aggregate(rows, cases)
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
