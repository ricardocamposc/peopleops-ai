"""Run the Phase 4.2 functional, query-programmer, and agent-team experiments."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from direct_sqlalchemy_phase42 import (
    MAX_SEMANTIC_REVISION_ATTEMPTS,
    MAX_TECHNICAL_REPAIR_ATTEMPTS,
    SEMANTIC_CLARIFIER_PROMPT,
    SENIOR_QUERY_REVIEWER_PROMPT,
    SQLALCHEMY_QUERY_DEVELOPER_PROMPT,
    LangChainAgentRuntime,
    Phase42State,
    _query_developer,
    _query_validation,
    _semantic_clarifier,
    assert_phase42_contract,
    build_graph,
    initial_state,
)

RUNNER_VERSION = "direct-sqlalchemy-phase42-v2"
DATASET_VERSION = "phase42-v1"
DEFAULT_CASES = Path(__file__).with_name("direct_sqlalchemy_phase42_cases.jsonl")
RoleModels = LangChainAgentRuntime


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_text(content: str) -> str:
    return _sha256_bytes(content.encode("utf-8"))


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _clean_state(state: Phase42State) -> dict[str, Any]:
    return {key: value for key, value in state.items() if key != "_llm"}


def _row_from_state(
    *, case: dict[str, Any], mode: str, state: dict[str, Any], started: float,
) -> dict[str, Any]:
    attempts = state.get("query_developer_attempts", [])
    validation_events = [
        event
        for event in state.get("audit_trail", [])
        if event.get("role") == "query_validation"
    ]
    first_validation = validation_events[0]["output"] if validation_events else None
    final_validation = validation_events[-1]["output"] if validation_events else None
    first = attempts[0] if attempts else None
    final_status = state.get("final_status") or (
        "FUNCTIONAL_ANALYST_COMPLETE"
        if mode == "FUNCTIONAL_ANALYST_ONLY"
        else "QUERY_DEVELOPER_ONLY_COMPLETE"
        if mode == "QUERY_DEVELOPER_ONLY"
        else ""
    )
    return {
        "id": case["id"],
        "language": case.get("language", "es"),
        "category": case.get("category"),
        "mode": mode,
        "question": case["question"],
        "accepted_outcomes": case.get("accepted_outcomes", []),
        "functional_expectation": case.get("functional_expectation"),
        "query_expectation": case.get("query_expectation"),
        "functional_analysis": state.get("functional_analysis"),
        "query_task": state.get("query_task"),
        "query_developer_attempts": attempts,
        "first_pass_status": first.get("status") if first else None,
        "first_pass_validation": first_validation,
        "final_validation": final_validation,
        "senior_reviews": state.get("senior_reviews", []),
        "senior_previous_issues_resolved": sum(
            item.get("resolution_status") == "RESOLVED"
            for review in state.get("senior_reviews", [])
            for item in review.get("previous_issue_resolutions", [])
        ),
        "senior_previous_issues_unresolved": sum(
            item.get("resolution_status") in {"UNRESOLVED", "PARTIALLY_RESOLVED"}
            for review in state.get("senior_reviews", [])
            for item in review.get("previous_issue_resolutions", [])
        ),
        "technical_repair_attempts": state.get("technical_repair_attempts", 0),
        "semantic_revision_attempts": state.get("semantic_revision_attempts", 0),
        "internal_tool_calls": state.get("internal_tool_calls", 0),
        "internal_validation_attempts": state.get("internal_validation_attempts", 0),
        "internal_self_repair_attempts": state.get("internal_self_repair_attempts", 0),
        "internal_self_repair_success": state.get("internal_self_repair_success", 0),
        "internal_iterations": state.get("internal_iterations", []),
        "internal_candidates_generated": state.get("internal_candidates_generated", 0),
        "internal_candidates_changed": state.get("internal_candidates_changed", 0),
        "internal_candidates_unchanged": state.get("internal_candidates_unchanged", 0),
        "syntax_short_circuits": state.get("syntax_short_circuits", 0),
        "build_short_circuits": state.get("build_short_circuits", 0),
        "compile_attempts": state.get("compile_attempts", 0),
        "tool_calls_avoided_by_short_circuit": state.get(
            "tool_calls_avoided_by_short_circuit", 0
        ),
        "candidate_valid_before_external_validator": state.get(
            "candidate_valid_before_external_validator", False
        ),
        "external_validator_pass_after_internal_validation": state.get(
            "external_validator_pass_after_internal_validation", False
        ),
        "final_status": final_status,
        "technical_valid": bool(
            final_validation and final_validation.get("technically_valid")
        ),
        "semantic_plausibility": (
            "SENIOR_APPROVED"
            if final_status == "APPROVED"
            else "NOT_EVALUATED"
            if mode in {"FUNCTIONAL_ANALYST_ONLY", "QUERY_DEVELOPER_ONLY"}
            else "SENIOR_NOT_APPROVED"
        ),
        "request_id": state.get("request_id"),
        "current_stage": state.get("current_stage"),
        "stage_history": state.get("stage_history", []),
        "audit_trail": state.get("audit_trail", []),
        "models": state.get("models", {}),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _run_mode(
    *, mode: str, cases: list[dict[str, Any]], graph: Any,
    models: dict[str, str], llm: RoleModels,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        state = initial_state(mode=mode, question=case["question"], llm=llm)
        state["models"] = models
        if mode == "FUNCTIONAL_ANALYST_ONLY":
            result = dict(state)
            result.update(_semantic_clarifier(result))
            result["final_status"] = (
                "NEEDS_CLARIFICATION"
                if result.get("functional_analysis", {}).get("needs_clarification")
                else "FUNCTIONAL_ANALYST_COMPLETE"
            )
        else:
            result = graph.invoke(state)
        rows.append(
            _row_from_state(
                case=case, mode=mode, state=_clean_state(result), started=started
            )
        )
    return rows


def _resume_developer_validation(
    *, analyst_rows: list[dict[str, Any]], models: dict[str, str], llm: RoleModels
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in analyst_rows:
        started = time.perf_counter()
        case = {
            "id": source["id"],
            "language": source.get("language", "es"),
            "category": source.get("category"),
            "question": source["question"],
            "accepted_outcomes": source.get("accepted_outcomes", []),
            "functional_expectation": source.get("functional_expectation"),
            "query_expectation": source.get("query_expectation"),
        }
        state = initial_state(
            mode="QUERY_DEVELOPER_ONLY", question=source["question"], llm=llm
        )
        state["models"] = models
        state["functional_analysis"] = source["functional_analysis"]
        state["query_task"] = source.get("query_task")
        state["audit_trail"] = list(source.get("audit_trail", []))
        if source.get("functional_analysis", {}).get("needs_clarification"):
            state["final_status"] = "NEEDS_CLARIFICATION"
        else:
            state.update(_query_developer(state))
            if state.get("current_query", {}).get("status") == "QUERY":
                state.update(_query_validation(state))
        rows.append(
            _row_from_state(
                case=case, mode="QUERY_DEVELOPER_ONLY",
                state=_clean_state(state), started=started,
            )
        )
    return rows


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _metrics(
    rows: list[dict[str, Any]], mode: str, *, semantic_clarifier_calls: int | None = None
) -> dict[str, Any]:
    cases = len(rows)
    first_pass_valid = sum(
        bool(row["first_pass_validation"] and row["first_pass_validation"].get("technically_valid"))
        for row in rows
    )
    generated_query = sum(row["first_pass_status"] == "QUERY" for row in rows)
    tech_attempted = sum(row["technical_repair_attempts"] > 0 for row in rows)
    tech_success = sum(
        row["technical_repair_attempts"] > 0 and row["technical_valid"] for row in rows
    )
    senior_reviewed = sum(bool(row["senior_reviews"]) for row in rows)
    senior_first_approved = sum(
        bool(row["senior_reviews"] and row["senior_reviews"][0].get("status") == "APPROVED")
        for row in rows
    )
    senior_revise = sum(
        any(review.get("status") == "REVISE" for review in row["senior_reviews"])
        for row in rows
    )
    semantic_attempted = sum(row["semantic_revision_attempts"] > 0 for row in rows)
    semantic_success = sum(
        row["semantic_revision_attempts"] > 0 and row["final_status"] == "APPROVED"
        for row in rows
    )
    final_approved = sum(row["final_status"] == "APPROVED" for row in rows)
    final_technical = sum(row["technical_valid"] for row in rows)
    error_codes = Counter(
        diagnostic.get("code", "UNKNOWN")
        for row in rows
        for diagnostic in (row["final_validation"] or {}).get("diagnostics", [])
    )
    return {
        "runner_version": RUNNER_VERSION,
        "mode": mode,
        "cases": cases,
        "workflow_completion": sum(bool(row["final_status"]) for row in rows),
        "semantic_clarifier_calls": (
            cases if semantic_clarifier_calls is None else semantic_clarifier_calls
        ),
        "query_generation": {
            "count": generated_query,
            "rate": _rate(generated_query, cases),
        },
        "first_pass_technical_validity": {
            "count": first_pass_valid,
            "rate": _rate(first_pass_valid, generated_query),
        },
        "technical_repair": {
            "attempted_cases": tech_attempted,
            "successful_cases": tech_success,
            "success_rate": _rate(tech_success, tech_attempted),
        },
        "external_technical_repair_attempts": tech_attempted,
        "external_technical_repair_success": tech_success,
        "internal_tool_calls": sum(row["internal_tool_calls"] for row in rows),
        "internal_candidates_generated": sum(
            row.get("internal_candidates_generated", 0) for row in rows
        ),
        "internal_candidates_changed": sum(
            row.get("internal_candidates_changed", 0) for row in rows
        ),
        "internal_candidates_unchanged": sum(
            row.get("internal_candidates_unchanged", 0) for row in rows
        ),
        "syntax_short_circuits": sum(row.get("syntax_short_circuits", 0) for row in rows),
        "build_short_circuits": sum(row.get("build_short_circuits", 0) for row in rows),
        "compile_attempts": sum(row.get("compile_attempts", 0) for row in rows),
        "tool_calls_avoided_by_short_circuit": sum(
            row.get("tool_calls_avoided_by_short_circuit", 0) for row in rows
        ),
        "internal_validation_attempts": sum(
            row["internal_validation_attempts"] for row in rows
        ),
        "internal_self_repair": {
            "attempted": sum(row["internal_self_repair_attempts"] for row in rows),
            "successful": sum(row["internal_self_repair_success"] for row in rows),
        },
        "candidate_valid_before_external_validator": sum(
            row["candidate_valid_before_external_validator"] for row in rows
        ),
        "external_validator_pass_after_internal_validation": sum(
            row["external_validator_pass_after_internal_validation"] for row in rows
        ),
        "senior_review": {
            "reviewed_cases": senior_reviewed,
            "first_pass_approved": senior_first_approved,
            "first_pass_approval_rate": _rate(senior_first_approved, senior_reviewed),
            "revision_requested_cases": senior_revise,
            "previous_issues_resolved": sum(
                row.get("senior_previous_issues_resolved", 0) for row in rows
            ),
            "previous_issues_unresolved": sum(
                row.get("senior_previous_issues_unresolved", 0) for row in rows
            ),
        },
        "semantic_repair": {
            "attempted_cases": semantic_attempted,
            "successful_cases": semantic_success,
            "success_rate": _rate(semantic_success, semantic_attempted),
        },
        "final": {
            "technical_valid": final_technical,
            "technical_validity_rate": _rate(final_technical, generated_query),
            "semantic_approved": final_approved,
            "semantic_approval_rate": _rate(final_approved, senior_reviewed),
            "needs_clarification": sum(
                row["final_status"] == "NEEDS_CLARIFICATION" for row in rows
            ),
            "needs_info": sum(row["final_status"] == "NEEDS_INFO" for row in rows),
            "cannot_implement": sum(
                row["final_status"] == "CANNOT_IMPLEMENT" for row in rows
            ),
            "technical_validation_failed": sum(
                row["final_status"] == "TECHNICAL_VALIDATION_FAILED" for row in rows
            ),
            "max_semantic_revisions_reached": sum(
                row["final_status"] == "MAX_SEMANTIC_REVISIONS_REACHED"
                for row in rows
            ),
        },
        "validation_error_codes": dict(error_codes),
        "latency_ms": {
            "average_case": round(
                sum(row["duration_ms"] for row in rows) / cases, 2
            ) if cases else 0,
        },
    }


def assert_runner_contract() -> None:
    assert_phase42_contract()
    cases = _load_cases(DEFAULT_CASES)
    assert len(cases) >= 30
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case["id"].startswith("P42-") for case in cases)
    assert {"es", "en", "pt"}.issubset({case.get("language") for case in cases})


def run(
    cases_path: Path,
    output_dir: Path,
    repetitions: int,
    limit: int | None = None,
    mode: str = "both",
    resume_functional_analysis: Path | None = None,
) -> None:
    assert_runner_contract()
    cases = _load_cases(cases_path)
    if not cases:
        raise ValueError("Phase 4.2 dataset is empty")
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be positive")
        cases = cases[:limit]

    selected_modes = {
        "analyst": ("FUNCTIONAL_ANALYST_ONLY",),
        "developer": ("QUERY_DEVELOPER_ONLY",),
        "team": ("AGENT_TEAM",),
        "both": ("QUERY_DEVELOPER_ONLY", "AGENT_TEAM"),
    }[mode]

    output_dir.mkdir(parents=True, exist_ok=True)
    model_config = {
        "semantic_clarifier": os.getenv("SEMANTIC_CLARIFIER_MODEL", "gpt-4o-mini"),
        "sqlalchemy_query_developer": os.getenv(
            "SQLALCHEMY_QUERY_DEVELOPER_MODEL", "gpt-4o-mini"
        ),
        "senior_query_reviewer": os.getenv(
            "SENIOR_QUERY_REVIEWER_MODEL", "gpt-4o-mini"
        ),
    }
    llm = RoleModels(model_config)
    all_rows: list[dict[str, Any]] = []

    if resume_functional_analysis is not None:
        analyst_rows = _load_cases(resume_functional_analysis)
        all_rows = _resume_developer_validation(
            analyst_rows=analyst_rows, models=model_config, llm=llm
        )
        for row in all_rows:
            row["repetition"] = 1
    else:
        graph = build_graph()
        for repetition in range(1, repetitions + 1):
            for mode_name in selected_modes:
                mode_rows = _run_mode(
                    mode=mode_name, cases=cases, graph=graph,
                    models=model_config, llm=llm,
                )
                for row in mode_rows:
                    row["repetition"] = repetition
                all_rows.extend(mode_rows)

    analyst_rows = [
        row for row in all_rows if row["mode"] == "FUNCTIONAL_ANALYST_ONLY"
    ]
    developer_rows = [
        row for row in all_rows if row["mode"] == "QUERY_DEVELOPER_ONLY"
    ]
    team_rows = [row for row in all_rows if row["mode"] == "AGENT_TEAM"]

    metrics = {
        "runner_version": RUNNER_VERSION,
        "dataset_version": DATASET_VERSION,
        "cases": len(cases),
        "repetitions": repetitions,
        "executions": len(all_rows),
        "functional_analyst_only": (
            _metrics(analyst_rows, "FUNCTIONAL_ANALYST_ONLY")
            if analyst_rows else None
        ),
        "query_developer_only": (
            _metrics(
                developer_rows,
                "QUERY_DEVELOPER_ONLY",
                semantic_clarifier_calls=0 if resume_functional_analysis else None,
            )
            if developer_rows else None
        ),
        "agent_team": (
            _metrics(team_rows, "AGENT_TEAM") if team_rows else None
        ),
    }

    manifest = {
        "runner_version": RUNNER_VERSION,
        "dataset_version": DATASET_VERSION,
        "dataset_path": str(cases_path),
        "dataset_sha256": _sha256_bytes(cases_path.read_bytes()),
        "git_commit_sha": _git_commit(),
        "prompt_sha256": {
            "functional_analyst": _sha256_text(SEMANTIC_CLARIFIER_PROMPT),
            "query_programmer": _sha256_text(SQLALCHEMY_QUERY_DEVELOPER_PROMPT),
            "senior_query_reviewer": _sha256_text(SENIOR_QUERY_REVIEWER_PROMPT),
        },
        "model_by_role": model_config,
        "cases": len(cases),
        "repetitions": repetitions,
        "mode": mode,
        "resumed_from_functional_analysis": (
            str(resume_functional_analysis) if resume_functional_analysis else None
        ),
        "selected_case_ids": [case["id"] for case in cases],
        "source_date": "2026-08-30",
        "timezone": "UTC",
        "llm_retries": 0,
        "mcp": False,
        "database_execution": False,
        "max_technical_repair_attempts": MAX_TECHNICAL_REPAIR_ATTEMPTS,
        "max_semantic_revision_attempts": MAX_SEMANTIC_REVISION_ATTEMPTS,
        "pipeline": (
            "functional analyst -> query programmer -> deterministic validation -> "
            "technical repair if invalid -> senior review if valid -> semantic repair"
        ),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, default=str) for row in all_rows
        ) + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    print(json.dumps({"output_dir": str(output_dir), "metrics": metrics}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--mode", choices=("analyst", "developer", "team", "both"), default="both"
    )
    parser.add_argument("--resume-functional-analysis", type=Path)
    args = parser.parse_args()
    run(
        args.cases, args.output_dir, args.repetitions, args.limit,
        args.mode, args.resume_functional_analysis,
    )


if __name__ == "__main__":
    main()
