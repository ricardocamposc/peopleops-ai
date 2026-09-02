"""Corrected offline replay for Semantic Baseline v1.

This module wraps the established replay and fixes one reporting defect: the
count of comparison rows that carry a top-level temporal must be restricted to
the frozen comparison partition (group F). It also reports comparison-only
redundancy classes so global/simple rows cannot contaminate comparison metrics.

No OpenAI calls are made. No semantic behavior is changed.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import semantic_baseline_v1_offline_replay as replay_v1
import semantic_baseline_v1_reporting_v2 as reporting_v2
import semantic_comparison_canonical_redundancy as redundancy
import semantic_understanding_phase343 as phase343

REPLAY_VERSION = "semantic-baseline-v1-offline-replay-v2"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _comparison_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    comparison_rows = [row for row in rows if row.get("group") == "F"]
    with_top_level_temporal = 0
    classes: Counter[str] = Counter()
    removable = 0

    for row in comparison_rows:
        payload = row.get("canonical_understanding")
        if payload is None:
            classes["NO_CANONICAL"] += 1
            continue
        canonical = phase343.SemanticUnderstandingV343.model_validate(payload)
        classification = redundancy.classify_top_level_temporal_redundancy(canonical)
        classes[classification] += 1
        if canonical.comparison is not None and canonical.temporal is not None:
            with_top_level_temporal += 1
        if classification in {
            "STRICT_EQUIVALENT",
            "EQUIVALENT_NON_RELATIVE_ANCHOR_METADATA",
        }:
            removable += 1

    return {
        "comparison_executions": len(comparison_rows),
        "comparison_with_top_level_temporal": with_top_level_temporal,
        "comparison_redundancy_classes": dict(classes),
        "comparison_mechanically_removable_executions": removable,
    }


def replay(*, rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    result = replay_v1.replay(rows=rows, cases=cases)
    diagnostics = _comparison_diagnostics(rows)
    result["replay_version"] = REPLAY_VERSION
    result["redundancy_experiment"].update(diagnostics)

    comparison_total = diagnostics["comparison_executions"]
    if comparison_total != result["corrected_reporting"]["comparison_executions"]:
        raise AssertionError("comparison partition mismatch between reporting and replay")

    return result


def assert_offline_replay_v2_contract() -> None:
    replay_v1.assert_offline_replay_contract()
    reporting_v2.assert_reporting_contract()

    simple = phase343.SemanticUnderstandingV343(
        goal="simple",
        temporal=phase343.TemporalMeaningV343(
            reference_frame="CURRENT_MONTH", relation="EXACT", unit="MONTH"
        ),
    )
    comparison = phase343.SemanticUnderstandingV343(
        goal="comparison",
        temporal=phase343.TemporalMeaningV343(
            reference_frame="CURRENT_MONTH", relation="EXACT", unit="MONTH"
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
    rows = [
        {"group": "A", "canonical_understanding": simple.model_dump(mode="json")},
        {"group": "F", "canonical_understanding": comparison.model_dump(mode="json")},
    ]
    diagnostics = _comparison_diagnostics(rows)
    assert diagnostics["comparison_executions"] == 1
    assert diagnostics["comparison_with_top_level_temporal"] == 1
    assert diagnostics["comparison_mechanically_removable_executions"] == 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    assert_offline_replay_v2_contract()
    cases = replay_v1.baseline_runner.load_cases(args.cases)
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
