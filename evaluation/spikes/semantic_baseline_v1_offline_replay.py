"""Offline replay for the established Semantic Baseline v1.

The replay consumes persisted Structured Outputs and never calls OpenAI. It has
two purposes:

1. recompute corrected v2 aggregate reporting from the frozen 240 rows;
2. run a strictly mechanical experiment that removes a top-level temporal value
   only when it is structurally equivalent to ``comparison.left`` and then
   measures the effect with the frozen evaluator.

The experiment does not modify the canonicalizer or baseline artifacts.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

import semantic_baseline_v1_reporting_v2 as reporting_v2
import semantic_baseline_v1_runner_aligned as baseline_runner
import semantic_comparison_baseline_evaluator_v1 as baseline_evaluator
import semantic_comparison_canonical_redundancy as redundancy
import semantic_understanding_phase343 as phase343

REPLAY_VERSION = "semantic-baseline-v1-offline-replay-v1"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _percent(num: int, den: int) -> float | None:
    return None if den == 0 else round(num * 100.0 / den, 2)


def _compile_and_measure(
    *, expected: dict[str, Any], canonical: phase343.SemanticUnderstandingV343
) -> dict[str, Any]:
    canonical_differences = baseline_runner.understanding_differences(
        expected, canonical
    )
    try:
        compiled = phase343.compile_comparison(canonical)
    except ValidationError as exc:
        return {
            "canonical_differences": canonical_differences,
            "canonical_success": not canonical_differences,
            "compiler_success": False,
            "compiled_success": False,
            "compiler_differences": ["COMPILER_SCHEMA_VALIDATION_ERROR"],
            "compiler_validation_errors": exc.errors(),
            "compiled": None,
        }

    compiler_differences = baseline_evaluator.compiler_differences(
        expected, canonical, compiled
    )
    return {
        "canonical_differences": canonical_differences,
        "canonical_success": not canonical_differences,
        "compiler_success": not compiler_differences,
        "compiled_success": not canonical_differences and not compiler_differences,
        "compiler_differences": compiler_differences,
        "compiler_validation_errors": [],
        "compiled": compiled.model_dump(mode="json"),
    }


def replay(
    *, rows: list[dict[str, Any]], cases: list[dict[str, Any]]
) -> dict[str, Any]:
    corrected_metrics = reporting_v2.aggregate(rows, cases)

    classifications: Counter[str] = Counter()
    comparison_rows = 0
    comparison_with_top_level_temporal = 0
    removable_rows = 0
    plan_changed_after_removal = 0
    recovered_canonical = 0
    recovered_compiled = 0
    current_canonical_success = 0
    current_compiled_success = 0
    experimental_canonical_success = 0
    experimental_compiled_success = 0
    by_case: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "executions": 0,
            "comparison_executions": 0,
            "with_top_level_temporal": 0,
            "removable": 0,
            "current_canonical_success": 0,
            "experimental_canonical_success": 0,
            "current_compiled_success": 0,
            "experimental_compiled_success": 0,
            "redundancy_classes": Counter(),
        }
    )
    details: list[dict[str, Any]] = []

    for row in rows:
        case_id = str(row["id"])
        case_summary = by_case[case_id]
        case_summary["executions"] += 1

        canonical_payload = row.get("canonical_understanding")
        if canonical_payload is None:
            continue
        canonical = phase343.SemanticUnderstandingV343.model_validate(canonical_payload)
        expected = row["expected"]
        current = _compile_and_measure(expected=expected, canonical=canonical)
        current_canonical_success += int(current["canonical_success"])
        current_compiled_success += int(current["compiled_success"])
        case_summary["current_canonical_success"] += int(current["canonical_success"])
        case_summary["current_compiled_success"] += int(current["compiled_success"])

        is_comparison = row.get("group") == "F"
        if is_comparison:
            comparison_rows += 1
            case_summary["comparison_executions"] += 1

        classification = redundancy.classify_top_level_temporal_redundancy(canonical)
        classifications[classification] += 1
        case_summary["redundancy_classes"][classification] += 1

        if canonical.comparison is not None and canonical.temporal is not None:
            comparison_with_top_level_temporal += 1
            case_summary["with_top_level_temporal"] += 1

        experimental = current
        removable = classification in {
            "STRICT_EQUIVALENT",
            "EQUIVALENT_NON_RELATIVE_ANCHOR_METADATA",
        }
        plan_unchanged = None
        if removable:
            removable_rows += 1
            case_summary["removable"] += 1
            stripped = redundancy.strip_redundant_top_level_temporal(canonical)
            before_compiled = phase343.compile_comparison(canonical)
            after_compiled = phase343.compile_comparison(stripped)
            plan_unchanged = (
                before_compiled.model_dump(mode="json")
                == after_compiled.model_dump(mode="json")
            )
            if not plan_unchanged:
                plan_changed_after_removal += 1
            experimental = _compile_and_measure(expected=expected, canonical=stripped)

        experimental_canonical_success += int(experimental["canonical_success"])
        experimental_compiled_success += int(experimental["compiled_success"])
        case_summary["experimental_canonical_success"] += int(
            experimental["canonical_success"]
        )
        case_summary["experimental_compiled_success"] += int(
            experimental["compiled_success"]
        )

        if not current["canonical_success"] and experimental["canonical_success"]:
            recovered_canonical += 1
        if not current["compiled_success"] and experimental["compiled_success"]:
            recovered_compiled += 1

        if removable or (is_comparison and canonical.temporal is not None):
            details.append(
                {
                    "id": case_id,
                    "repetition": row.get("repetition"),
                    "classification": classification,
                    "plan_unchanged": plan_unchanged,
                    "current_canonical_differences": current[
                        "canonical_differences"
                    ],
                    "experimental_canonical_differences": experimental[
                        "canonical_differences"
                    ],
                    "current_compiler_differences": current[
                        "compiler_differences"
                    ],
                    "experimental_compiler_differences": experimental[
                        "compiler_differences"
                    ],
                    "current_compiled_success": current["compiled_success"],
                    "experimental_compiled_success": experimental[
                        "compiled_success"
                    ],
                }
            )

    if plan_changed_after_removal:
        raise AssertionError(
            "A mechanically removable top-level temporal changed ComparisonPlan"
        )

    serializable_by_case: dict[str, Any] = {}
    for case_id, summary in sorted(by_case.items()):
        serializable_by_case[case_id] = {
            **summary,
            "redundancy_classes": dict(summary["redundancy_classes"]),
        }

    total = len(rows)
    return {
        "replay_version": REPLAY_VERSION,
        "executions": total,
        "corrected_reporting": corrected_metrics,
        "current_replayed": {
            "canonical_success": current_canonical_success,
            "canonical_success_pct": _percent(current_canonical_success, total),
            "compiled_success": current_compiled_success,
            "compiled_success_pct": _percent(current_compiled_success, total),
        },
        "redundancy_experiment": {
            "comparison_executions": comparison_rows,
            "comparison_with_top_level_temporal": comparison_with_top_level_temporal,
            "redundancy_classes": dict(classifications),
            "mechanically_removable_executions": removable_rows,
            "comparison_plan_changed_after_removal": plan_changed_after_removal,
            "canonical_success_after_experiment": experimental_canonical_success,
            "canonical_success_after_experiment_pct": _percent(
                experimental_canonical_success, total
            ),
            "compiled_success_after_experiment": experimental_compiled_success,
            "compiled_success_after_experiment_pct": _percent(
                experimental_compiled_success, total
            ),
            "canonical_executions_recovered": recovered_canonical,
            "compiled_executions_recovered": recovered_compiled,
        },
        "by_case": serializable_by_case,
        "details": details,
    }


def assert_offline_replay_contract() -> None:
    redundancy.assert_redundancy_contract()
    reporting_v2.assert_reporting_contract()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    assert_offline_replay_contract()
    cases = baseline_runner.load_cases(args.cases)
    rows = _load_jsonl(args.raw)
    result = replay(rows=rows, cases=cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
