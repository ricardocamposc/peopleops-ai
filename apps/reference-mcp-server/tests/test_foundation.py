from fastapi.testclient import TestClient
from pydantic import ValidationError

from reference_mcp_server.config import Settings
from reference_mcp_server.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_server_owns_only_synthetic_database_configuration(monkeypatch) -> None:
    monkeypatch.setenv("SYNTHETIC_HRIS_DATABASE_HOST", "synthetic-hris-db")
    settings = Settings()
    assert settings.synthetic_hris_database_host == "synthetic-hris-db"
    assert not hasattr(settings, "peopleops_database_host")


def test_invalid_server_configuration_is_rejected() -> None:
    try:
        Settings(SYNTHETIC_HRIS_DATABASE_PORT="not-a-port")
    except ValidationError:
        return
    raise AssertionError("invalid database port must be rejected")
