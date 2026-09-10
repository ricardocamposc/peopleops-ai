"""Offline replay of Phase 3.4.4 against frozen Semantic Baseline v1 outputs.

The replay reuses persisted raw Semantic Understanding outputs, applies the new
deterministic Phase 3.4.4 canonicalizer, recompiles them with the frozen
comparison compiler, and measures them with the frozen evaluator. It never calls
OpenAI and never changes the baseline artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

import semantic_baseline_v1_reporting_v2 as reporting_v2
import semantic_baseline_v1_runner_aligned as baseline_runner
import semantic_comparison_baseline_evaluator_v1 as evaluator
import semantic_understanding_phase343 as phase343
import semantic_understanding_phase344 as phase344

REPLAY_VERSION = "semantic-baseline-v1-phase344-offline-replay"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _percent(num: int, den: int) -> float | None:
    return None if den == 0 else round(num * 100.0 / den, 2)


def _measure(
    expected: dict[str, Any], canonical: phase343.SemanticUnderstandingV343
) -> dict[str, Any]:
    canonical_diff = baseline_runner.understanding_differences(expected, canonical)
    try:
        compiled = phase343.compile_comparison(canonical)
    except ValidationError as exc:
        return {
            "canonical_success": not canonical_diff,
            "canonical_differences": canonical_diff,
            "compiler_success": False,
            "compiler_differences": ["COMPILER_SCHEMA_VALIDATION_ERROR"],
            "compiler_validation_errors": exc.errors(),
            "compiled_success": False,
            "compiled": None,
        }
    compiler_diff = evaluator.compiler_differences(expected, canonical, compiled)
    return {
        "canonical_success": not canonical_diff,
        "canonical_differences": canonical_diff,
        "compiler_success": not compiler_diff,
        "compiler_differences": compiler_diff,
        "compiler_validation_errors": [],
        "compiled_success": not canonical_diff and not compiler_diff,
        "compiled": compiled.model_dump(mode="json"),
    }


def replay(rows: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    canonical_success = 0
    compiler_success = 0
    compiled_success = 0
    comparison_canonical = 0
    comparison_compiled = 0
    simple_canonical = 0
    simple_compiled = 0
    compiler_valid_inputs = 0
    compiler_success_given_valid = 0

    for row in rows:
        raw_payload = row.get("raw_understanding")
        if raw_payload is None:
            continue
        raw = phase343.SemanticUnderstandingV343.model_validate(raw_payload)
        canonical = phase344.canonicalize(raw)
        measured = _measure(row["expected"], canonical)
        is_comparison = row.get("group") == "F"

        canonical_success += int(measured["canonical_success"])
        compiler_success += int(measured["compiler_success"])
        compiled_success += int(measured["compiled_success"])
        if measured["canonical_success"]:
            compiler_valid_inputs += 1
            compiler_success_given_valid += int(measured["compiler_success"])
        if is_comparison:
            comparison_canonical += int(measured["canonical_success"])
            comparison_compiled += int(measured["compiled_success"])
        else:
            simple_canonical += int(measured["canonical_success"])
            simple_compiled += int(measured["compiled_success"])

        before_canonical = bool(row.get("canonical_success"))
        before_compiled = bool(row.get("compiled_success"))
        if (
            before_canonical != measured["canonical_success"]
            or before_compiled != measured["compiled_success"]
            or row.get("compiler_success") != measured["compiler_success"]
        ):
            details.append(
                {
                    "id": row["id"],
                    "group": row.get("group"),
                    "repetition": row.get("repetition"),
                    "before_canonical_success": before_canonical,
                    "after_canonical_success": measured["canonical_success"],
                    "before_compiler_success": row.get("compiler_success"),
                    "after_compiler_success": measured["compiler_success"],
                    "before_compiled_success": before_compiled,
                    "after_compiled_success": measured["compiled_success"],
                    "after_canonical_differences": measured["canonical_differences"],
                    "after_compiler_differences": measured["compiler_differences"],
                }
            )

    total = len(rows)
    return {
        "replay_version": REPLAY_VERSION,
        "executions": total,
        "baseline_reference": {
            "canonical_success": sum(bool(row.get("canonical_success")) for row in rows),
            "compiled_success": sum(bool(row.get("compiled_success")) for row in rows),
            "simple_compiled_success": sum(
                bool(row.get("compiled_success")) for row in rows if row.get("group") != "F"
            ),
            "comparison_compiled_success": sum(
                bool(row.get("compiled_success")) for row in rows if row.get("group") == "F"
            ),
        },
        "phase344": {
            "canonical_success": canonical_success,
            "canonical_success_pct": _percent(canonical_success, total),
            "compiler_success": compiler_success,
            "compiler_success_pct": _percent(compiler_success, total),
            "compiled_success": compiled_success,
            "compiled_success_pct": _percent(compiled_success, total),
            "simple_canonical_success": simple_canonical,
            "simple_compiled_success": simple_compiled,
            "comparison_canonical_success": comparison_canonical,
            "comparison_compiled_success": comparison_compiled,
            "compiler_valid_input_cases": compiler_valid_inputs,
            "compiler_success_given_valid_input": compiler_success_given_valid,
            "compiler_success_given_valid_input_pct": _percent(
                compiler_success_given_valid, compiler_valid_inputs
            ),
        },
        "changed_executions": details,
    }


def assert_phase344_replay_contract() -> None:
    phase344.assert_phase344_contract()
    reporting_v2.assert_reporting_contract()
    evaluator.assert_evaluator_contract()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    assert_phase344_replay_contract()
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
