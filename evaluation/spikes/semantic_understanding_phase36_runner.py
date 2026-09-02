"""Run Phase 3.6 Semantic Understanding against the frozen baseline cases.

Only the understanding prompt changes. The schema remains V343, canonicalization
and compilation use the validated Phase 3.4.5 path, and semantic correctness is
measured with evaluator v3. No SQL, MCP, or executable Eloquent is used.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from peopleops_api.analysis_workflow import OpenAIStructuredModel
from semantic_query_dsl_phase242 import (
    CAPABILITIES,
    SOURCE_DATE,
    SOURCE_TIMEZONE,
    scoped_catalog,
)
from semantic_query_dsl_phase243 import ScopeSelectionV243
from semantic_query_dsl_phase244 import capabilities

import semantic_baseline_v1_runner_aligned as baseline_runner
import semantic_comparison_baseline_evaluator_v3 as evaluator_v3
import semantic_understanding_phase3 as phase3
import semantic_understanding_phase343 as phase343
import semantic_understanding_phase345 as phase345
import semantic_understanding_phase36 as phase36

RUNNER_VERSION = "semantic-understanding-phase36-v1"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _percent(num: int, den: int) -> float | None:
    return None if den == 0 else round(num * 100.0 / den, 2)


def run(
    cases_path: Path,
    output_dir: Path,
    model: str,
    repetitions: int,
) -> None:
    cases = _load_cases(cases_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    llm = OpenAIStructuredModel(
        api_key=os.environ["OPENAI_API_KEY"],
        model=model,
        max_retries=0,
    )

    rows: list[dict[str, Any]] = []
    failures = Counter()
    by_case: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "executions": 0,
            "raw_success": 0,
            "canonical_success": 0,
            "compiler_success": 0,
            "compiled_success": 0,
        }
    )

    for repetition in range(1, repetitions + 1):
        for case in cases:
            started = time.perf_counter()
            case_id = str(case["id"])
            summary = by_case[case_id]
            summary["executions"] += 1

            scope_instructions = (
                f"{phase3.SCOPE_PROMPT}\n\nQuestion:\n{case['question']}\n\n"
                f"Capabilities:\n{json.dumps(CAPABILITIES)}"
            )
            scope = llm.parse(
                purpose="phase36-capability-scope",
                instructions=scope_instructions,
                output_model=ScopeSelectionV243,
            )
            selected = capabilities(scope)
            catalog = scoped_catalog(selected)

            instructions = (
                f"{phase36.UNDERSTANDING_PROMPT_V36}\n\n"
                f"Question:\n{case['question']}\n\n"
                f"Source date: {SOURCE_DATE.isoformat()}\n"
                f"Timezone: {SOURCE_TIMEZONE}\n"
                f"Scoped catalog:\n{json.dumps(catalog)}"
            )
            raw = llm.parse(
                purpose="phase36-semantic-understanding",
                instructions=instructions,
                output_model=phase343.SemanticUnderstandingV343,
            )
            canonical = phase345.canonicalize(raw)
            compiled = phase345.compile_semantic(canonical)
            expected = case["expected"]

            raw_diff = baseline_runner.understanding_differences(expected, raw)
            canonical_diff = baseline_runner.understanding_differences(
                expected, canonical
            )
            compiler_diff = evaluator_v3.compiler_differences(
                expected, canonical, compiled
            )

            raw_ok = not raw_diff
            canonical_ok = not canonical_diff
            compiler_ok = not compiler_diff
            compiled_ok = canonical_ok and compiler_ok

            summary["raw_success"] += int(raw_ok)
            summary["canonical_success"] += int(canonical_ok)
            summary["compiler_success"] += int(compiler_ok)
            summary["compiled_success"] += int(compiled_ok)

            for diff in canonical_diff:
                failures[diff] += 1

            rows.append(
                {
                    "id": case_id,
                    "group": case.get("group"),
                    "language": case.get("language"),
                    "repetition": repetition,
                    "question": case["question"],
                    "expected": expected,
                    "scope": scope.model_dump(mode="json"),
                    "selected_capabilities": selected,
                    "raw_understanding": raw.model_dump(mode="json"),
                    "canonical_understanding": canonical.model_dump(mode="json"),
                    "compiled": compiled.model_dump(mode="json"),
                    "raw_differences": raw_diff,
                    "canonical_differences": canonical_diff,
                    "compiler_differences": compiler_diff,
                    "raw_success": raw_ok,
                    "canonical_success": canonical_ok,
                    "compiler_success": compiler_ok,
                    "compiled_success": compiled_ok,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )

    total = len(rows)
    canonical_success = sum(row["canonical_success"] for row in rows)
    compiled_success = sum(row["compiled_success"] for row in rows)
    comparison_rows = [row for row in rows if row.get("group") == "F"]
    simple_rows = [row for row in rows if row.get("group") != "F"]
    valid_inputs = [row for row in rows if row["canonical_success"]]

    metrics = {
        "runner_version": RUNNER_VERSION,
        "cases": len(cases),
        "repetitions": repetitions,
        "executions": total,
        "structured_output_success": total,
        "raw_understanding_success": sum(row["raw_success"] for row in rows),
        "canonical_understanding_success": canonical_success,
        "canonical_understanding_success_pct": _percent(canonical_success, total),
        "compiled_semantic_success": compiled_success,
        "compiled_semantic_success_pct": _percent(compiled_success, total),
        "simple_compiled_success": sum(row["compiled_success"] for row in simple_rows),
        "simple_executions": len(simple_rows),
        "comparison_compiled_success": sum(
            row["compiled_success"] for row in comparison_rows
        ),
        "comparison_executions": len(comparison_rows),
        "comparison_canonical_success": sum(
            row["canonical_success"] for row in comparison_rows
        ),
        "compiler_valid_inputs": len(valid_inputs),
        "compiler_success_given_valid_input": sum(
            row["compiler_success"] for row in valid_inputs
        ),
        "canonical_difference_counts": dict(failures),
        "by_case": dict(sorted(by_case.items())),
        "measurement_evaluator": "semantic_comparison_baseline_evaluator_v3",
    }
    manifest = {
        "phase": "3.6",
        "runner_version": RUNNER_VERSION,
        "cases": len(cases),
        "repetitions": repetitions,
        "expected_executions": len(cases) * repetitions,
        "actual_executions": total,
        "model": model,
        "source_date": SOURCE_DATE.isoformat(),
        "timezone": SOURCE_TIMEZONE,
        "max_retries": 0,
        "understanding_prompt": "UNDERSTANDING_PROMPT_V36",
        "schema": "SemanticUnderstandingV343",
        "canonicalizer": "Phase 3.4.5",
        "compiler": "Phase 3.4.5",
        "measurement_evaluator": "semantic_comparison_baseline_evaluator_v3",
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
    parser.add_argument(
        "--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )
    args = parser.parse_args()
    phase36.assert_phase36_contract()
    phase345.assert_phase345_contract()
    evaluator_v3.assert_evaluator_contract()
    run(args.cases, args.output_dir, args.model, args.repetitions)


if __name__ == "__main__":
    main()
