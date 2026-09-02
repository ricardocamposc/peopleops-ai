"""Offline Phase 3.4.4 replay using corrected semantic evaluator v2.

Consumes the frozen 240 raw understandings and never calls OpenAI. The purpose is
to distinguish true compiler defects from evaluator-shape defects before changing
compiler logic.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

import semantic_baseline_v1_runner_aligned as baseline_runner
import semantic_comparison_baseline_evaluator_v2 as evaluator_v2
import semantic_understanding_phase343 as phase343
import semantic_understanding_phase344 as phase344

REPLAY_VERSION = "semantic-baseline-v1-phase344-evaluator-v2-replay"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _percent(num: int, den: int) -> float | None:
    return None if den == 0 else round(num * 100.0 / den, 2)


def replay(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    canonical_success = 0
    compiler_success = 0
    compiled_success = 0
    valid_inputs = 0
    compiler_success_given_valid = 0
    comparison_compiled = 0
    simple_compiled = 0
    differences = Counter()
    by_case: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "executions": 0,
            "canonical_success": 0,
            "compiler_success": 0,
            "compiled_success": 0,
            "compiler_differences": Counter(),
        }
    )
    details: list[dict[str, Any]] = []

    for row in rows:
        case_id = str(row["id"])
        summary = by_case[case_id]
        summary["executions"] += 1
        expected = row["expected"]

        raw = phase343.SemanticUnderstandingV343.model_validate(row["raw_understanding"])
        canonical = phase344.canonicalize(raw)
        canonical_diff = baseline_runner.understanding_differences(expected, canonical)
        can_ok = not canonical_diff
        canonical_success += int(can_ok)
        summary["canonical_success"] += int(can_ok)

        compiled = None
        compiler_diff: list[str]
        try:
            compiled = phase343.compile_comparison(canonical)
            compiler_diff = evaluator_v2.compiler_differences(
                expected, canonical, compiled
            )
        except ValidationError:
            compiler_diff = ["COMPILER_SCHEMA_VALIDATION_ERROR"]

        comp_ok = not compiler_diff
        end_ok = can_ok and comp_ok
        compiler_success += int(comp_ok)
        compiled_success += int(end_ok)
        summary["compiler_success"] += int(comp_ok)
        summary["compiled_success"] += int(end_ok)
        if can_ok:
            valid_inputs += 1
            compiler_success_given_valid += int(comp_ok)
        if row.get("group") == "F":
            comparison_compiled += int(end_ok)
        else:
            simple_compiled += int(end_ok)

        for diff in compiler_diff:
            differences[diff] += 1
            summary["compiler_differences"][diff] += 1

        if can_ok and not comp_ok:
            details.append(
                {
                    "id": case_id,
                    "repetition": row.get("repetition"),
                    "canonical_differences": canonical_diff,
                    "compiler_differences": compiler_diff,
                    "canonical": canonical.model_dump(mode="json"),
                    "compiled": (
                        None if compiled is None else compiled.model_dump(mode="json")
                    ),
                }
            )

    serializable_by_case = {
        case_id: {
            **summary,
            "compiler_differences": dict(summary["compiler_differences"]),
        }
        for case_id, summary in sorted(by_case.items())
    }

    return {
        "replay_version": REPLAY_VERSION,
        "executions": total,
        "canonical_success": canonical_success,
        "canonical_success_pct": _percent(canonical_success, total),
        "compiler_success": compiler_success,
        "compiler_success_pct": _percent(compiler_success, total),
        "compiled_success": compiled_success,
        "compiled_success_pct": _percent(compiled_success, total),
        "simple_compiled_success": simple_compiled,
        "simple_executions": sum(row.get("group") != "F" for row in rows),
        "comparison_compiled_success": comparison_compiled,
        "comparison_executions": sum(row.get("group") == "F" for row in rows),
        "compiler_valid_inputs": valid_inputs,
        "compiler_success_given_valid_input": compiler_success_given_valid,
        "compiler_success_given_valid_input_pct": _percent(
            compiler_success_given_valid, valid_inputs
        ),
        "compiler_difference_counts": dict(differences),
        "canonical_valid_compiler_invalid": len(details),
        "by_case": serializable_by_case,
        "canonical_valid_compiler_invalid_details": details,
    }


def assert_replay_contract() -> None:
    phase344.assert_phase344_contract()
    evaluator_v2.assert_evaluator_contract()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert_replay_contract()
    rows = _load_jsonl(args.raw)
    result = replay(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
