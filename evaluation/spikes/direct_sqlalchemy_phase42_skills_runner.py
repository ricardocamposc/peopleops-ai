"""Run Phase 4.2 using skill-specific Query Programmer prompts.

This is a differentiated Phase 4.2 run, not a new phase. It reuses the existing
Phase 4.2 dataset, graph, metrics, validator, Functional Analyst, and Senior
Reviewer while swapping only the Query Programmer runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import direct_sqlalchemy_phase42_runner as base_runner
from direct_sqlalchemy_phase42_skills import (
    QUERY_GENERATE_PROMPT,
    QUERY_SEMANTIC_REPAIR_PROMPT,
    QUERY_TECHNICAL_REPAIR_PROMPT,
    SkillPromptRuntime,
)

RUNNER_VERSION = "direct-sqlalchemy-phase42-skill-prompts-v1"


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def run(
    cases_path: Path,
    output_dir: Path,
    repetitions: int,
    limit: int | None = None,
    mode: str = "both",
    resume_functional_analysis: Path | None = None,
) -> None:
    previous_runtime = base_runner.RoleModels
    previous_version = base_runner.RUNNER_VERSION
    previous_programmer_prompt = base_runner.SQLALCHEMY_QUERY_DEVELOPER_PROMPT
    try:
        base_runner.RoleModels = SkillPromptRuntime
        base_runner.RUNNER_VERSION = RUNNER_VERSION
        # Compatibility with the base manifest. The detailed skill hashes are
        # written immediately after the run.
        base_runner.SQLALCHEMY_QUERY_DEVELOPER_PROMPT = QUERY_GENERATE_PROMPT
        base_runner.run(
            cases_path,
            output_dir,
            repetitions,
            limit,
            mode,
            resume_functional_analysis,
        )
    finally:
        base_runner.RoleModels = previous_runtime
        base_runner.RUNNER_VERSION = previous_version
        base_runner.SQLALCHEMY_QUERY_DEVELOPER_PROMPT = previous_programmer_prompt

    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runner_version"] = RUNNER_VERSION
    manifest["query_programmer_prompt_strategy"] = "skill_specific"
    manifest["prompt_sha256"].update({
        "query_programmer_generate": _sha256_text(QUERY_GENERATE_PROMPT),
        "query_programmer_technical_repair": _sha256_text(
            QUERY_TECHNICAL_REPAIR_PROMPT
        ),
        "query_programmer_semantic_repair": _sha256_text(
            QUERY_SEMANTIC_REPAIR_PROMPT
        ),
    })
    manifest["query_programmer_skills"] = [
        "GENERATE",
        "TECHNICAL_REPAIR",
        "SEMANTIC_REPAIR",
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=base_runner.DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--mode", choices=("analyst", "developer", "team", "both"), default="both"
    )
    parser.add_argument("--resume-functional-analysis", type=Path)
    args = parser.parse_args()
    run(
        args.cases,
        args.output_dir,
        args.repetitions,
        args.limit,
        args.mode,
        args.resume_functional_analysis,
    )


if __name__ == "__main__":
    main()
