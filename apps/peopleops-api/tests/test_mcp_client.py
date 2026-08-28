import asyncio

import pytest
from mcp import Client

from peopleops_api.hr_data_gateway import HRDataGateway
from peopleops_api.mcp_client import MCPClient, MCPProviderError, MCPTimeoutError, MCPUnavailableError
from peopleops_api.mcp_contracts import DiscoveryRequestContext, SecurityContext
from peopleops_api.query_contracts import ConceptualQuery, QuerySelect


def test_official_in_memory_handshake_exposes_protocol_metadata() -> None:
    from reference_mcp_server.main import create_mcp_server

    async def check() -> tuple[object, object, str, list[object]]:
        async with Client(create_mcp_server()) as client:
            tools = await client.list_tools()
            return client.server_info, client.server_capabilities, client.protocol_version, tools.tools

    info, capabilities, protocol, tools = asyncio.run(check())
    assert info is not None
    assert info.name == "reference-mcp-server"
    assert capabilities is not None
    assert protocol
    assert {tool.name for tool in tools} >= {
        "discover_catalog",
        "validate_conceptual_query",
        "execute_conceptual_query",
    }


def test_gateway_uses_official_in_memory_mcp_server() -> None:
    from reference_mcp_server.main import create_mcp_server

    gateway = HRDataGateway(MCPClient(server=create_mcp_server(), max_retries=0))
    catalog = gateway.discover_catalog(request_id="req-1", security=SecurityContext(scopes=["hr:read"]))
    assert catalog.provider_type == "reference_synthetic_hris"
    assert catalog.entities


def test_gateway_validates_query_through_mcp_tool() -> None:
    from reference_mcp_server.main import create_mcp_server

    gateway = HRDataGateway(MCPClient(server=create_mcp_server(), max_retries=0))
    result = gateway.validate_query(
        ConceptualQuery(entities=["employee"], select=[QuerySelect(field="employee.employee_code")]),
        request_id="req-query",
        security=SecurityContext(scopes=["hr:read"]),
    )
    assert result.valid is True
    assert result.catalog_version


def test_unavailable_provider_is_normalized() -> None:
    client = MCPClient(server_url="http://127.0.0.1:1", max_retries=0, timeout_seconds=0.1)
    with pytest.raises((MCPTimeoutError, MCPProviderError, MCPUnavailableError)):
        client.call_tool(
            "discover_catalog",
            {"request_id": "req-timeout", "security": {}},
            object,
            DiscoveryRequestContext(request_id="req-timeout"),
        )


def test_mcp_client_never_exposes_a_physical_sql_operation() -> None:
    from reference_mcp_server.main import create_mcp_server

    async def check() -> list[str]:
        async with Client(create_mcp_server()) as client:
            result = await client.list_tools()
            return [tool.name for tool in result.tools]

    names = asyncio.run(check())
    assert "execute_sql" not in names
    assert "execute_conceptual_query" in names
