"""Run Phase 4.3 agentic Query Programmer experiments with real tool calling."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import direct_sqlalchemy_phase42 as phase42
import direct_sqlalchemy_phase42_runner as phase42_runner
import direct_sqlalchemy_phase43 as phase43

RUNNER_VERSION = "direct-sqlalchemy-phase43-v2"
DATASET_VERSION = "phase42-v1"
DEFAULT_CASES = Path(__file__).with_name("direct_sqlalchemy_phase42_cases.jsonl")


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _programmer_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event for event in state.get("audit_trail", [])
        if event.get("role") == "sqlalchemy_query_developer"
    ]


def _event_agent_rounds(event: dict[str, Any]) -> int:
    """Count actual model turns, not interaction/tool events.

    Phase 4.3 records the model round on every interaction. Multiple tool calls may
    happen in one model turn, so ``len(internal_iterations)`` over-counts rounds.
    """
    rounds = [
        int(item.get("round", 0) or 0)
        for item in event.get("internal_iterations", [])
    ]
    return max(rounds, default=0)


def _agent_metadata(state: dict[str, Any]) -> dict[str, int]:
    events = _programmer_events(state)
    return {
        "agent_tool_rounds": sum(_event_agent_rounds(event) for event in events),
        "agent_submission_attempts": sum(
            int(event.get("agent_submission_attempts", 0) or 0) for event in events
        ),
        "agent_submission_rejections": sum(
            int(event.get("agent_submission_rejections", 0) or 0) for event in events
        ),
    }


def _candidate_metrics(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Derive candidate metrics from validation tool calls only.

    A model may continue requesting validation after the deterministic validation
    budget is exhausted. Those requests are still generated candidates, but they
    are not validator executions. Keeping both counts separate prevents the old
    inconsistency where changed/unchanged candidates could exceed the reported
    number of generated candidates.
    """
    validation_requests: list[dict[str, Any]] = [
        item
        for row in rows
        for item in row.get("internal_iterations", [])
        if item.get("kind") == "VALIDATION_TOOL_CALL"
    ]
    generated = len(validation_requests)
    changed = sum(item.get("candidate_changed") is True for item in validation_requests)
    unchanged = sum(item.get("candidate_changed") is False for item in validation_requests)
    initial = sum(item.get("candidate_changed") is None for item in validation_requests)
    budget_rejected = sum(
        item.get("result", {}).get("stage") == "TOOL_BUDGET"
        for item in validation_requests
    )
    executed = generated - budget_rejected
    return {
        "candidate_validation_requests": generated,
        "candidates_generated": generated,
        "candidates_initial": initial,
        "candidates_changed": changed,
        "candidates_unchanged": unchanged,
        "candidate_validations_executed": executed,
        "candidate_validation_budget_rejections": budget_rejected,
    }


def _row(case: dict[str, Any], state: dict[str, Any], started: float) -> dict[str, Any]:
    base = phase42_runner._row_from_state(
        case=case,
        mode="AGENT_TEAM",
        state={key: value for key, value in state.items() if key != "_llm"},
        started=started,
    )
    base.update(_agent_metadata(state))
    base["technical_generation_failed"] = base["final_status"] == "TECHNICAL_GENERATION_FAILED"
    return base


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base = phase42_runner._metrics(rows, "AGENT_TEAM")
    base["runner_version"] = RUNNER_VERSION

    candidate_metrics = _candidate_metrics(rows)

    # Phase 4.2 names are kept for comparability, but in Phase 4.3 they are
    # normalized from model-initiated validation requests rather than generic
    # interaction events.
    base["internal_candidates_generated"] = candidate_metrics["candidates_generated"]
    base["internal_candidates_changed"] = candidate_metrics["candidates_changed"]
    base["internal_candidates_unchanged"] = candidate_metrics["candidates_unchanged"]

    base["agent_tool_calling"] = {
        "model_initiated_tool_calls": sum(row.get("internal_tool_calls", 0) for row in rows),
        "validation_attempts": sum(row.get("internal_validation_attempts", 0) for row in rows),
        "tool_rounds": sum(row.get("agent_tool_rounds", 0) for row in rows),
        "submission_attempts": sum(row.get("agent_submission_attempts", 0) for row in rows),
        "submission_rejections": sum(row.get("agent_submission_rejections", 0) for row in rows),
        "self_repair_attempts": sum(row.get("internal_self_repair_attempts", 0) for row in rows),
        "self_repair_success": sum(row.get("internal_self_repair_success", 0) for row in rows),
        "technical_generation_failed": sum(
            row.get("technical_generation_failed", False) for row in rows
        ),
        **candidate_metrics,
    }
    base["final"]["technical_generation_failed"] = sum(
        row.get("final_status") == "TECHNICAL_GENERATION_FAILED" for row in rows
    )
    return base


def assert_runner_contract() -> None:
    phase43.assert_phase43_contract()
    cases = _load_cases(DEFAULT_CASES)
    assert len(cases) >= 30
    assert len({case["id"] for case in cases}) == len(cases)

    synthetic = [{
        "internal_iterations": [
            {
                "kind": "VALIDATION_TOOL_CALL",
                "round": 1,
                "candidate_changed": None,
                "result": {"valid": False, "stats": {}},
            },
            {
                "kind": "VALIDATION_TOOL_CALL",
                "round": 2,
                "candidate_changed": True,
                "result": {"valid": False, "stage": "TOOL_BUDGET"},
            },
            {"kind": "SUBMISSION_ACCEPTED", "round": 3},
        ]
    }]
    counts = _candidate_metrics(synthetic)
    assert counts["candidates_generated"] == 2
    assert counts["candidates_initial"] == 1
    assert counts["candidates_changed"] == 1
    assert counts["candidates_unchanged"] == 0
    assert counts["candidate_validations_executed"] == 1
    assert counts["candidate_validation_budget_rejections"] == 1
    assert (
        counts["candidates_initial"]
        + counts["candidates_changed"]
        + counts["candidates_unchanged"]
        == counts["candidates_generated"]
    )


def run(
    *, cases_path: Path, output_dir: Path, case_ids: list[str] | None = None,
    limit: int | None = None,
) -> None:
    assert_runner_contract()
    cases = _load_cases(cases_path)
    if case_ids:
        requested = set(case_ids)
        cases = [case for case in cases if case["id"] in requested]
        missing = requested - {case["id"] for case in cases}
        if missing:
            raise ValueError(f"Unknown case ids: {sorted(missing)}")
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be positive")
        cases = cases[:limit]
    if not cases:
        raise ValueError("No Phase 4.3 cases selected")

    output_dir.mkdir(parents=True, exist_ok=True)
    model_config = {
        "semantic_clarifier": os.getenv("SEMANTIC_CLARIFIER_MODEL", "gpt-4o-mini"),
        "sqlalchemy_query_developer": os.getenv("SQLALCHEMY_QUERY_DEVELOPER_MODEL", "gpt-4o-mini"),
        "senior_query_reviewer": os.getenv("SENIOR_QUERY_REVIEWER_MODEL", "gpt-4o-mini"),
    }
    runtime = phase43.LangChainToolCallingRuntime(model_config)
    graph = phase43.build_graph()
    rows: list[dict[str, Any]] = []

    for case in cases:
        started = time.perf_counter()
        state = phase43.initial_state(
            mode="AGENT_TEAM", question=case["question"], llm=runtime
        )
        state["models"] = model_config
        result = graph.invoke(state)
        rows.append(_row(case, result, started))

    metrics = _metrics(rows)
    manifest = {
        "runner_version": RUNNER_VERSION,
        "dataset_version": DATASET_VERSION,
        "dataset_path": str(cases_path),
        "dataset_sha256": _sha256(cases_path.read_bytes()),
        "git_commit_sha": _git_commit(),
        "model_by_role": model_config,
        "selected_case_ids": [case["id"] for case in cases],
        "query_programmer_mode": "MODEL_INITIATED_TOOL_CALLING",
        "query_programmer_tools": [
            "validate_sqlalchemy_candidate",
            "SubmitQueryProgrammerResult",
        ],
        "max_candidate_validations_per_outer_attempt": phase43.MAX_CANDIDATE_VALIDATIONS,
        "max_agent_tool_rounds_per_outer_attempt": phase43.MAX_AGENT_TOOL_ROUNDS,
        "max_external_technical_repair_attempts": phase42.MAX_TECHNICAL_REPAIR_ATTEMPTS,
        "max_semantic_revision_attempts": phase42.MAX_SEMANTIC_REVISION_ATTEMPTS,
        "external_validator": True,
        "senior_reviewer": True,
        "mcp": False,
        "database_execution": False,
        "source_date": phase42.REFERENCE_CONTEXT["reference_date"],
        "timezone": phase42.REFERENCE_CONTEXT["timezone"],
        "candidate_metric_semantics": {
            "candidates_generated": "model validation-tool requests carrying a candidate",
            "candidates_initial": "first candidate in each Query Programmer invocation",
            "candidates_changed": "validation requests whose candidate differs from the previous request in the same invocation",
            "candidates_unchanged": "validation requests whose candidate equals the previous request in the same invocation",
            "candidate_validations_executed": "requests that actually reached deterministic validation",
            "candidate_validation_budget_rejections": "validation requests rejected because the per-invocation validation budget was exhausted",
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "metrics": metrics}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--case-ids", nargs="*")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run(
        cases_path=args.cases,
        output_dir=args.output_dir,
        case_ids=args.case_ids,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
