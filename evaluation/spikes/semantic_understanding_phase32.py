"""Phase 3.2 spike: semantic composition hardening over Phase 3.1.

Inspection-only experiment. It keeps the Phase 3 architecture and dataset, adds:
- stricter semantic-composition guidance for temporal scope vs calendar filters;
- deterministic capability closure from canonical field references;
- independent selected-scope vs effective-scope metrics;
- compiler attribution only after effective scope + canonical understanding are valid.

No MCP, SQL, executable Eloquent, physical schema, case-id routing, or natural-language
logic is used by deterministic post-processing.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import semantic_understanding_phase3 as phase3
import semantic_understanding_phase31 as phase31
from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import CAPABILITIES, SOURCE_DATE, SOURCE_TIMEZONE, scoped_catalog
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import capabilities

ROOT = Path(__file__).resolve().parents[2]

UNDERSTANDING_PROMPT_V32 = phase3.UNDERSTANDING_PROMPT + """

SEMANTIC COMPOSITION INVARIANTS
- Temporal meaning defines the containing time domain. Calendar conditions filter positions inside that domain.
  Never replace an explicitly stated containing year/month/range merely because a weekday/day-of-month/calendar
  predicate is also present.
- A calendar recurrence/filter is not a breakdown. Add a breakdown only when the user explicitly asks to split,
  group, compare, or report results by that dimension.
- Do not add requested_fields merely because a field participates in measure, filter, grouping, ordering, or time.
- Ordering a DATE field directly uses derivation=null unless the user explicitly asks to sort by a derived calendar
  component such as year/month/weekday.
- PREVIOUS requires a resolvable unit. If the request establishes only 'previous period' and no period unit is
  explicitly or contextually established, report an ambiguity instead of choosing month/year/payroll period.
- For relative reference frames (CURRENT_MONTH, CURRENT_YEAR, CURRENT_DATE), do not materialize year/month/months
  values. Preserve only the semantic relation needed by deterministic compilation.
- For an explicit containing year combined with a calendar condition (for example a weekday, day-of-month, or
  calendar predicate), temporal meaning remains EXPLICIT + EXACT + YEAR for that year; the calendar condition is
  represented separately.
"""


def referenced_fields(u: phase3.SemanticUnderstanding) -> set[str]:
    """Collect qualified conceptual field references without reading natural language."""
    fields = set(u.requested_fields)
    if u.measure:
        fields.add(u.measure.field)
    for breakdown in u.breakdowns:
        fields.add(breakdown.field)
    for condition in u.calendar_conditions:
        fields.add(condition.field)
    for ordering in u.order_by:
        fields.add(ordering.field)
    return {field for field in fields if field}


def field_capability_index() -> dict[str, str]:
    """Build field -> capability ownership from conceptual discovery metadata."""
    index: dict[str, str] = {}
    for capability, metadata in CAPABILITIES.items():
        for field in metadata.get("fields", {}):
            index[field] = capability
    return index


def derive_required_capabilities(u: phase3.SemanticUnderstanding) -> list[str]:
    """Derive capability closure mechanically from canonical field references."""
    index = field_capability_index()
    return sorted({index[field] for field in referenced_fields(u) if field in index})


def effective_capabilities(
    selected: list[str],
    canonical: phase3.SemanticUnderstanding,
) -> list[str]:
    """Union selected capabilities with deterministic ownership of referenced fields."""
    return sorted(set(selected) | set(derive_required_capabilities(canonical)))


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
                purpose="phase32-capability-scope",
                instructions=scope_instructions,
                output_model=ScopeSelectionV243,
            )
            selected = capabilities(scope)
            selected_catalog = scoped_catalog(selected)
            selected_scope_diff = scope_differences(case, selected)
            row["scope"] = scope.model_dump()
            row["selected_capabilities"] = selected
            row["selected_scope_differences"] = selected_scope_diff
            row["selected_scope_success"] = not selected_scope_diff
            row["selected_scoped_catalog"] = selected_catalog

            understanding_instructions = (
                f"{UNDERSTANDING_PROMPT_V32}\n\nQuestion:\n{case['question']}\n\n"
                f"Source date: {SOURCE_DATE.isoformat()}\nTimezone: {SOURCE_TIMEZONE}\n"
                f"Scoped catalog:\n{json.dumps(selected_catalog)}"
            )
            raw = llm.parse(
                purpose="phase32-semantic-understanding",
                instructions=understanding_instructions,
                output_model=phase3.SemanticUnderstanding,
            )
            row["raw_understanding"] = raw.model_dump()
            raw_diff = strict_understanding_differences(case, raw)
            row["raw_understanding_differences"] = raw_diff
            row["raw_understanding_success"] = not raw_diff

            canonical = phase31.canonicalize_understanding(raw)
            row["canonical_understanding"] = canonical.model_dump()
            row["canonicalization_changed"] = canonical.model_dump() != raw.model_dump()
            canonical_diff = strict_understanding_differences(case, canonical)
            row["canonical_understanding_differences"] = canonical_diff
            row["canonical_understanding_success"] = not canonical_diff

            derived_caps = derive_required_capabilities(canonical)
            effective = effective_capabilities(selected, canonical)
            effective_scope_diff = scope_differences(case, effective)
            row["reference_fields"] = sorted(referenced_fields(canonical))
            row["derived_required_capabilities"] = derived_caps
            row["effective_capabilities"] = effective
            row["effective_scope_differences"] = effective_scope_diff
            row["effective_scope_success"] = not effective_scope_diff
            row["effective_scoped_catalog"] = scoped_catalog(effective)

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
                effective,
                intent,
                normalized,
                normalization_error,
            )
            row["compiled_differences"] = qdiff
            row["compiled_semantic_success"] = not qdiff
            row["eloquent_like"] = (
                None if normalization_error else phase3.eloquent_like(intent, normalized)
            )

            if canonical_diff:
                first_layer = "UNDERSTANDING_FAILURE"
            elif effective_scope_diff:
                first_layer = "EFFECTIVE_SCOPE_FAILURE"
            elif qdiff:
                first_layer = "COMPILER_OR_NORMALIZATION_FAILURE"
            elif selected_scope_diff:
                first_layer = "SELECTED_SCOPE_RECOVERED"
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
        if row.get("effective_scope_success")
        and row.get("canonical_understanding_success")
    ]
    compiler_success_on_valid_input = sum(
        bool(row.get("compiled_semantic_success")) for row in valid_compiler_inputs
    )

    selected_scope_recovered = sum(
        bool(not row.get("selected_scope_success") and row.get("effective_scope_success"))
        for row in rows
    )

    metrics = {
        "phase": "3.2-semantic-composition",
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
        "selected_scope_success": sum(
            bool(r.get("selected_scope_success")) for r in rows
        ),
        "effective_scope_success": sum(
            bool(r.get("effective_scope_success")) for r in rows
        ),
        "selected_scope_recovered": selected_scope_recovered,
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
        "phase": "3.2-semantic-composition",
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
            "compiler_success_given_valid_input",
        ],
        "diagnostic_metrics": [
            "raw_understanding_success",
            "selected_scope_success",
            "effective_scope_success",
        ],
        "mcp_execution": False,
        "sql_execution": False,
        "canonicalizer_may_infer_missing_intent": False,
        "effective_scope_derived_from_field_ownership": True,
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
