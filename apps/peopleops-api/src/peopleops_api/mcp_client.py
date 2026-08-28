"""Official MCP client boundary for the provider-neutral HR gateway."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any

from mcp import Client
from mcp.types import TextContent
from pydantic import BaseModel, ValidationError

from peopleops_api.mcp_contracts import DiscoveryRequestContext


class MCPClientError(Exception):
    def __init__(self, code: str, message: str, *, request_id: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.retryable = retryable


class MCPTimeoutError(MCPClientError):
    pass


class MCPUnavailableError(MCPClientError):
    pass


class MCPContractError(MCPClientError):
    pass


class MCPProviderError(MCPClientError):
    pass


class MCPClient:
    """Synchronous application adapter over the official async MCP client."""

    def __init__(self, *, server_url: str | None = None, server: Any | None = None, timeout_seconds: float = 5.0, max_retries: int = 0, **_: Any):
        if server is None and server_url is None:
            raise ValueError("server_url or in-process server is required")
        endpoint = str(server_url).rstrip("/") if server_url else None
        if endpoint and not endpoint.endswith("/mcp"):
            endpoint += "/mcp"
        self._server = server if server is not None else endpoint
        self.server_url = endpoint
        self.timeout_seconds = min(max(timeout_seconds, 0.1), 120.0)
        self.max_retries = min(max(max_retries, 0), 3)
        self.server_info: Any | None = None
        self.server_capabilities: Any | None = None
        self.protocol_version: str | None = None

    def call_tool(
        self, name: str, arguments: dict[str, Any], response_model: type[BaseModel], context: DiscoveryRequestContext
    ) -> BaseModel:
        return self._run(self._call_tool(name, arguments, response_model, context), context)

    async def _call_tool(
        self, name: str, arguments: dict[str, Any], response_model: type[BaseModel], context: DiscoveryRequestContext
    ) -> BaseModel:
        for attempt in range(self.max_retries + 1):
            try:
                async with Client(self._server, read_timeout_seconds=self.timeout_seconds) as client:
                    self.server_info = client.server_info
                    self.server_capabilities = client.server_capabilities
                    self.protocol_version = client.protocol_version
                    result = await client.call_tool(name, arguments)
                    if result.is_error:
                        code = _provider_error_code(result.content)
                        raise MCPProviderError(
                            code, "MCP provider rejected the request", request_id=context.request_id
                        )
                    payload = result.structured_content
                    if payload is None:
                        raise MCPContractError(
                            "MCP_CONTRACT_ERROR", "MCP provider returned no structured result", request_id=context.request_id
                        )
                    # MCP structured output wraps top-level arrays in a
                    # `result` object; preserve the typed RootModel contract
                    # used by HRDataGateway at this boundary.
                    if isinstance(payload, dict) and set(payload) == {"result"}:
                        payload = payload["result"]
                    try:
                        return response_model.model_validate(payload)
                    except ValidationError as exc:
                        raise MCPContractError(
                            "MCP_CONTRACT_ERROR", "MCP provider returned an invalid structured contract", request_id=context.request_id
                        ) from exc
            except MCPClientError as exc:
                if exc.retryable and attempt < self.max_retries:
                    continue
                raise
            except (TimeoutError, asyncio.TimeoutError) as exc:
                if attempt < self.max_retries:
                    continue
                raise MCPTimeoutError("MCP_TIMEOUT", "MCP provider timed out", request_id=context.request_id, retryable=True) from exc
            except (OSError, ConnectionError) as exc:
                if attempt < self.max_retries:
                    continue
                raise MCPUnavailableError("MCP_UNAVAILABLE", "MCP provider is unavailable", request_id=context.request_id, retryable=True) from exc
            except Exception as exc:
                if attempt < self.max_retries:
                    continue
                raise MCPUnavailableError("MCP_UNAVAILABLE", "MCP provider is unavailable", request_id=context.request_id, retryable=True) from exc
        raise MCPUnavailableError("MCP_UNAVAILABLE", "MCP provider is unavailable", request_id=context.request_id)

    def _run(self, coroutine: Any, context: DiscoveryRequestContext) -> BaseModel:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result: Future[BaseModel] = Future()

        def runner() -> None:
            try:
                result.set_result(asyncio.run(coroutine))
            except BaseException as exc:
                result.set_exception(exc)

        threading.Thread(target=runner, daemon=True).start()
        try:
            return result.result(timeout=self.timeout_seconds + 5)
        except TimeoutError as exc:
            raise MCPTimeoutError("MCP_TIMEOUT", "MCP provider timed out", request_id=context.request_id, retryable=True) from exc


def _provider_error_code(content: list[Any]) -> str:
    known = {
        "INVALID_CONCEPTUAL_QUERY",
        "UNSUPPORTED_ENTITY",
        "UNSUPPORTED_FIELD",
        "UNSUPPORTED_RELATIONSHIP",
        "AUTHORIZATION_DENIED",
        "QUERY_VALIDATION_FAILED",
        "QUERY_VALIDATION_ERROR",
        "QUERY_EXECUTION_ERROR",
        "QUERY_TIMEOUT",
        "SOURCE_UNAVAILABLE",
        "EXECUTION_FAILED",
        "CATALOG_CHANGED",
    }
    text = " ".join(item.text for item in content if isinstance(item, TextContent))
    return next((code for code in known if code in text), "MCP_PROVIDER_ERROR")
