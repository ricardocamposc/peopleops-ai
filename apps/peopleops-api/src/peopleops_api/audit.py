from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from peopleops_api.models import AnalysisInteraction


def transition(
    session: Session,
    interaction: AnalysisInteraction,
    *,
    stage: str,
    status: str,
    error_type: str | None = None,
    error_detail: str | None = None,
    snapshots: dict[str, Any] | None = None,
) -> AnalysisInteraction:
    event = {
        "stage": stage,
        "status": status,
        "at": datetime.now(UTC).isoformat(),
        "error_type": error_type,
    }
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
    session.add(interaction)
    return interaction
