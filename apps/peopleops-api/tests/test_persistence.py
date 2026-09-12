from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from peopleops_api.audit import transition
from peopleops_api.main import app
from peopleops_api.models import AnalysisInteraction, Conversation
from peopleops_api.repositories import (
    create_human_review,
    create_interaction,
    get_interaction,
    record_human_review_decision,
)


def test_interaction_is_persisted_with_unique_request_and_conversation(db_session) -> None:
    first = create_interaction(
        db_session,
        question="First question",
        conversation_id=None,
        created_by="tester",
        metadata={"source": "test"},
    )
    second = create_interaction(
        db_session,
        question="Follow-up",
        conversation_id=first.conversation_id,
        created_by=None,
        metadata={},
    )

    assert first.request_id != second.request_id
    assert first.conversation_id == second.conversation_id
    assert len(first.stage_history) == 1
    assert first.stage_history[0]["stage"] == "received"


def test_transition_appends_and_persists_safe_error(db_session) -> None:
    interaction = AnalysisInteraction(
        conversation=Conversation(metadata_={}),
        question="Test failure",
        stage_history=[],
    )
    db_session.add(interaction)
    db_session.flush()
    transition(
        db_session,
        interaction,
        stage="planning",
        status="failed",
        error_type="SYSTEM_ERROR",
        error_detail="safe detail",
    )
    db_session.commit()

    persisted = get_interaction(db_session, interaction.request_id)
    assert persisted is not None
    assert persisted.current_stage == "planning"
    assert persisted.status == "failed"
    assert len(persisted.stage_history) == 1
    assert persisted.error_type == "SYSTEM_ERROR"
    assert persisted.error_detail == "safe detail"


def test_analysis_api_registers_and_reads_interaction(monkeypatch, db_session) -> None:
    from peopleops_api.db import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/analysis",
            json={"question": "Show recent analysis", "created_by": "tester"},
        )
        assert response.status_code == 201
        request_id = response.json()["request_id"]
        read_response = client.get(f"/api/v1/analysis/{request_id}")
        assert read_response.status_code == 200
        assert read_response.json()["status"] in {"failed", "completed", "insufficient_data"}
        assert read_response.json()["stage_history"][0]["status"] == "received"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_analysis_api_lists_recent_interactions(db_session) -> None:
    from peopleops_api.db import get_db

    create_interaction(
        db_session,
        question="History question",
        conversation_id=None,
        created_by="tester",
        metadata={},
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get("/api/v1/analysis?limit=10")
        assert response.status_code == 200
        assert response.json()[0]["question"] == "History question"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_analysis_api_reports_payroll_authorization_as_controlled_restriction(
    monkeypatch, db_session
) -> None:
    from peopleops_api.analysis_workflow import AnalysisWorkflow
    from peopleops_api.db import get_db

    def fake_run(self, interaction):  # noqa: ANN001
        interaction.status = "insufficient_data"
        interaction.current_stage = "finalize_response"
        interaction.error_type = "AUTHORIZATION_ERROR"
        interaction.error_detail = "payroll access requires the hr:payroll scope"
        interaction.response = {
            "answer": "La solicitud requiere permisos adicionales para consultar esos datos.",
            "status": "insufficient_data",
            "facts": [],
            "policies": [],
            "inference": [],
            "key_findings": [],
            "warnings": ["La solicitud requiere permisos adicionales para consultar esos datos."],
        }
        interaction.warnings = interaction.response["warnings"]
        db_session.add(interaction)
        db_session.commit()
        return interaction

    def override_get_db():
        yield db_session

    monkeypatch.setattr(AnalysisWorkflow, "run", fake_run)
    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post(
            "/api/v1/analysis",
            json={"question": "Que trabajadores ganan mas de 1000?", "created_by": "tester"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "insufficient_data"
        assert body["error_type"] == "AUTHORIZATION_ERROR"
        assert "permisos adicionales" in body["response"]["answer"]
        assert "REPEATED_TOOL_FAILURE_NO_PROGRESS" not in str(body)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_analysis_details_api_returns_safe_persisted_trace(db_session) -> None:
    from peopleops_api.db import get_db

    interaction = create_interaction(
        db_session,
        question="Explain this flow",
        conversation_id=None,
        created_by="tester",
        metadata={},
    )
    transition(
        db_session,
        interaction,
        stage="planning",
        status="completed",
        snapshots={
            "semantic_request": {
                "goal": "Explain evidence",
                "required_capabilities": ["structured_data"],
            },
            "query_plan": {
                "goal": "Explain evidence",
                "queries": [{"query": {"entities": ["conceptual_entity"]}}],
                "combination": {"strategy": "independent"},
            },
            "validation": {"semantic_coverage": {"status": "COMPLETE"}},
        },
    )
    interaction.evaluation_trace = {
        "provider_validations": [
            {
                "attempt_number": 1,
                "query_index": 0,
                "accepted": True,
                "query_hash": "abc",
                "prompt_template": "hidden",
                "input": {"messages": ["hidden"]},
            }
        ],
        "provider_executions": [
            {
                "attempt_number": 1,
                "query_index": 0,
                "success": True,
                "row_count": 2,
                "result_verification_status": "VALID",
            }
        ],
        "senior_reviews": [
            {
                "attempt_number": 1,
                "status": "APPROVE",
                "review": {"summary": "Covered"},
                "semantic_coverage": {"status": "COMPLETE"},
            }
        ],
    }
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get(f"/api/v1/analysis/{interaction.request_id}/details")
        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["tool_validations"] == 1
        assert body["summary"]["tool_executions"] == 1
        assert {step["kind"] for step in body["steps"]} >= {"workflow", "analysis", "tool", "review"}
        serialized = str(body)
        assert "hidden" not in serialized
        assert "prompt_template" not in serialized
        assert "input" not in serialized
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_analysis_api_exposes_human_review_comment_in_summary_and_details(db_session) -> None:
    from peopleops_api.db import get_db

    interaction = create_interaction(
        db_session,
        question="Restricted analysis",
        conversation_id=None,
        created_by="tester",
        metadata={},
    )
    interaction.status = "completed"
    interaction.current_stage = "synthesis"
    interaction.response = {"answer": "The reviewer rejected proceeding with this analysis."}
    review = create_human_review(
        db_session,
        interaction,
        reason="Restricted read requires review",
        recommendation_snapshot={"type": "authorization"},
        evidence_snapshot=[],
    )
    record_human_review_decision(
        db_session,
        review.id,
        decision="reject",
        reviewed_by="reviewer@example.test",
        comments="No aprobar porque falta justificacion de negocio.",
    )
    interaction.status = "completed"
    interaction.current_stage = "synthesis"
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.get(f"/api/v1/analysis/{interaction.request_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["human_review"]["decision"] == "reject"
        assert body["human_review"]["comments"] == "No aprobar porque falta justificacion de negocio."

        detail_response = client.get(f"/api/v1/analysis/{interaction.request_id}/details")
        assert detail_response.status_code == 200
        detail_body = detail_response.json()
        human_review_step = next(
            step for step in detail_body["steps"] if step["title"] == "Human Review"
        )
        assert human_review_step["status"] == "reject"
        assert "Comentario: No aprobar porque falta justificacion de negocio." in human_review_step[
            "details"
        ]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_missing_conversation_is_rejected(db_session) -> None:
    with pytest.raises(LookupError):
        create_interaction(
            db_session,
            question="Question",
            conversation_id=uuid4(),
            created_by=None,
            metadata={},
        )
