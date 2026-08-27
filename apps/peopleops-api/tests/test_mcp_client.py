from dataclasses import dataclass

import pytest

from peopleops_api.hr_data_gateway import HRDataGateway
from peopleops_api.mcp_client import MCPClient, MCPContractError, MCPTimeoutError
from peopleops_api.mcp_contracts import SecurityContext


@dataclass
class FakeTransport:
    response: object | None = None
    error: Exception | None = None
    calls: int = 0
    last_headers: dict[str, str] | None = None

    def request(self, *, url, headers, timeout, method="GET", body=None):
        self.calls += 1
        self.last_headers = headers
        if self.error:
            raise self.error
        return self.response


def test_gateway_maps_typed_catalog_and_forwards_correlation_context() -> None:
    transport = FakeTransport(
        response=type(
            "Response",
            (),
            {
                "status_code": 200,
                "body": b'{"provider_type":"reference","catalog_version":"v1",'
                b'"fingerprint":"abc","capabilities":[],"entities":[],"relationships":[]}',
                "headers": {"X-Request-ID": "req-1"},
            },
        )()
    )
    gateway = HRDataGateway(
        MCPClient(server_url="http://provider:8001", transport=transport, max_retries=0)
    )

    catalog = gateway.discover_catalog(
        request_id="req-1",
        security=SecurityContext(actor_id="analyst-1", role="hr", scopes=["hr:read"]),
    )

    assert catalog.provider_type == "reference"
    assert transport.last_headers == {
        "Accept": "application/json",
        "X-Request-ID": "req-1",
        "X-Correlation-ID": "req-1",
        "X-Security-Scopes": "hr:read",
        "X-Actor-ID": "analyst-1",
        "X-Role": "hr",
    }


def test_timeout_is_normalized_and_retries_are_bounded() -> None:
    transport = FakeTransport(error=TimeoutError())
    client = MCPClient(
        server_url="http://provider:8001", transport=transport, max_retries=2, timeout_seconds=0.1
    )

    with pytest.raises(MCPTimeoutError) as error:
        client.get_json("/discovery/catalog", object, _context())

    assert error.value.code == "MCP_TIMEOUT"
    assert error.value.request_id == "req-timeout"
    assert transport.calls == 3


def test_invalid_provider_payload_is_a_safe_contract_error() -> None:
    transport = FakeTransport(
        response=type("Response", (), {"status_code": 200, "body": b"not-json", "headers": {}})()
    )
    client = MCPClient(server_url="http://provider:8001", transport=transport, max_retries=0)

    with pytest.raises(MCPContractError) as error:
        client.get_json("/discovery/catalog", object, _context())

    assert str(error.value) == "MCP provider returned an invalid discovery contract"


def test_gateway_posts_typed_query_and_preserves_request_id() -> None:
    transport = FakeTransport(
        response=type(
            "Response",
            (),
            {
                "status_code": 200,
                "body": b'{"request_id":"req-query","valid":true,"query_hash":"abc",'
                b'"catalog_version":"v1","errors":[],"warnings":[]}',
                "headers": {"X-Request-ID": "req-query"},
            },
        )()
    )
    from peopleops_api.query_contracts import ConceptualQuery, QuerySelect

    gateway = HRDataGateway(
        MCPClient(server_url="http://provider:8001", transport=transport, max_retries=0)
    )
    result = gateway.validate_query(
        ConceptualQuery(entities=["employee"], select=[QuerySelect(field="employee.id")]),
        request_id="req-query",
    )
    assert result.valid is True
    assert result.request_id == "req-query"
    assert transport.last_headers["Content-Type"] == "application/json"


def _context():
    from peopleops_api.mcp_contracts import DiscoveryRequestContext

    return DiscoveryRequestContext(request_id="req-timeout")
