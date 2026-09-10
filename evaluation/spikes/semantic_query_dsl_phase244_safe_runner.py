"""Robust evaluation runner for Semantic Query Intent Phase 2.4.4.

This file intentionally does not change Phase 2.4.4 prompts, schemas, dataset,
or semantic rules. It only makes evaluation instrumentation resilient:
- scope and raw intent are retained before normalization;
- incomplete relative scopes are classified instead of dereferenced;
- normalization/rendering failures do not abort the case artifact;
- the batch continues after post-processing failures.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import (
    CAPABILITIES,
    SOURCE_DATE,
    SOURCE_TIMEZONE,
    TYPE_CAPABILITIES,
    scoped_catalog,
)
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import (
    INTENT_PROMPT_V244,
    SCOPE_PROMPT_V244,
    SemanticQueryIntentV244,
    capabilities,
    derived_answerability,
    derived_entities,
    eloquent_like,
    normalize_time_scope,
    result_mode,
    scope_shape_errors,
    semantic_differences,
    validate_operations,
)

ROOT = Path(__file__).resolve().parents[2]


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _normalization_preflight(intent: SemanticQueryIntentV244) -> list[str]:
    """Return structural errors that make normalization unsafe.

    The semantic contract remains Phase 2.4.4's contract. This function only
    prevents the evaluator from dereferencing missing relative bounds.
    """
    errors = scope_shape_errors(intent.time_scope)
    scope = intent.time_scope
    if scope is None:
        return errors

    if scope.kind == "RELATIVE_RANGE":
        if scope.relative_start is None and (
            "TIME_SCOPE_MISSING_FIELD:RELATIVE_RANGE:relative_start" not in errors
        ):
            errors.append("TIME_SCOPE_MISSING_FIELD:RELATIVE_RANGE:relative_start")
        if scope.relative_end is None and (
            "TIME_SCOPE_MISSING_FIELD:RELATIVE_RANGE:relative_end" not in errors
        ):
            errors.append("TIME_SCOPE_MISSING_FIELD:RELATIVE_RANGE:relative_end")

    return sorted(set(errors))


def _safe_normalize(
    intent: SemanticQueryIntentV244,
) -> tuple[dict[str, Any] | None, str | None]:
    preflight = _normalization_preflight(intent)
    missing = [error for error in preflight if "TIME_SCOPE_MISSING_FIELD" in error]
    if missing:
        return None, ";".join(missing)

    try:
        return normalize_time_scope(intent.time_scope), None
    except Exception as exc:  # instrumentation must retain the raw intent
        return None, f"{type(exc).__name__}: {str(exc)[:240]}"


def _non_normalizing_differences(
    case: dict[str, Any],
    cats: list[str],
    intent: SemanticQueryIntentV244,
) -> list[str]:
    """Evaluate Phase 2.4.4 semantics that do not require normalization."""
    expected = case["expected"]
    differences: list[str] = []

    if sorted(cats) != sorted(expected.get("capabilities", [])):
        differences.append("CAPABILITY_SCOPE_MISMATCH")
    if result_mode(intent) != expected.get("result_mode", result_mode(intent)):
        differences.append("RESULT_MODE_MISMATCH")
    if sorted(intent.result_fields) != sorted(expected.get("result_fields", [])):
        differences.append("RESULT_FIELDS_MISMATCH")
    if sorted((item.field, item.aggregation) for item in intent.measures) != sorted(
        (item["field"], item["aggregation"])
        for item in expected.get("measures", [])
    ):
        differences.append("MEASURE_MISMATCH")
    if sorted(
        (item.field, item.derivation, item.direction) for item in intent.order_by
    ) != sorted(
        (item["field"], item.get("derivation"), item["direction"])
        for item in expected.get("order_by", [])
    ):
        differences.append("ORDER_BY_MISMATCH")
    if intent.limit != expected.get("limit"):
        differences.append("LIMIT_MISMATCH")
    if sorted((item.field, item.derivation) for item in intent.group_by) != sorted(
        (item["field"], item.get("derivation"))
        for item in expected.get("group_by", [])
    ):
        differences.append("GROUP_BY_MISMATCH")
    if derived_answerability(intent) != expected.get(
        "answerability", "UNDERSTOOD_AND_EXECUTABLE"
    ):
        differences.append("ANSWERABILITY_MISMATCH")
    if expected.get("relative_required") and (
        not intent.time_scope or intent.time_scope.kind != "RELATIVE_RANGE"
    ):
        differences.append("RELATIVE_INTENT_NOT_SYMBOLIC")

    actual_derived = sorted(
        (
            item.field,
            item.derivation,
            item.operator,
            str(item.value),
            tuple(map(str, item.values)),
        )
        for item in intent.derived_calendar_filters
    )
    expected_derived = sorted(
        (
            item["field"],
            item["derivation"],
            item["operator"],
            str(item.get("value")),
            tuple(map(str, item.get("values", []))),
        )
        for item in expected.get("derived_conditions", [])
    )
    if actual_derived != expected_derived:
        differences.append("DERIVED_CONDITION_MISMATCH")

    actual_calendar = sorted(
        (item.field, item.predicate) for item in intent.calendar_predicate_filters
    )
    expected_calendar = sorted(
        (item["field"], item["predicate"])
        for item in expected.get("calendar_conditions", [])
    )
    if actual_calendar != expected_calendar:
        differences.append("CALENDAR_CONDITION_MISMATCH")

    differences.extend(scope_shape_errors(intent.time_scope))
    differences.extend(validate_operations(cats, intent))
    return sorted(set(differences))


def _evaluate_differences(
    case: dict[str, Any],
    cats: list[str],
    intent: SemanticQueryIntentV244,
    normalized: dict[str, Any] | None,
    normalization_error: str | None,
) -> list[str]:
    if normalization_error is None:
        try:
            return semantic_differences(case, cats, intent)
        except Exception as exc:
            differences = _non_normalizing_differences(case, cats, intent)
            differences.append(f"EVALUATOR_POSTPROCESS_ERROR:{type(exc).__name__}")
            return sorted(set(differences))

    differences = _non_normalizing_differences(case, cats, intent)
    differences.append("NORMALIZATION_ERROR")

    # If a range was expected but normalization could not produce one, retain
    # the semantic mismatch rather than turning the whole response into a
    # model/transport failure.
    if case["expected"].get("normalized_ranges") and normalized is None:
        differences.append("RANGE_MISMATCH")
    return sorted(set(differences))


def _safe_eloquent(
    intent: SemanticQueryIntentV244,
    normalization_error: str | None,
) -> tuple[str | None, str | None]:
    if normalization_error is not None:
        return None, "skipped because temporal normalization is invalid"
    try:
        return eloquent_like(intent), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:240]}"


def run(
    cases: list[dict[str, Any]],
    repetitions: int,
    output: Path,
    model_name: str,
) -> None:
    model = OpenAIStructuredModel(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model=model_name,
        timeout_seconds=60,
        max_retries=0,
        max_output_tokens=4096,
    )
    output.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    descriptions = {key: value["description"] for key, value in CAPABILITIES.items()}

    for case in cases:
        for repetition in range(1, repetitions + 1):
            started = time.monotonic()
            row: dict[str, Any] = {
                "attempt_id": str(uuid.uuid4()),
                "question_id": case["id"],
                "question": case["question"],
                "repetition": repetition,
            }

            try:
                scope = model.parse(
                    purpose=SCOPE_PROMPT_V244,
                    instructions=(
                        "Capability catalog: "
                        + json.dumps(descriptions, ensure_ascii=False)
                        + "\nQuestion: "
                        + case["question"]
                    ),
                    output_model=ScopeSelectionV243,
                )
                cats = capabilities(scope)
                catalog = scoped_catalog(cats)

                # Scope is retained before the second model call/postprocessing.
                row.update(
                    {
                        "scope": scope.model_dump(mode="json"),
                        "capabilities": cats,
                        "scoped_fields": sorted(catalog["fields"]),
                    }
                )

                intent = model.parse(
                    purpose=INTENT_PROMPT_V244,
                    instructions=(
                        "Provider temporal context: "
                        + json.dumps(
                            {
                                "source_current_date": SOURCE_DATE.isoformat(),
                                "source_timezone": SOURCE_TIMEZONE,
                            }
                        )
                        + "\nType capabilities: "
                        + json.dumps(TYPE_CAPABILITIES)
                        + "\nScoped conceptual fields: "
                        + json.dumps(catalog["fields"], ensure_ascii=False)
                        + "\nDefault result fields are platform metadata; "
                        "do not copy them unless explicitly named: "
                        + json.dumps(
                            catalog["default_result_fields"], ensure_ascii=False
                        )
                        + "\nQuestion: "
                        + case["question"]
                    ),
                    output_model=SemanticQueryIntentV244,
                )

                # Raw intent is retained before normalization/evaluation/rendering.
                row.update(
                    {
                        "structured_output_success": True,
                        "raw_intent": intent.model_dump(mode="json"),
                        "derived_result_mode": result_mode(intent),
                        "derived_answerability": derived_answerability(intent),
                        "derived_entities": derived_entities(intent),
                        "time_scope_shape_errors": scope_shape_errors(
                            intent.time_scope
                        ),
                        "field_operation_errors": validate_operations(cats, intent),
                    }
                )

                normalized, normalization_error = _safe_normalize(intent)
                row["normalized_time_scope"] = normalized
                row["normalization_error"] = normalization_error

                differences = _evaluate_differences(
                    case,
                    cats,
                    intent,
                    normalized,
                    normalization_error,
                )
                rendered, render_error = _safe_eloquent(
                    intent, normalization_error
                )
                row.update(
                    {
                        "eloquent_like": rendered,
                        "render_error": render_error,
                        "semantic_success": not differences,
                        "semantic_differences": differences,
                    }
                )
            except Exception as exc:
                # Only failures before a structured intent exists remain model/
                # transport failures. Any data already captured in row survives.
                row.update(
                    {
                        "structured_output_success": bool(row.get("raw_intent")),
                        "semantic_success": False,
                        "semantic_differences": [
                            model.last_failure_class or "MODEL_OR_TRANSPORT_FAILURE"
                        ],
                        "exception_class": type(exc).__name__,
                        "error": str(exc)[:300],
                    }
                )

            row["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
            rows.append(row)
            print(
                json.dumps(
                    {
                        key: row.get(key)
                        for key in (
                            "question_id",
                            "structured_output_success",
                            "semantic_success",
                            "semantic_differences",
                            "normalization_error",
                            "latency_ms",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    (output / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    failures = Counter(
        difference
        for row in rows
        for difference in row.get("semantic_differences", [])
    )
    metrics = {
        "total": len(rows),
        "structured_output_success_rate": sum(
            bool(row.get("structured_output_success")) for row in rows
        )
        / len(rows),
        "semantic_success_rate": sum(
            bool(row.get("semantic_success")) for row in rows
        )
        / len(rows),
        "normalization_error_rate": sum(
            bool(row.get("normalization_error")) for row in rows
        )
        / len(rows),
        "failure_distribution": dict(failures),
    }
    (output / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": datetime.utcnow().isoformat() + "Z",
                "phase": "2.4.4-safe-runner",
                "semantic_contract": "2.4.4-unchanged",
                "model": model_name,
                "source_current_date": SOURCE_DATE.isoformat(),
                "source_timezone": SOURCE_TIMEZONE,
                "cases": len(cases),
                "repetitions": repetitions,
                "mcp_executed": False,
                "sql_executed": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=ROOT / "evaluation/spikes/semantic_query_dsl_phase244_cases.jsonl",
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )
    args = parser.parse_args()
    run(load_cases(args.cases), args.repetitions, args.output, args.model)


if __name__ == "__main__":
    main()
