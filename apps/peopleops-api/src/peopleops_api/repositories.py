from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from peopleops_api.models import AnalysisInteraction, Conversation


def create_interaction(
    session: Session,
    *,
    question: str,
    conversation_id: UUID | None,
    created_by: str | None,
    metadata: dict,
) -> AnalysisInteraction:
    conversation = None
    if conversation_id:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise LookupError("conversation not found")
    else:
        conversation = Conversation(created_by=created_by, metadata_=metadata)
        session.add(conversation)
        session.flush()
    interaction = AnalysisInteraction(
        conversation_id=conversation.id, question=question, stage_history=[]
    )
    session.add(interaction)
    session.flush()
    from peopleops_api.audit import transition

    transition(session, interaction, stage="received", status="received")
    session.commit()
    session.refresh(interaction)
    return interaction


def get_interaction(session: Session, request_id: UUID) -> AnalysisInteraction | None:
    return session.scalar(
        select(AnalysisInteraction).where(AnalysisInteraction.request_id == request_id)
    )
