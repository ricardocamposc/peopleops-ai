import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

from peopleops_api.hr_data_gateway import HRDataGateway
from peopleops_api.mcp_client import MCPClient
from peopleops_api.mcp_contracts import SecurityContext
from peopleops_api.query_contracts import ConceptualQuery, QuerySelect


@pytest.fixture(scope="module")
def reference_server():
    port = _free_port()
    server_root = Path(__file__).parents[2] / "reference-mcp-server"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(server_root / "src")
    env["MCP_LIVE_DISCOVERY"] = "false"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "reference_mcp_server.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=server_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(50):
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            output = process.stdout.read().decode(errors="replace") if process.stdout else ""
            pytest.fail(f"reference MCP server could not start: {output}")
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_gateway_discovers_catalog_over_real_http(reference_server) -> None:
    gateway = HRDataGateway(MCPClient(server_url=reference_server, max_retries=0))

    catalog = gateway.discover_catalog(request_id="integration-request-1")

    assert catalog.provider_type == "reference_synthetic_hris"
    assert catalog.catalog_version
    assert {capability.name for capability in catalog.capabilities} >= {
        "workforce",
        "payroll",
    }
    assert catalog.entities


def test_gateway_validates_query_over_real_http(reference_server) -> None:
    gateway = HRDataGateway(MCPClient(server_url=reference_server, max_retries=0))
    result = gateway.validate_query(
        ConceptualQuery(
            entities=["employee"], select=[QuerySelect(field="employee.employee_code")]
        ),
        request_id="integration-query-1",
        security=SecurityContext(scopes=["hr:read"]),
    )
    assert result.valid is True
    assert result.request_id == "integration-query-1"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
