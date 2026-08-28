"""Real MCP contract and schema-independence tests."""

import asyncio

from mcp import Client

from reference_mcp_server.alternate_schema import build_alternate_catalog
from reference_mcp_server.discovery import build_catalog
from reference_mcp_server.main import create_mcp_server
from reference_mcp_server.query_contracts import ConceptualQuery, QuerySelect


def test_contract_lists_generic_capabilities_and_negotiates_protocol() -> None:
    async def check() -> tuple[str, list[str]]:
        async with Client(create_mcp_server()) as client:
            tools = await client.list_tools()
            return client.protocol_version, [item.name for item in tools.tools]

    protocol, tools = asyncio.run(check())
    assert protocol
    assert {"discover_catalog", "validate_conceptual_query", "execute_conceptual_query"} <= set(tools)


def test_conceptual_validation_and_authorization_are_structured() -> None:
    query = ConceptualQuery(entities=["employee"], select=[QuerySelect(field="employee.employee_code")])

    async def check() -> tuple[dict, dict]:
        async with Client(create_mcp_server()) as client:
            valid = await client.call_tool("validate_conceptual_query", {"query": query.model_dump(mode="json"), "request_id": "valid-1", "security": {"scopes": ["hr:read"]}})
            denied = await client.call_tool("validate_conceptual_query", {"query": {"entities": ["payroll"], "select": [{"field": "payroll.net_amount"}]}, "request_id": "denied-1", "security": {"scopes": ["hr:read"]}})
            return valid.structured_content or {}, denied.structured_content or {}

    valid, denied = asyncio.run(check())
    assert valid["valid"] is True
    assert denied["valid"] is False
    assert any("hr:payroll" in item for item in denied["errors"])


def test_same_conceptual_query_maps_differently_inside_provider_adapters() -> None:
    from reference_mcp_server.execution import translate_query, validate_query

    query = ConceptualQuery(
        entities=["employee", "payroll", "payroll_period"],
        select=[QuerySelect(field="employee.employee_code"), QuerySelect(field="payroll.net_amount")],
        relationships=["payroll_employee", "payroll_period"],
    )
    a = translate_query(query, build_catalog())
    b = translate_query(query, build_alternate_catalog())
    assert validate_query(query, build_catalog(), ["hr:payroll"]).valid
    assert validate_query(query, build_alternate_catalog(), ["hr:payroll"]).valid
    assert a.sql != b.sql
    assert "employee_payroll" in a.sql
    assert "pay_movement" in b.sql
