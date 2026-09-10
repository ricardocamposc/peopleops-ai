"""Run five production PeopleOps analyses and persist viewer-friendly traces."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = Path(__file__).with_name("production_query_programmer_smoke_cases.jsonl")
DEFAULT_BASE_URL = os.getenv("PEOPLEOPS_API_URL", "http://127.0.0.1:8000")


def _load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _post_analysis(base_url: str, case: dict) -> dict:
    payload = {
        "question": case["question"],
        "metadata": {"evaluation_structured_hr": True, "smoke_case_id": case["id"]},
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/v1/analysis",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:  # noqa: S310 - configured local API URL
            created = json.loads(response.read().decode("utf-8"))
        # The POST response is allowed to be a compact representation. The
        # persisted GET is the authoritative source for the complete audit
        # trace, including failed agent attempts and final-stage snapshots.
        request_id = created.get("request_id")
        if request_id:
            with urlopen(  # noqa: S310 - configured local API URL
                f"{base_url.rstrip('/')}/api/v1/analysis/{request_id}", timeout=30
            ) as persisted:
                return json.loads(persisted.read().decode("utf-8"))
        return created
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"PeopleOps API request failed for {case['id']}: {exc}") from exc


def _message(value: dict) -> dict:
    return {
        "type": value.get("type"),
        "content": value.get("content"),
        "tool_calls": value.get("tool_calls", []),
        "tool_call_id": value.get("tool_call_id"),
    }


def _audit_trace(trace: dict, stage_history: list[dict] | None = None) -> list[dict]:
    audit: list[dict] = []
    workflow_events = trace.get("workflow_events", [])
    if not workflow_events:
        workflow_events = [
            {
                "role": "workflow_transition",
                "stage": item.get("stage"),
                "status": item.get("status"),
                "snapshots": {
                    "error_type": item.get("error_type"),
                    "error_detail": item.get("error_detail"),
                },
                "sequence": index + 1,
            }
            for index, item in enumerate(stage_history or [])
        ]
    for event in workflow_events:
        audit.append({
            "role": "workflow_transition",
            "stage": event.get("stage"),
            "status": event.get("status"),
            "snapshots": event.get("snapshots") or {},
            "sequence": event.get("sequence"),
        })
    functional_audit: list[dict] = []
    for event in trace.get("functional_analyst", []):
        if event.get("role") == "functional_analyst_tool":
            functional_audit.append({
                "role": "functional_analyst_tool",
                "round": event.get("round"),
                "tool_name": event.get("tool"),
                "input": event.get("input"),
                "output": event.get("output"),
            })
        elif event.get("role") == "functional_analyst_error":
            functional_audit.append({
                "role": "functional_analyst_error",
                "call_number": event.get("call_number"),
                "round": event.get("round"),
                "model": event.get("model"),
                "prompt_template": event.get("prompt_template"),
                "rendered_system_prompt": event.get("rendered_system_prompt"),
                "input": event.get("input"),
                "rendered_messages": (event.get("input") or {}).get("messages", []),
                "error": event.get("error"),
            })
        else:
            functional_audit.append({
                "role": "functional_analyst",
                "call_number": event.get("call_number"),
                "round": event.get("round"),
                "model": event.get("model"),
                "prompt_template": event.get("prompt_template"),
                "rendered_system_prompt": event.get("rendered_system_prompt"),
                "input": event.get("input"),
                "rendered_messages": (event.get("input") or {}).get("messages", []),
                "output": event.get("output"),
            })
    programmer_audit: list[dict] = []
    senior_audit: list[dict] = []
    senior_events = trace.get("senior_reviewer", [])
    for attempt_index, attempt in enumerate(trace.get("query_programmer_agent", [])):
        model_events = attempt.get("model_events", [])
        tool_events = attempt.get("tool_events", [])
        tools_by_round: dict[int, list[dict]] = {}
        for event in tool_events:
            tools_by_round.setdefault(event.get("round") or 0, []).append(event)
        previous_message_count = 0
        for event in model_events:
            messages = [_message(item) for item in event.get("request_messages", [])]
            programmer_audit.append({
                "role": "query_programmer_model",
                "round": event.get("round"),
                "prompt_template": attempt.get("prompt_template"),
                "rendered_system_prompt": attempt.get("rendered_system_prompt"),
                "input": {"messages": messages},
                "incremental_input": {"messages": messages[previous_message_count:]},
                "rendered_messages": messages,
                "output": _message(event.get("response_message") or {}),
            })
            previous_message_count = len(messages)
            for tool_event in tools_by_round.get(event.get("round") or 0, []):
                programmer_audit.append({
                    "role": "query_programmer_tool",
                    "round": tool_event.get("round"),
                    "tool_name": tool_event.get("tool"),
                    "input": tool_event.get("input"),
                    "output": tool_event.get("output"),
                })
        if attempt_index < len(senior_events):
            event = senior_events[attempt_index]
            messages = event.get("input", {}).get("messages", [])
            senior_audit.append({
                "role": "senior_query_reviewer",
                "call_number": event.get("call_number"),
                "model": event.get("model"),
                "prompt_template": event.get("prompt_template"),
                "rendered_system_prompt": event.get("rendered_system_prompt"),
                "input": event.get("input"),
                "incremental_input": {"messages": messages},
                "rendered_messages": messages,
                "output": event.get("output"),
            })
    # Stage history contains both the entry and exit transition for most
    # nodes.  Keep both, but place them around the events that caused them so
    # the viewer represents the actual graph traversal instead of showing all
    # LangGraph bookkeeping before the agent calls.
    workflow = audit
    first_planning = next(
        (index for index, event in enumerate(workflow)
         if event.get("stage") == "planning" and event.get("status") == "running"),
        None,
    )
    if first_planning is None:
        return _collapse_workflow_events(
            [*functional_audit, *workflow, *programmer_audit, *senior_audit]
        )

    first_understanding = next(
        (index for index, event in enumerate(workflow)
         if event.get("stage") == "understanding" and event.get("status") == "running"),
        None,
    )
    prefix_end = first_understanding + 1 if first_understanding is not None else first_planning
    prefix = workflow[:prefix_end]
    before_planning = workflow[prefix_end:first_planning]
    planning_and_after = workflow[first_planning:]
    first_senior = next(
        (index for index, event in enumerate(planning_and_after)
         if event.get("stage") == "senior_review" and event.get("status") == "running"),
        None,
    )
    if first_senior is None:
        return _collapse_workflow_events(
            [*prefix, *functional_audit, *before_planning,
             *planning_and_after, *programmer_audit, *senior_audit]
        )

    planning_start = planning_and_after[:1]
    after_planning_start = planning_and_after[1:first_senior]
    senior_and_after = planning_and_after[first_senior:]
    senior_completed = next(
        (index for index, event in enumerate(senior_and_after)
         if event.get("stage") == "senior_review" and event.get("status") == "completed"),
        None,
    )
    if senior_completed is None:
        return _collapse_workflow_events(
            [*prefix, *functional_audit, *before_planning, *planning_start,
             *programmer_audit, *after_planning_start,
             *senior_audit, *senior_and_after]
        )

    after_senior = senior_and_after[senior_completed:]
    return _collapse_workflow_events([
        *prefix,
        *functional_audit,
        *before_planning,
        *planning_start,
        *programmer_audit,
        *after_planning_start,
        *senior_audit,
        *after_senior,
    ])


def _collapse_workflow_events(events: list[dict]) -> list[dict]:
    """Collapse adjacent running/completed transitions for one graph node."""
    collapsed: list[dict] = []
    for event in events:
        if (
            collapsed
            and event.get("role") == "workflow_transition"
            and collapsed[-1].get("role") == "workflow_transition"
            and event.get("stage") == collapsed[-1].get("stage")
        ):
            previous = collapsed[-1]
            previous["lifecycle"] = [
                *previous.get("lifecycle", [previous.get("status")]),
                event.get("status"),
            ]
            previous["status"] = event.get("status")
            if event.get("snapshots"):
                previous["snapshots"] = event["snapshots"]
            continue
        if event.get("role") == "workflow_transition":
            event = {**event, "lifecycle": [event.get("status")]}
        collapsed.append(event)
    return collapsed


def _row(case: dict, response: dict, started: float) -> dict:
    trace = response.get("evaluation_trace") or {}
    agent_trace = trace.get("query_programmer_agent", [])
    functional_events = trace.get("functional_analyst", [])
    functional_analysis = trace.get("semantic_request")
    if functional_analysis is None:
        functional_analysis = next(
            (
                json.loads(event["output"]["content"])
                for event in reversed(functional_events)
                if isinstance(event.get("output"), dict)
                and isinstance(event["output"].get("content"), str)
                and event["output"].get("content")
            ),
            None,
        )
    metadata = agent_trace[-1] if agent_trace else {}
    stage_history = response.get("stage_history", [])
    audit_trace = trace.get("audit_trail") or _audit_trace(trace, stage_history)
    model_events = [event for event in audit_trace if event["role"] == "query_programmer_model"]
    tool_events = [event for event in audit_trace if event["role"] == "query_programmer_tool"]
    planning = trace.get("planning_attempts", [])
    return {
        "id": case["id"],
        "language": case.get("language", "es"),
        "category": case.get("category"),
        "mode": "PRODUCTION_QUERY_PROGRAMMER_SUBGRAPH",
        "question": case["question"],
        "query_task": trace.get("semantic_request") or functional_analysis,
        "functional_analysis": functional_analysis,
        "query_programmer_output": planning[-1] if planning else None,
        "programmer_metadata": {
            **metadata,
            "agent_tool_rounds": metadata.get("model_rounds", 0),
            "internal_tool_calls": metadata.get("tool_calls", 0),
            "internal_validation_attempts": metadata.get("validation_calls", 0),
        },
        "model_events": model_events,
        "tool_events": tool_events,
        "audit_trail": audit_trace,
        "senior_reviews": trace.get("senior_reviews", []),
        "validation": trace.get("provider_validations", []),
        "stage_history": response.get("stage_history", []),
        "technical_valid": response.get("status") == "completed",
        "final_status": response.get("status"),
        "response": response.get("response"),
        "models": {"query_programmer": metadata.get("model")},
        "error_type": response.get("error_type"),
        "error_detail": response.get("error_detail"),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def run(
    *, cases_path: Path, output_dir: Path, base_url: str,
    case_ids: set[str] | None = None, allow_case_count: bool = False,
    limit: int | None = None,
) -> None:
    cases = _load_cases(cases_path)
    if case_ids is not None:
        unknown = case_ids.difference(case["id"] for case in cases)
        if unknown:
            raise ValueError(f"unknown case IDs: {sorted(unknown)}")
        cases = [case for case in cases if case["id"] in case_ids]
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be positive")
        cases = cases[:limit]
    if case_ids is None and not allow_case_count and len(cases) != 5:
        raise ValueError(f"smoke dataset must contain exactly 5 cases, found {len(cases)}")
    if not cases:
        raise ValueError("at least one case is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_type": "production_query_programmer_smoke",
        "phase": "phase44",
        "test_description": (
            f"Phase 4.4 — Production Query Programmer — baseline {len(cases)} cases"
            if allow_case_count
            else "Phase 4.4 — Production Query Programmer — selected case smoke"
            if case_ids is not None
            else "Phase 4.4 — Production Query Programmer — complete 5-case smoke"
        ),
        "cases": len(cases),
        "status": "RUNNING",
        "api_base_url": base_url,
        "pipeline": "Functional Analyst -> MCP catalog -> Query Programmer subgraph -> Senior Reviewer -> MCP execution -> synthesize",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output_dir / "raw_responses.jsonl").write_text("", encoding="utf-8")
    rows: list[dict] = []
    try:
        for case in cases:
            started = time.perf_counter()
            row = _row(case, _post_analysis(base_url, case), started)
            artifact = f"{case['id']}.json"
            (output_dir / artifact).write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            rows.append(row)
            with (output_dir / "raw_responses.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"id": case["id"], "artifact": artifact, "test_description": case["question"]}, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            manifest["completed_cases"] = len(rows)
            (output_dir / "metrics.json").write_text(json.dumps(_metrics(rows), indent=2) + "\n", encoding="utf-8")
            (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except Exception:
        manifest["status"] = "INTERRUPTED"
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        raise
    manifest["status"] = "COMPLETE"
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _metrics(rows: list[dict]) -> dict:
    return {
        "cases": len(rows),
        "completed": sum(row.get("final_status") == "completed" for row in rows),
        "model_rounds": sum(row.get("programmer_metadata", {}).get("model_rounds", 0) for row in rows),
        "tool_calls": sum(row.get("programmer_metadata", {}).get("tool_calls", 0) for row in rows),
        "validation_calls": sum(row.get("programmer_metadata", {}).get("validation_calls", 0) for row in rows),
        "senior_reviews": sum(bool(row.get("senior_reviews")) for row in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--allow-case-count",
        action="store_true",
        help="Allow a dataset size other than the default five-case smoke",
    )
    args = parser.parse_args()
    run(
        cases_path=args.cases,
        output_dir=args.output_dir,
        base_url=args.base_url,
        case_ids=set(args.case_ids) if args.case_ids else None,
        allow_case_count=args.allow_case_count,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
