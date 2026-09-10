"""Corrected reporting for Semantic Baseline v1.

The formal baseline has six fixed groups (A-F), where group F is the comparison
suite. Some non-executable comparison cases intentionally have
``expected.comparison == null``. Therefore simple/comparison reporting must use
the dataset group contract, not presence of an executable comparison object.

This module does not change semantic evaluation. It only corrects aggregate
reporting and can recompute metrics from an existing raw_responses.jsonl without
calling OpenAI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import semantic_baseline_v1_runner_resilient as resilient

REPORTING_VERSION = "semantic-baseline-v1-reporting-v2"
COMPARISON_GROUP = "F"


def _percent(num: int, den: int) -> float | None:
    return None if den == 0 else round(num * 100.0 / den, 2)


def _is_comparison_row(row: dict[str, Any]) -> bool:
    """Classify by the frozen baseline dataset contract, not executable shape."""
    return row.get("group") == COMPARISON_GROUP


def correct_partition_metrics(
    rows: list[dict[str, Any]], metrics: dict[str, Any]
) -> dict[str, Any]:
    """Correct simple/comparison aggregates and enforce partition invariants."""
    comparison_rows = [row for row in rows if _is_comparison_row(row)]
    simple_rows = [row for row in rows if not _is_comparison_row(row)]

    if len(simple_rows) + len(comparison_rows) != len(rows):
        raise AssertionError("simple/comparison rows must partition all executions")

    simple_success = sum(bool(row.get("compiled_success")) for row in simple_rows)
    comparison_success = sum(
        bool(row.get("compiled_success")) for row in comparison_rows
    )
    global_success = sum(bool(row.get("compiled_success")) for row in rows)

    if simple_success + comparison_success != global_success:
        raise AssertionError(
            "simple + comparison compiled successes must equal global compiled success"
        )

    corrected = dict(metrics)
    corrected.update(
        {
            "simple_executions": len(simple_rows),
            "simple_compiled_success": simple_success,
            "simple_compiled_success_pct": _percent(simple_success, len(simple_rows)),
            "comparison_executions": len(comparison_rows),
            "comparison_compiled_success": comparison_success,
            "comparison_compiled_success_pct": _percent(
                comparison_success, len(comparison_rows)
            ),
            "reporting_version": REPORTING_VERSION,
            "comparison_partition_rule": "group == F",
            "partition_invariant": {
                "simple_plus_comparison_executions": len(simple_rows)
                + len(comparison_rows),
                "global_executions": len(rows),
                "simple_plus_comparison_compiled_success": simple_success
                + comparison_success,
                "global_compiled_success": global_success,
                "valid": True,
            },
        }
    )
    return corrected


def aggregate(rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Reuse frozen metrics, then repair only the reporting partition."""
    return correct_partition_metrics(rows, resilient._aggregate(rows, cases))


def assert_reporting_contract() -> None:
    """Protect the F12-like non-executable comparison case from misclassification."""
    rows = [
        {
            "id": "SIMPLE",
            "group": "A",
            "compiled_success": False,
        },
        {
            "id": "COMPARISON_ABSTENTION",
            "group": "F",
            "compiled_success": True,
            "expected": {"comparison": None, "answerability": "NEEDS_CLARIFICATION"},
        },
    ]
    metrics = correct_partition_metrics(rows, {"compiled_semantic_success": 1})
    assert metrics["simple_executions"] == 1
    assert metrics["comparison_executions"] == 1
    assert metrics["simple_compiled_success"] == 0
    assert metrics["comparison_compiled_success"] == 1
    assert metrics["partition_invariant"]["valid"] is True


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    assert_reporting_contract()
    cases = resilient.base.load_cases(args.cases)
    rows = _load_jsonl(args.raw)
    metrics = aggregate(rows, cases)
    args.output.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
