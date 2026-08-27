from dataclasses import dataclass
from uuid import uuid4

import pytest

from peopleops_api.analysis_contracts import AnalysisPlan, SemanticRequest, StructuredAnswer
from peopleops_api.analysis_workflow import AnalysisWorkflow
from peopleops_api.mcp_contracts import SecurityContext
from peopleops_api.models import AnalysisInteraction
from peopleops_api.repositories import (
    create_human_review,
    get_human_review,
    record_human_review_decision,
)
from peopleops_api.query_contracts import QuerySelect


@dataclass
class ReviewModel:
    outputs: list[object]
    model_name: str = "fake-review-model"

    def parse(self, *, purpose, instructions, output_model):
        output = self.outputs.pop(0)
        assert isinstance(output, output_model)
        return output


def _paused_interaction(db_session) -> AnalysisInteraction:
    interaction = AnalysisInteraction(
        request_id=uuid4(),
        question="Should this restricted analysis proceed?",
        stage_history=[],
    )
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session,
        gateway=_Gateway(),
        model=ReviewModel(
            [
                SemanticRequest(
                    goal="restricted analysis",
                    required_capabilities=["workforce"],
                    entities=["employee"],
                    sensitivity="restricted",
                    requires_human_review=True,
                ),
                AnalysisPlan(
                    goal="restricted analysis",
                    queries=[
                        {
                            "purpose": "workforce",
                            "query": {
                                "entities": ["employee"],
                                "select": [QuerySelect(field="employee.employee_code")],
                            },
                        }
                    ],
                ),
            ]
        ),
        security=SecurityContext(),
    ).run(interaction)
    assert result.status == "pending_human_review"
    assert result.completed_at is None
    assert result.human_review_id is not None
    return result


class _Gateway:
    def discover_catalog(self, *, request_id, security):
        from reference_mcp_server.discovery import build_catalog

        return build_catalog()

    def validate_query(self, query, *, request_id, security):
        from peopleops_api.query_contracts import QueryValidation

        return QueryValidation(
            request_id=request_id,
            valid=True,
            query_hash="review-query",
            catalog_version="2026.08",
        )

    def execute_query(self, query, *, request_id, security):
        from peopleops_api.query_contracts import QueryResult, QueryValidation

        return QueryResult(
            request_id=request_id,
            validation=QueryValidation(
                request_id=request_id,
                valid=True,
                query_hash="review-query",
                catalog_version="2026.08",
            ),
            columns=["employee_code"],
            rows=[{"employee_code": "E001"}],
        )


def test_human_review_creation_is_idempotent_and_snapshot_is_logically_immutable(db_session):
    interaction = AnalysisInteraction(request_id=uuid4(), question="Review this", stage_history=[])
    db_session.add(interaction)
    db_session.commit()
    recommendation = {"summary": "review", "nested": {"value": 1}}
    evidence = [{"type": "structured_data", "result": {"rows": [{"value": 1}]}}]

    first = create_human_review(
        db_session,
        interaction,
        reason="restricted",
        recommendation_snapshot=recommendation,
        evidence_snapshot=evidence,
    )
    second = create_human_review(
        db_session,
        interaction,
        reason="different reason",
        recommendation_snapshot={"summary": "different"},
        evidence_snapshot=[],
    )
    recommendation["nested"]["value"] = 2
    evidence[0]["result"]["rows"][0]["value"] = 2
    db_session.commit()

    persisted = get_human_review(db_session, first.id)
    assert second.id == first.id
    assert persisted.recommendation_snapshot["nested"]["value"] == 1
    assert persisted.evidence_snapshot[0]["result"]["rows"][0]["value"] == 1


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [("reject", "completed"), ("needs_information", "insufficient_data")],
)
def test_reject_and_needs_information_resume_same_request_id(db_session, decision, expected_status):
    interaction = _paused_interaction(db_session)
    review = get_human_review(db_session, interaction.human_review_id)

    recorded, audit_row, created = record_human_review_decision(
        db_session,
        review.id,
        decision=decision,
        reviewed_by="reviewer@example.test",
        comments="Audited decision",
    )
    db_session.commit()
    assert created is True
    assert audit_row.decision == decision
    assert recorded.status == decision
    assert interaction.status == "pending_human_review"

    result = AnalysisWorkflow(
        session=db_session,
        gateway=_Gateway(),
        model=ReviewModel([]),
        security=SecurityContext(),
    ).run(interaction)

    assert result.request_id == interaction.request_id
    assert result.status == expected_status
    assert result.response["warnings"]
    assert [event["stage"] for event in result.stage_history][-2:] == [
        "human_review",
        "synthesis",
    ]


def test_approve_resumes_and_is_idempotent(db_session):
    interaction = _paused_interaction(db_session)
    review = get_human_review(db_session, interaction.human_review_id)
    _, first_row, created = record_human_review_decision(
        db_session,
        review.id,
        decision="approve",
        reviewed_by="reviewer@example.test",
        comments=None,
    )
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=_Gateway(),
        model=ReviewModel([StructuredAnswer(answer="Approved analysis.")]),
        security=SecurityContext(),
    ).run(interaction)
    _, second_row, second_created = record_human_review_decision(
        db_session,
        review.id,
        decision="approve",
        reviewed_by="reviewer@example.test",
        comments=None,
    )

    assert created is True
    assert second_created is False
    assert second_row.id == first_row.id
    assert result.request_id == interaction.request_id
    assert result.status == "completed"
    assert result.response["answer"] == "Approved analysis."


def test_different_second_decision_is_rejected(db_session):
    interaction = _paused_interaction(db_session)
    review = get_human_review(db_session, interaction.human_review_id)
    record_human_review_decision(
        db_session,
        review.id,
        decision="reject",
        reviewed_by="reviewer@example.test",
        comments=None,
    )
    db_session.commit()

    with pytest.raises(ValueError, match="different decision"):
        record_human_review_decision(
            db_session,
            review.id,
            decision="approve",
            reviewed_by="other@example.test",
            comments=None,
        )
