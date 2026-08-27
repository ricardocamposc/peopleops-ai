from fastapi.testclient import TestClient

from reference_mcp_server.discovery import build_catalog
from reference_mcp_server.main import app

client = TestClient(app)


def test_discovery_catalog_exposes_capabilities_entities_and_version() -> None:
    response = client.get("/discovery/catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["provider_type"] == "reference_synthetic_hris"
    assert body["catalog_version"]
    assert len(body["fingerprint"]) == 64
    assert {cap["name"] for cap in body["capabilities"]} >= {
        "workforce",
        "employment",
        "attendance",
        "overtime",
        "time_off",
        "payroll",
    }
    assert len(body["entities"]) == 14


def test_entity_description_contains_typed_fields_semantics_and_sensitivity() -> None:
    response = client.get("/discovery/entities/payroll")
    assert response.status_code == 200
    body = response.json()
    fields = {field["field_id"]: field for field in body["fields"]}
    assert body["physical_source"] == "employee_payroll"
    assert body["sensitivity"] == "restricted"
    assert fields["net_amount"]["data_type"] == "decimal"
    assert fields["net_amount"]["semantic_role"] == "amount"
    assert fields["employee_id"]["is_foreign_key"] is True


def test_relationship_discovery_exposes_fk_join_semantics() -> None:
    response = client.get("/discovery/relationships")
    assert response.status_code == 200
    relationships = response.json()
    payroll_employee = next(
        item for item in relationships if item["relationship_id"] == "payroll_employee"
    )
    assert payroll_employee["from_entity"] == "payroll"
    assert payroll_employee["to_entity"] == "employee"
    assert payroll_employee["relationship_type"] == "many_to_one"
    assert "employee_payroll.employee_id" in payroll_employee["physical_mapping"]


def test_fingerprint_is_stable_and_changes_when_catalog_metadata_changes() -> None:
    first = build_catalog()
    second = build_catalog()
    changed = build_catalog(catalog_version="2026.09")
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint


def test_unknown_entity_returns_typed_safe_error() -> None:
    response = client.get("/discovery/entities/not-a-real-entity")
    assert response.status_code == 404
    assert response.json()["code"] == "ENTITY_NOT_FOUND"
    assert "not-a-real-entity" in response.json()["message"]
