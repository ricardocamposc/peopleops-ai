from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from peopleops_api.models import AnalysisInteraction
from peopleops_api.observability import safe_error_detail


def transition(
    session: Session,
    interaction: AnalysisInteraction,
    *,
    stage: str,
    status: str,
    error_type: str | None = None,
    error_detail: str | None = None,
    snapshots: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    graph_node: str | None = None,
) -> AnalysisInteraction:
    if error_detail is not None:
        error_detail = safe_error_detail(error_detail)
    event = {
        "stage": stage,
        "status": status,
        "at": datetime.now(UTC).isoformat(),
        "error_type": error_type,
    }
    event["graph_node"] = graph_node or stage
    interaction.stage_history = [*(interaction.stage_history or []), event]
    interaction.current_stage = stage
    interaction.status = status
    if error_type is not None:
        interaction.error_type = error_type
        interaction.error_detail = error_detail
    for field, value in (snapshots or {}).items():
        if not hasattr(interaction, field):
            raise ValueError(f"unsupported audit snapshot: {field}")
        setattr(interaction, field, value)
    trace = interaction.evaluation_trace or {}
    audit_trail = trace.setdefault("audit_trail", [])
    audit_event = {
        "role": "workflow_transition",
        "stage": stage,
        "status": status,
        "snapshots": {**(snapshots or {}), **(context or {})},
        "at": event["at"],
        "sequence": len(audit_trail) + 1,
    }
    audit_event["graph_node"] = graph_node or stage
    audit_trail.append(audit_event)
    interaction.evaluation_trace = trace
    session.add(interaction)
    return interaction


def synchronize_workflow_audit(interaction: AnalysisInteraction) -> None:
    """Ensure every durable stage transition is present in the audit trail.

    LangGraph state values can contain an older copy of ``evaluation_trace``
    when a node returns.  ``stage_history`` is the workflow's durable source
    of truth, so reconcile only missing transition events at the persistence
    boundary instead of reconstructing or reordering model/tool events.
    """
    trace = interaction.evaluation_trace or {}
    audit_trail = trace.setdefault("audit_trail", [])
    known = {
        (event.get("at"), event.get("stage"), event.get("status"))
        for event in audit_trail
        if event.get("role") == "workflow_transition"
    }
    for stage_event in interaction.stage_history or []:
        key = (stage_event.get("at"), stage_event.get("stage"), stage_event.get("status"))
        if key in known:
            continue
        audit_trail.append(
            {
                "role": "workflow_transition",
                "stage": stage_event.get("stage"),
                "status": stage_event.get("status"),
                "snapshots": {},
                "at": stage_event.get("at"),
                "sequence": len(audit_trail) + 1,
                "graph_node": stage_event.get("graph_node"),
            }
        )
        known.add(key)
    interaction.evaluation_trace = trace
