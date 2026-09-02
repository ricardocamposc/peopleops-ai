"""Run Phase 4.0.1 prompt-only Direct Conceptual Eloquent experiment.

Reuses the validated Phase 4.0 runner, validator, model catalog, provider mapping,
and SQL safety logic. Only the first-LLM generation prompt is replaced.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import direct_conceptual_eloquent_phase40_runner as base_runner
import direct_conceptual_eloquent_phase401 as phase401


def assert_runner_contract() -> None:
    phase401.assert_phase401_contract()
    base_runner.assert_runner_contract()


def run(
    cases_path: Path,
    output_dir: Path,
    model: str,
    repetitions: int,
    *,
    translate_sql: bool,
    execute_sql: bool,
) -> None:
    assert_runner_contract()
    original_prompt = base_runner.phase40.ELOQUENT_GENERATION_PROMPT
    try:
        base_runner.phase40.ELOQUENT_GENERATION_PROMPT = phase401.ELOQUENT_GENERATION_PROMPT
        base_runner.run(
            cases_path,
            output_dir,
            model,
            repetitions,
            translate_sql=translate_sql,
            execute_sql=execute_sql,
        )
    finally:
        base_runner.phase40.ELOQUENT_GENERATION_PROMPT = original_prompt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--translate-sql", action="store_true")
    parser.add_argument("--execute-sql", action="store_true")
    args = parser.parse_args()
    if args.execute_sql and not args.translate_sql:
        parser.error("--execute-sql requires --translate-sql")
    run(
        args.cases,
        args.output_dir,
        args.model,
        args.repetitions,
        translate_sql=args.translate_sql,
        execute_sql=args.execute_sql,
    )


if __name__ == "__main__":
    main()
