"""HTTP smoke checks for the Slice 18 portfolio release.

The checks deliberately query the MCP HTTP boundary. They do not import HRIS
models or connect to either database, so a passing smoke run is evidence of
the deployed topology rather than a local-provider shortcut.
"""

from __future__ import annotations

import json
import os
import asyncio
from mcp import Client
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(
    url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None
):
    payload = json.dumps(body).encode() if body is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    with urlopen(
        Request(url, data=payload, headers=request_headers, method=method), timeout=10
    ) as response:
        content = response.read().decode()
        try:
            parsed = json.loads(content) if content else {}
        except json.JSONDecodeError:
            parsed = {"body": content}
        return response.status, parsed


def main() -> int:
    api = f"http://localhost:{os.getenv('API_PORT', '8000')}"
    mcp = f"http://localhost:{os.getenv('MCP_PORT', '8001')}"
    web = f"http://localhost:{os.getenv('WEB_PORT', '3000')}"
    checks: list[str] = []

    for label, url in (
        ("api health", f"{api}/api/v1/health"),
        ("mcp health", f"{mcp}/health"),
        ("web", f"{web}/"),
    ):
        status, _ = request(url)
        if status != 200:
            raise RuntimeError(f"{label} returned HTTP {status}")
        checks.append(label)

    status, catalog = request(
        f"{api}/api/v1/hr-data/catalog", headers={"X-Security-Scopes": "hr:read"}
    )
    if status != 200 or not catalog.get("fingerprint"):
        raise RuntimeError("PeopleOps catalog request did not return a fingerprint")
    checks.append("PeopleOps → HRDataGateway → MCP catalog")

    payroll_query = {
        "entities": ["employee", "payroll", "payroll_period"],
        "select": [{"field": "employee.employee_code"}, {"field": "payroll.net_amount"}],
        "relationships": ["payroll_employee", "payroll_period"],
        "limit": 10,
    }
    async def validate_with_mcp() -> tuple[dict, dict, str]:
        async with Client(f"{mcp}/mcp") as client:
            valid = await client.call_tool(
                "validate_conceptual_query",
                {"query": payroll_query, "request_id": "slice18-smoke-payroll", "security": {"scopes": ["hr:read", "hr:payroll"]}},
            )
            denied = await client.call_tool(
                "validate_conceptual_query",
                {"query": payroll_query, "request_id": "slice18-smoke-denied", "security": {"scopes": ["hr:read"]}},
            )
            return valid.structured_content or {}, denied.structured_content or {}, client.protocol_version

    valid, denied, protocol_version = asyncio.run(validate_with_mcp())
    if not valid.get("valid"):
        raise RuntimeError("MCP payroll conceptual validation failed")
    checks.append("MCP conceptual payroll validation")
    if denied.get("valid") is not False or not protocol_version:
        raise RuntimeError("MCP payroll authorization sanity check did not fail closed")
    checks.append("payroll scope denial")

    origin = os.getenv("FRONTEND_URL", "http://localhost:3000")
    status, _ = request(
        f"{api}/api/v1/health",
        method="OPTIONS",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    if status != 200:
        raise RuntimeError(f"CORS preflight returned HTTP {status}")
    checks.append("CORS preflight")
    print(json.dumps({"status": "passed", "checks": checks}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, RuntimeError) as exc:
        raise SystemExit(f"release smoke failed: {exc}") from exc
