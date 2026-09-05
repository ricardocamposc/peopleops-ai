"""Run the Phase 4.2 query-developer-only and agent-team experiments."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from direct_sqlalchemy_phase42 import (
    LangChainAgentRuntime,
    Phase42State,
    _query_developer,
    _query_validation,
    _semantic_clarifier,
    assert_phase42_contract,
    build_graph,
    initial_state,
)

RUNNER_VERSION = "direct-sqlalchemy-phase42-v1"


RoleModels = LangChainAgentRuntime


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _clean_state(state: Phase42State) -> dict[str, Any]:
    return {key: value for key, value in state.items() if key != "_llm"}


def _run_mode(
    *,
    mode: str,
    cases: list[dict[str, Any]],
    graph: Any,
    models: dict[str, str],
    llm: RoleModels,
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
        clean = _clean_state(result)
        attempts = clean.get("query_developer_attempts", [])
        first = attempts[0] if attempts else None
        first_validation = None
        validation_events = [
            event
            for event in clean.get("audit_trail", [])
            if event.get("role") == "query_validation"
        ]
        if validation_events:
            first_validation = validation_events[0]["output"]
        final_validation = validation_events[-1]["output"] if validation_events else None
        senior_reviews = clean.get("senior_reviews", [])
        final_status = clean.get("final_status") or (
            "FUNCTIONAL_ANALYST_COMPLETE" if mode == "FUNCTIONAL_ANALYST_ONLY" else
            "QUERY_DEVELOPER_ONLY_COMPLETE" if mode == "QUERY_DEVELOPER_ONLY" else ""
        )
        rows.append(
            {
                "id": case["id"],
                "language": case.get("language", "es"),
                "category": case.get("category"),
                "mode": mode,
                "question": case["question"],
                "accepted_outcomes": case.get("accepted_outcomes", []),
                "functional_analysis": clean.get("functional_analysis"),
                "query_task": clean.get("query_task"),
                "query_developer_attempts": attempts,
                "first_pass_validation": first_validation,
                "final_validation": final_validation,
                "senior_reviews": senior_reviews,
                "revision_count": clean.get("revision_count", 0),
                "final_status": final_status,
                "technical_valid": bool(final_validation and final_validation["technically_valid"]),
                "semantic_plausibility": (
                    "SENIOR_APPROVED"
                    if final_status == "APPROVED"
                    else "NOT_EVALUATED"
                    if mode in {"FUNCTIONAL_ANALYST_ONLY", "QUERY_DEVELOPER_ONLY"}
                    else "SENIOR_NOT_APPROVED"
                ),
                "audit_trail": clean.get("audit_trail", []),
                "models": models,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "first_pass_status": first.get("status") if first else None,
            }
        )
    return rows


def _resume_developer_validation(
    *, analyst_rows: list[dict[str, Any]], models: dict[str, str], llm: RoleModels
) -> list[dict[str, Any]]:
    """Continue an existing analyst run without invoking the analyst again."""
    rows: list[dict[str, Any]] = []
    for source in analyst_rows:
        started = time.perf_counter()
        state = initial_state(
            mode="QUERY_DEVELOPER_ONLY", question=source["question"], llm=llm
        )
        state["models"] = models
        state["functional_analysis"] = source["functional_analysis"]
        state["query_task"] = source.get("query_task")
        state["audit_trail"] = list(source.get("audit_trail", []))
        state.update(_query_developer(state))
        state.update(_query_validation(state))
        clean = _clean_state(state)
        current_query = clean.get("current_query") or {}
        validation = clean.get("validation_result")
        rows.append({
            "id": source["id"],
            "language": source.get("language", "es"),
            "category": source.get("category"),
            "mode": "QUERY_DEVELOPER_ONLY",
            "question": source["question"],
            "accepted_outcomes": source.get("accepted_outcomes", []),
            "functional_analysis": clean.get("functional_analysis"),
            "query_task": clean.get("query_task"),
            "query_developer_attempts": clean.get("query_developer_attempts", []),
            "first_pass_validation": validation,
            "final_validation": validation,
            "senior_reviews": [],
            "revision_count": 0,
            "final_status": (
                "QUERY_DEVELOPER_ONLY_COMPLETE"
                if current_query.get("status") == "QUERY"
                else current_query.get("status", "")
            ),
            "technical_valid": bool(validation and validation["technically_valid"]),
            "semantic_plausibility": "NOT_EVALUATED",
            "audit_trail": clean.get("audit_trail", []),
            "models": models,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "first_pass_status": current_query.get("status"),
        })
    return rows


def _metrics(
    rows: list[dict[str, Any]], mode: str, *, semantic_clarifier_calls: int | None = None
) -> dict[str, Any]:
    senior_reviews = [review for row in rows for review in row["senior_reviews"]]
    first_pass_valid = [row for row in rows if row["first_pass_validation"] and row["first_pass_validation"]["technically_valid"]]
    final_approved = [row for row in rows if row["final_status"] == "APPROVED"]
    revisions = [review for review in senior_reviews if review["status"] == "REVISE"]
    repaired = [row for row in rows if row["revision_count"] > 0 and row["final_status"] == "APPROVED"]
    return {
        "runner_version": RUNNER_VERSION,
        "mode": mode,
        "cases": len(rows),
        "executions": len(rows),
        "semantic_clarifier_calls": (
            len(rows) if semantic_clarifier_calls is None else semantic_clarifier_calls
        ),
        "query_developer_initial_attempts": len(rows),
        "query_developer_first_pass_query": sum(row["first_pass_status"] == "QUERY" for row in rows),
        "query_developer_first_pass_technical_valid": len(first_pass_valid),
        "senior_reviews": len(senior_reviews),
        "final_approved": len(final_approved),
        "revision_requested": len(revisions),
        "repair_success": len(repaired),
        "needs_clarification_final": sum(row["final_status"] == "NEEDS_CLARIFICATION" for row in rows),
        "max_revisions_reached": sum(row["final_status"] == "MAX_REVISIONS_REACHED" for row in rows),
        "technical_valid_final": sum(row["technical_valid"] for row in rows),
        "validation_error_counts": dict(Counter(
            error
            for row in rows
            for error in (row["final_validation"] or {}).get("all_errors", [])
        )),
        "latency_ms": {
            "average_case": round(sum(row["duration_ms"] for row in rows) / len(rows), 2)
            if rows else 0,
        },
    }


def assert_runner_contract() -> None:
    assert_phase42_contract()
    cases = _load_cases(Path(__file__).with_name("direct_sqlalchemy_phase412_cases.jsonl"))
    assert len(cases) == 24
    assert len({case["id"] for case in cases}) == 24
    assert "FUNCTIONAL_ANALYST_ONLY" in {"FUNCTIONAL_ANALYST_ONLY", "QUERY_DEVELOPER_ONLY", "AGENT_TEAM"}


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
    assert len(cases) == 24
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
        "sqlalchemy_query_developer": os.getenv("SQLALCHEMY_QUERY_DEVELOPER_MODEL", "gpt-4o-mini"),
        "senior_query_reviewer": os.getenv("SENIOR_QUERY_REVIEWER_MODEL", "gpt-4o-mini"),
    }
    llm = RoleModels(model_config)
    all_rows: list[dict[str, Any]] = []
    if resume_functional_analysis is not None:
        analyst_rows = _load_cases(resume_functional_analysis)
        if len(analyst_rows) != 24:
            raise ValueError("The functional analyst run must contain exactly 24 rows")
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
                    mode=mode_name, cases=cases, graph=graph, models=model_config, llm=llm
                )
                for row in mode_rows:
                    row["repetition"] = repetition
                all_rows.extend(mode_rows)
    developer_rows = [row for row in all_rows if row["mode"] == "QUERY_DEVELOPER_ONLY"]
    team_rows = [row for row in all_rows if row["mode"] == "AGENT_TEAM"]
    metrics = {
        "runner_version": RUNNER_VERSION,
        "cases": len(cases),
        "repetitions": repetitions,
        "executions": len(all_rows),
        "query_developer_only": (
            _metrics(
                developer_rows,
                "QUERY_DEVELOPER_ONLY",
                semantic_clarifier_calls=0 if resume_functional_analysis else None,
            )
            if developer_rows
            else None
        ),
        "agent_team": _metrics(team_rows, "AGENT_TEAM") if team_rows else None,
        "team_approval_uplift_vs_first_pass": (
            _metrics(team_rows, "AGENT_TEAM")["final_approved"]
            - _metrics(developer_rows, "QUERY_DEVELOPER_ONLY")["query_developer_first_pass_technical_valid"]
            if team_rows and developer_rows else None
        ),
    }
    manifest = {
        "runner_version": RUNNER_VERSION,
        "model_by_role": model_config,
        "cases": len(cases),
        "repetitions": repetitions,
        "mode": mode,
        "resumed_from_functional_analysis": str(resume_functional_analysis) if resume_functional_analysis else None,
        "selected_case_ids": [case["id"] for case in cases],
        "source_date": "2026-08-30",
        "timezone": "UTC",
        "retries": 0,
        "mcp": False,
        "database_execution": False,
        "max_repair_attempts": 1,
        "pipeline": "semantic clarifier -> SQLAlchemy query developer -> deterministic gate -> senior -> bounded repair",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in all_rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "metrics": metrics}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--mode", choices=("analyst", "developer", "team", "both"), default="both")
    parser.add_argument("--resume-functional-analysis", type=Path)
    args = parser.parse_args()
    run(args.cases, args.output_dir, args.repetitions, args.limit, args.mode, args.resume_functional_analysis)


if __name__ == "__main__":
    main()
