"""Phase 3.1 spike: canonicalize SemanticUnderstanding before deterministic compilation.

Inspection-only experiment. It reuses the Phase 3 prompts, schema, dataset semantics,
compiler, query evaluator and renderer. The new layer may remove mechanically redundant
or incompatible SemanticUnderstanding fields, but it must never infer missing intent.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import semantic_understanding_phase3 as phase3
from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import CAPABILITIES, SOURCE_DATE, SOURCE_TIMEZONE, scoped_catalog
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import capabilities

ROOT = Path(__file__).resolve().parents[2]


def canonicalize_temporal(
    temporal: phase3.TemporalMeaning | None,
) -> phase3.TemporalMeaning | None:
    """Remove only fields made redundant/incompatible by the semantic temporal type."""
    if temporal is None:
        return None

    data = temporal.model_dump()
    frame = temporal.reference_frame
    relation = temporal.relation
    unit = temporal.unit

    if frame == "EXPLICIT" and relation == "EXACT":
        data["count"] = None
        data["through_current_date"] = False
        data["start_date"] = None
        data["end_date"] = None
        if unit == "YEAR":
            data["month"] = None
            data["months"] = []
        elif unit == "MONTH":
            if temporal.month is not None:
                data["months"] = []
            elif temporal.months:
                data["month"] = None
        return phase3.TemporalMeaning.model_validate(data)

    if frame == "CURRENT_MONTH":
        data["year"] = None
        data["month"] = None
        data["months"] = []
        data["start_date"] = None
        data["end_date"] = None
        data["through_current_date"] = False
        if relation in {"EXACT", "PREVIOUS"}:
            data["count"] = None
        return phase3.TemporalMeaning.model_validate(data)

    if frame == "CURRENT_YEAR" and relation == "FROM_START":
        data["year"] = None
        data["month"] = None
        data["months"] = []
        data["count"] = None
        data["start_date"] = None
        data["end_date"] = None
        return phase3.TemporalMeaning.model_validate(data)

    if frame == "CURRENT_DATE" and relation == "LAST_N":
        data["year"] = None
        data["month"] = None
        data["months"] = []
        data["start_date"] = None
        data["end_date"] = None
        return phase3.TemporalMeaning.model_validate(data)

    return temporal.model_copy(deep=True)


def canonicalize_understanding(
    understanding: phase3.SemanticUnderstanding,
) -> phase3.SemanticUnderstanding:
    """Canonicalize structural noise without inventing semantic intent."""
    canonical = understanding.model_copy(deep=True)

    if canonical.ambiguities or canonical.unsupported_reasons:
        canonical.requested_fields = []
        canonical.measure = None
        canonical.temporal = None
        canonical.breakdowns = []
        canonical.calendar_conditions = []
        canonical.order_by = []
        canonical.limit = None
        return canonical

    canonical.temporal = canonicalize_temporal(canonical.temporal)
    return canonical


def strict_understanding_differences(
    case: dict[str, Any],
    understanding: phase3.SemanticUnderstanding,
) -> list[str]:
    differences = phase3.understanding_differences(case, understanding)
    expected_order = case["understanding"].get("order_by", [])
    actual_order = [item.model_dump(exclude_none=True) for item in understanding.order_by]
    if actual_order != expected_order and "UNDERSTANDING_ORDER" not in differences:
        differences.append("UNDERSTANDING_ORDER")
    return differences


def scope_differences(case: dict[str, Any], selected: list[str]) -> list[str]:
    expected = sorted(case["expected"].get("capabilities", []))
    return [] if sorted(selected) == expected else ["CAPABILITY_SCOPE_MISMATCH"]


def run(case_path: Path, output_dir: Path, model: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = phase3.load_cases(case_path)
    llm = OpenAIStructuredModel(
        api_key=os.environ["OPENAI_API_KEY"],
        model=model,
        max_retries=0,
    )
    rows: list[dict[str, Any]] = []

    for case in cases:
        row: dict[str, Any] = {"id": case["id"], "question": case["question"]}
        started = time.perf_counter()
        try:
            scope_instructions = (
                f"{phase3.SCOPE_PROMPT}\n\nQuestion:\n{case['question']}\n\n"
                f"Capabilities:\n{json.dumps(CAPABILITIES)}"
            )
            scope = llm.parse(
                purpose="phase31-capability-scope",
                instructions=scope_instructions,
                output_model=ScopeSelectionV243,
            )
            cats = capabilities(scope)
            catalog = scoped_catalog(cats)
            sdiff = scope_differences(case, cats)
            row["scope"] = scope.model_dump()
            row["capabilities"] = cats
            row["scope_differences"] = sdiff
            row["scope_success"] = not sdiff
            row["scoped_catalog"] = catalog

            understanding_instructions = (
                f"{phase3.UNDERSTANDING_PROMPT}\n\nQuestion:\n{case['question']}\n\n"
                f"Source date: {SOURCE_DATE.isoformat()}\nTimezone: {SOURCE_TIMEZONE}\n"
                f"Scoped catalog:\n{json.dumps(catalog)}"
            )
            raw = llm.parse(
                purpose="phase31-semantic-understanding",
                instructions=understanding_instructions,
                output_model=phase3.SemanticUnderstanding,
            )
            row["raw_understanding"] = raw.model_dump()
            raw_diff = strict_understanding_differences(case, raw)
            row["raw_understanding_differences"] = raw_diff
            row["raw_understanding_success"] = not raw_diff

            canonical = canonicalize_understanding(raw)
            row["canonical_understanding"] = canonical.model_dump()
            row["canonicalization_changed"] = canonical.model_dump() != raw.model_dump()
            canonical_diff = strict_understanding_differences(case, canonical)
            row["canonical_understanding_differences"] = canonical_diff
            row["canonical_understanding_success"] = not canonical_diff

            intent = phase3.compile_understanding(canonical)
            row["compiled_intent"] = intent.model_dump()
            row["derived_answerability"] = phase3.derived_answerability(intent)
            row["derived_result_mode"] = phase3.result_mode(intent)
            row["derived_entities"] = phase3.derived_entities(intent)

            normalized = None
            normalization_error = None
            try:
                normalized = phase3.normalize_time_scope(intent.time_scope)
            except Exception as exc:  # diagnostic artifact, not production path
                normalization_error = f"{type(exc).__name__}: {exc}"
            row["normalized_time_scope"] = normalized
            row["normalization_error"] = normalization_error
            qdiff = phase3.semantic_differences(
                case,
                cats,
                intent,
                normalized,
                normalization_error,
            )
            row["compiled_differences"] = qdiff
            row["compiled_semantic_success"] = not qdiff
            row["eloquent_like"] = (
                None if normalization_error else phase3.eloquent_like(intent, normalized)
            )

            if sdiff:
                first_layer = "SCOPE_FAILURE"
            elif canonical_diff:
                first_layer = "UNDERSTANDING_FAILURE"
            elif qdiff:
                first_layer = "COMPILER_OR_NORMALIZATION_FAILURE"
            else:
                first_layer = "FULL_SUCCESS"
            row["first_failing_layer"] = first_layer
        except Exception as exc:  # preserve batch diagnostics
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["raw_understanding_success"] = False
            row["canonical_understanding_success"] = False
            row["compiled_semantic_success"] = False
            row["first_failing_layer"] = "RUNNER_OR_MODEL_FAILURE"

        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)

    valid_compiler_inputs = [
        row
        for row in rows
        if row.get("scope_success") and row.get("canonical_understanding_success")
    ]
    compiler_success_on_valid_input = sum(
        bool(row.get("compiled_semantic_success")) for row in valid_compiler_inputs
    )

    metrics = {
        "phase": "3.1-semantic-understanding-canonicalizer",
        "cases": len(rows),
        "raw_understanding_success": sum(
            bool(r.get("raw_understanding_success")) for r in rows
        ),
        "canonical_understanding_success": sum(
            bool(r.get("canonical_understanding_success")) for r in rows
        ),
        "compiled_semantic_success": sum(
            bool(r.get("compiled_semantic_success")) for r in rows
        ),
        "scope_success": sum(bool(r.get("scope_success")) for r in rows),
        "compiler_valid_input_cases": len(valid_compiler_inputs),
        "compiler_success_given_valid_input": compiler_success_on_valid_input,
        "raw_failure_distribution": dict(
            Counter(
                d for r in rows for d in r.get("raw_understanding_differences", [])
            )
        ),
        "canonical_failure_distribution": dict(
            Counter(
                d
                for r in rows
                for d in r.get("canonical_understanding_differences", [])
            )
        ),
        "compiled_failure_distribution": dict(
            Counter(d for r in rows for d in r.get("compiled_differences", []))
        ),
        "first_failing_layer_distribution": dict(
            Counter(r.get("first_failing_layer") for r in rows)
        ),
    }
    manifest = {
        "phase": "3.1-semantic-understanding-canonicalizer",
        "run_id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "model": model,
        "source_current_date": SOURCE_DATE.isoformat(),
        "source_timezone": SOURCE_TIMEZONE,
        "retries": 0,
        "dataset": str(case_path),
        "primary_gates": [
            "canonical_understanding_success",
            "compiled_semantic_success",
        ],
        "diagnostic_metric": "raw_understanding_success",
        "mcp_execution": False,
        "sql_execution": False,
        "canonicalizer_may_infer_missing_intent": False,
    }

    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(r, default=str) for r in rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        default=str(ROOT / "evaluation/spikes/semantic_understanding_phase3_cases.jsonl"),
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()
    run(Path(args.cases), Path(args.output_dir), args.model)


if __name__ == "__main__":
    main()
