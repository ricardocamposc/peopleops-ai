from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from peopleops_api.audit import transition
from peopleops_api.main import app
from peopleops_api.models import AnalysisInteraction, Conversation
from peopleops_api.repositories import create_interaction, get_interaction


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


def test_missing_conversation_is_rejected(db_session) -> None:
    with pytest.raises(LookupError):
        create_interaction(
            db_session,
            question="Question",
            conversation_id=uuid4(),
            created_by=None,
            metadata={},
        )
