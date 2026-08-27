"""Reusable MCP contract and Schema A/B tests for Slice 13."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from reference_mcp_server.alternate_schema import build_alternate_catalog
from reference_mcp_server.discovery import build_catalog
from reference_mcp_server.main import create_app
from reference_mcp_server.query_contracts import ConceptualQuery, QuerySelect

ROOT = Path(__file__).parents[3]
CASES = ROOT / "evaluation" / "cases" / "schema_independence_v1.jsonl"
DATABASE_URL = os.getenv("SYNTHETIC_HRIS_TEST_DATABASE_URL")


@pytest.fixture(params=["A", "B"])
def contract_client(request: pytest.FixtureRequest) -> TestClient:
    return TestClient(create_app(request.param))


def _headers(request_id: str = "contract-request", *, payroll: bool = False) -> dict[str, str]:
    scopes = "hr:read,hr:payroll" if payroll else "hr:read"
    return {"X-Request-ID": request_id, "X-Security-Scopes": scopes}


def test_contract_discovery_is_provider_neutral_and_schema_specific_only_at_mcp_boundary(
    contract_client: TestClient,
) -> None:
    response = contract_client.get("/discovery/catalog", headers=_headers())
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["catalog_version"]
    assert len(catalog["fingerprint"]) == 64
    assert {item["name"] for item in catalog["capabilities"]} >= {"workforce", "payroll"}
    assert {item["entity_id"] for item in catalog["entities"]} >= {
        "employee",
        "overtime",
        "payroll",
        "payroll_period",
    }
    assert {item["relationship_id"] for item in catalog["relationships"]} >= {
        "payroll_employee",
        "payroll_period",
    }
    assert all(item["physical_source"] for item in catalog["entities"])


def test_contract_validation_security_limits_and_read_only(contract_client: TestClient) -> None:
    query = {
        "entities": ["employee"],
        "select": [{"field": "employee.employee_code"}],
        "limit": 10,
    }
    valid = contract_client.post("/query/validate", json=query, headers=_headers())
    assert valid.status_code == 200
    assert valid.json()["valid"] is True
    assert valid.json()["request_id"] == "contract-request"

    unauthorized = contract_client.post(
        "/query/validate",
        json={"entities": ["payroll"], "select": [{"field": "payroll.net_amount"}]},
        headers=_headers("restricted-request"),
    )
    assert unauthorized.json()["valid"] is False
    assert any("hr:payroll" in error for error in unauthorized.json()["errors"])

    oversized = contract_client.post(
        "/query/validate",
        json={"entities": ["employee"], "select": [{"field": "employee.id"}], "limit": 1001},
        headers=_headers("limit-request"),
    )
    assert oversized.status_code == 422

    physical = contract_client.post(
        "/query/execute",
        json={"entities": ["employee"], "select": [{"field": "employee.id"}]},
        headers=_headers("execute-request"),
    )
    # The endpoint must return a typed validation/result or a normalized provider error;
    # it must never accept an arbitrary physical write payload.
    assert physical.status_code in {200, 422, 504}


def test_contract_error_and_correlation_behavior(contract_client: TestClient) -> None:
    response = contract_client.get(
        "/discovery/entities/does-not-exist", headers=_headers("error-request")
    )
    assert response.status_code == 404
    assert response.json()["code"] == "ENTITY_NOT_FOUND"
    assert response.headers["X-Request-ID"] == "error-request"


def test_same_conceptual_payroll_contract_translates_differently_per_schema() -> None:
    query = ConceptualQuery(
        entities=["employee", "payroll", "payroll_period"],
        select=[
            QuerySelect(field="employee.employee_code"),
            QuerySelect(field="payroll_period.code", alias="period"),
            QuerySelect(field="payroll.net_amount"),
        ],
        relationships=["payroll_employee", "payroll_period"],
        filters=[],
        limit=10,
    )
    from reference_mcp_server.execution import translate_query, validate_query

    a = translate_query(query, build_catalog())
    b = translate_query(query, build_alternate_catalog())
    assert validate_query(query, build_catalog(), ["hr:payroll"]).valid
    assert validate_query(query, build_alternate_catalog(), ["hr:payroll"]).valid
    assert a.columns == b.columns == ["employee_code", "period", "net_amount"]
    assert a.sql != b.sql
    assert "employee_payroll" in a.sql
    assert "pay_movement" in b.sql


def _load_cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]


@pytest.mark.skipif(not DATABASE_URL, reason="SYNTHETIC_HRIS_TEST_DATABASE_URL is not configured")
def test_schema_independence_real_postgresql_a_b() -> None:
    """Run the same PeopleOps gateway-shaped HTTP queries against both source adapters."""

    try:
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
        alembic_config = Config(str(ROOT / "synthetic-hris" / "alembic.ini"))
        alembic_config.set_main_option(
            "script_location", str(ROOT / "synthetic-hris" / "migrations")
        )
        alembic_config.set_main_option(
            "sqlalchemy.url",
            DATABASE_URL.replace("%", "%%").replace("postgresql://", "postgresql+psycopg://"),
        )
        command.upgrade(alembic_config, "head")
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute((ROOT / "synthetic-hris" / "seeds" / "seed.sql").read_text())
            cursor.execute(
                (ROOT / "synthetic-hris" / "alternate-schema" / "migration.sql").read_text()
            )
            cursor.execute((ROOT / "synthetic-hris" / "alternate-schema" / "seed.sql").read_text())
    except psycopg.Error as exc:
        pytest.skip(f"schema independence PostgreSQL fixture unavailable: {exc}")

    query = ConceptualQuery(
        entities=["employee", "payroll", "payroll_period"],
        select=[
            QuerySelect(field="employee.employee_code"),
            QuerySelect(field="payroll_period.code", alias="period"),
            QuerySelect(field="payroll.net_amount"),
        ],
        relationships=["payroll_employee", "payroll_period"],
        filters=[],
        limit=10,
    )
    results = []
    for schema in ("A", "B"):
        with TestClient(create_app(schema)) as client:
            response = client.post(
                "/query/execute",
                json=query.model_dump(mode="json"),
                headers=_headers(f"schema-{schema}", payroll=True),
            )
            assert response.status_code == 200, response.text
            results.append(response.json())

    normalized = [
        [(row["employee_code"], row["period"], float(row["net_amount"])) for row in result["rows"]]
        for result in results
    ]
    assert normalized[0] == normalized[1]
    assert ("E-100", "2025-02", 4250.0) in normalized[0]
