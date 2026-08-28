"""Export persisted API evidence for one Policy RAG evaluation run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

API_SRC = Path(__file__).resolve().parents[1] / "apps" / "peopleops-api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))


def _json_value(value):
    if isinstance(value, UUID):
        return str(value)
    return value


def export_run(run_id: str) -> dict:
    from peopleops_api.db import SessionLocal
    from peopleops_api.models import AnalysisInteraction, Conversation

    with SessionLocal() as session:
        conversations = list(
            session.scalars(
                select(Conversation)
                .where(Conversation.metadata_.contains({"evaluation_run_id": run_id}))
                .order_by(Conversation.created_at)
            ).all()
        )
        conversation_ids = [item.id for item in conversations]
        interactions = []
        if conversation_ids:
            interactions = list(
                session.scalars(
                    select(AnalysisInteraction)
                    .where(AnalysisInteraction.conversation_id.in_(conversation_ids))
                    .order_by(AnalysisInteraction.created_at)
                ).all()
            )

        records = []
        for interaction in interactions:
            records.append(
                {
                    "id": _json_value(interaction.id),
                    "request_id": _json_value(interaction.request_id),
                    "conversation_id": _json_value(interaction.conversation_id),
                    "question": interaction.question,
                    "status": interaction.status,
                    "current_stage": interaction.current_stage,
                    "stage_history": interaction.stage_history or [],
                    "semantic_request": interaction.semantic_request,
                    "query_plan": interaction.query_plan,
                    "validation": interaction.validation,
                    "structured_result": interaction.structured_result,
                    "policy_sources": interaction.policy_sources or [],
                    "policy_versions": interaction.policy_versions or [],
                    "evidence": interaction.evidence or [],
                    "response": interaction.response,
                    "warnings": interaction.warnings or [],
                    "model_name": interaction.model_name,
                    "latency_ms": interaction.latency_ms,
                    "error_type": interaction.error_type,
                    "error_detail": interaction.error_detail,
                    "created_at": interaction.created_at.isoformat(),
                    "updated_at": interaction.updated_at.isoformat(),
                    "completed_at": (
                        interaction.completed_at.isoformat()
                        if interaction.completed_at
                        else None
                    ),
                }
            )
        return {
            "run_id": run_id,
            "conversation_count": len(conversations),
            "interaction_count": len(records),
            "conversations": [
                {
                    "id": _json_value(item.id),
                    "metadata": item.metadata_ or {},
                    "created_at": item.created_at.isoformat(),
                }
                for item in conversations
            ],
            "interactions": records,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = export_run(args.run_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("run_id", "conversation_count", "interaction_count")}))


if __name__ == "__main__":
    main()
