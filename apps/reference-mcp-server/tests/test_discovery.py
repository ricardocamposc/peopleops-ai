import asyncio

from mcp import Client

from reference_mcp_server.main import create_mcp_server


def test_discovery_is_exposed_as_real_mcp_tools() -> None:
    async def check() -> dict:
        async with Client(create_mcp_server()) as client:
            result = await client.call_tool("discover_catalog", {"request_id": "discovery-1"})
            return result.structured_content or {}

    body = asyncio.run(check())
    assert body["provider_type"] == "reference_synthetic_hris"
    assert body["catalog_version"]
    assert len(body["fingerprint"]) == 64
    assert {cap["name"] for cap in body["capabilities"]} >= {"workforce", "payroll"}
    assert len(body["entities"]) == 14


def test_entity_and_relationship_metadata_are_available_through_mcp() -> None:
    async def check() -> tuple[dict, list[dict]]:
        async with Client(create_mcp_server()) as client:
            entity = await client.call_tool("describe_entity", {"entity_id": "payroll", "request_id": "discovery-2"})
            relationships = await client.call_tool("discover_relationships", {"request_id": "discovery-3"})
            relationship_payload = relationships.structured_content or {}
            return entity.structured_content or {}, relationship_payload.get("result", [])

    entity, relationships = asyncio.run(check())
    fields = {field["field_id"]: field for field in entity["fields"]}
    assert entity["physical_source"] == "employee_payroll"
    assert fields["net_amount"]["semantic_role"] == "amount"
    payroll_employee = next(item for item in relationships if item["relationship_id"] == "payroll_employee")
    assert payroll_employee["from_entity"] == "payroll"
    assert "employee_payroll.employee_id" in payroll_employee["physical_mapping"]


def test_catalog_fingerprint_is_stable_and_version_sensitive() -> None:
    from reference_mcp_server.discovery import build_catalog

    assert build_catalog().fingerprint == build_catalog().fingerprint
    assert build_catalog().fingerprint != build_catalog(catalog_version="2026.09").fingerprint


def test_unknown_entity_is_a_tool_error() -> None:
    async def check() -> bool:
        async with Client(create_mcp_server()) as client:
            result = await client.call_tool("describe_entity", {"entity_id": "not-real", "request_id": "error-1"})
            return result.is_error

    assert asyncio.run(check()) is True
