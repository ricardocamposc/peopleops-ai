from fastapi.testclient import TestClient
from pydantic import ValidationError

from peopleops_api.config import Settings
from peopleops_api.main import app


def test_health() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_explicit_cors_preflight() -> None:
    response = TestClient(app).options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_api_owns_only_peopleops_database_configuration(monkeypatch) -> None:
    monkeypatch.setenv("PEOPLEOPS_DATABASE_HOST", "peopleops-db")
    settings = Settings()
    assert settings.peopleops_database_host == "peopleops-db"
    assert not hasattr(settings, "synthetic_hris_database_host")


def test_invalid_api_configuration_is_rejected() -> None:
    try:
        Settings(PEOPLEOPS_DATABASE_PORT="not-a-port")
    except ValidationError:
        return
    raise AssertionError("invalid database port must be rejected")
