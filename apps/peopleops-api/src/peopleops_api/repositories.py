from datetime import UTC, datetime
from copy import deepcopy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from peopleops_api.models import (
    AnalysisInteraction,
    Conversation,
    HumanReviewDecision,
    HumanReviewRequest,
)


def create_interaction(
    session: Session,
    *,
    question: str,
    conversation_id: UUID | None,
    created_by: str | None,
    metadata: dict,
    request_id: UUID | None = None,
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
        conversation_id=conversation.id, question=question, stage_history=[], request_id=request_id
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


def list_interactions(session: Session, *, limit: int = 50) -> list[AnalysisInteraction]:
    """Return recent analyses for the user-facing history view."""
    bounded_limit = max(1, min(limit, 100))
    statement = (
        select(AnalysisInteraction)
        .order_by(AnalysisInteraction.created_at.desc())
        .limit(bounded_limit)
    )
    return list(session.scalars(statement).all())


def create_human_review(
    session: Session,
    interaction: AnalysisInteraction,
    *,
    reason: str,
    recommendation_snapshot: dict,
    evidence_snapshot: list,
) -> HumanReviewRequest:
    # Lock the parent interaction so concurrent workflow retries cannot both
    # pass the existence check before the unique constraint is evaluated.
    locked_interaction = session.get(AnalysisInteraction, interaction.id, with_for_update=True)
    if locked_interaction is None:
        raise LookupError("analysis interaction not found")
    existing = session.scalar(
        select(HumanReviewRequest).where(HumanReviewRequest.analysis_id == locked_interaction.id)
    )
    if existing is not None:
        return existing
    review = HumanReviewRequest(
        analysis_id=locked_interaction.id,
        status="pending",
        reason=reason,
        recommendation_snapshot=deepcopy(recommendation_snapshot),
        evidence_snapshot=deepcopy(evidence_snapshot),
    )
    session.add(review)
    session.flush()
    locked_interaction.human_review_id = review.id
    locked_interaction.human_review_status = "pending"
    return review


def get_human_review(session: Session, review_id: UUID, *, for_update: bool = False):
    statement = select(HumanReviewRequest).where(HumanReviewRequest.id == review_id)
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def list_human_reviews(
    session: Session, *, status: str | None = "pending"
) -> list[HumanReviewRequest]:
    statement = select(HumanReviewRequest).order_by(HumanReviewRequest.requested_at)
    if status is not None:
        statement = statement.where(HumanReviewRequest.status == status)
    return list(session.scalars(statement).unique().all())


def record_human_review_decision(
    session: Session,
    review_id: UUID,
    *,
    decision: str,
    reviewed_by: str,
    comments: str | None,
) -> tuple[HumanReviewRequest, HumanReviewDecision, bool]:
    review = get_human_review(session, review_id, for_update=True)
    if review is None:
        raise LookupError("human review not found")
    existing = session.scalar(
        select(HumanReviewDecision).where(HumanReviewDecision.review_request_id == review.id)
    )
    if existing is not None:
        if existing.decision != decision:
            raise ValueError("human review already has a different decision")
        return review, existing, False
    if review.status != "pending":
        raise ValueError("human review is not pending")
    decision_row = HumanReviewDecision(
        review_request_id=review.id,
        decision=decision,
        reviewed_by=reviewed_by,
        comments=comments,
    )
    session.add(decision_row)
    review.status = decision
    review.decision = decision
    review.reviewed_by = reviewed_by
    review.comments = comments
    review.reviewed_at = datetime.now(UTC)
    interaction = session.get(AnalysisInteraction, review.analysis_id)
    if interaction is not None:
        interaction.human_review_status = decision
        from peopleops_api.audit import transition

        transition(
            session,
            interaction,
            stage="human_review",
            status=decision,
            snapshots={"human_review_status": decision},
        )
        # The review decision is an event inside the paused execution.  The
        # interaction remains resumable until the workflow consumes it.
        interaction.status = "pending_human_review"
    session.flush()
    return review, decision_row, True
