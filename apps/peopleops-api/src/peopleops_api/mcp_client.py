"""Small real HTTP client for the Reference MCP discovery transport."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: bytes
    headers: dict[str, str]


class HTTPTransport(Protocol):
    def request(
        self,
        *,
        url: str,
        headers: dict[str, str],
        timeout: float,
        method: str = "GET",
        body: bytes | None = None,
    ) -> TransportResponse: ...


class UrllibHTTPTransport:
    def request(
        self,
        *,
        url: str,
        headers: dict[str, str],
        timeout: float,
        method: str = "GET",
        body: bytes | None = None,
    ) -> TransportResponse:
        request = Request(url, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                return TransportResponse(
                    status_code=response.status,
                    body=response.read(),
                    headers=dict(response.headers.items()),
                )
        except HTTPError as exc:
            return TransportResponse(
                status_code=exc.code,
                body=exc.read(),
                headers=dict(exc.headers.items()) if exc.headers else {},
            )


class MCPClient:
    def __init__(
        self,
        *,
        server_url: str,
        timeout_seconds: float = 5.0,
        max_retries: int = 2,
        transport: HTTPTransport | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.transport = transport or UrllibHTTPTransport()

    def get_json(
        self, path: str, response_model: type[BaseModel], context: DiscoveryRequestContext
    ) -> BaseModel:
        headers = self._headers(context)
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                response = self.transport.request(
                    url=f"{self.server_url}{path}",
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except TimeoutError as exc:
                if attempt + 1 < attempts:
                    continue
                raise MCPTimeoutError(
                    "MCP_TIMEOUT",
                    "MCP provider timed out",
                    request_id=context.request_id,
                    retryable=True,
                ) from exc
            except (URLError, OSError) as exc:
                if attempt + 1 < attempts:
                    continue
                raise MCPUnavailableError(
                    "MCP_UNAVAILABLE",
                    "MCP provider is unavailable",
                    request_id=context.request_id,
                    retryable=True,
                ) from exc

            if response.status_code in {502, 503, 504} and attempt + 1 < attempts:
                time.sleep(0.01)
                continue
            if response.status_code >= 400:
                raise MCPProviderError(
                    "MCP_PROVIDER_ERROR",
                    "MCP provider rejected the request",
                    request_id=context.request_id,
                    retryable=response.status_code in {429, 500, 502, 503, 504},
                )
            echoed_request_id = response.headers.get("X-Request-ID")
            if echoed_request_id and echoed_request_id != context.request_id:
                raise MCPContractError(
                    "MCP_CONTRACT_ERROR",
                    "MCP provider returned an unexpected correlation identifier",
                    request_id=context.request_id,
                )
            try:
                payload = json.loads(response.body)
                return response_model.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                raise MCPContractError(
                    "MCP_CONTRACT_ERROR",
                    "MCP provider returned an invalid discovery contract",
                    request_id=context.request_id,
                ) from exc

        raise MCPUnavailableError(
            "MCP_UNAVAILABLE", "MCP provider is unavailable", request_id=context.request_id
        )

    def post_json(
        self,
        path: str,
        payload: BaseModel,
        response_model: type[BaseModel],
        context: DiscoveryRequestContext,
    ) -> BaseModel:
        headers = {**self._headers(context), "Content-Type": "application/json"}
        body = json.dumps(payload.model_dump(mode="json"), separators=(",", ":")).encode()
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                response = self.transport.request(
                    url=f"{self.server_url}{path}",
                    headers=headers,
                    timeout=self.timeout_seconds,
                    method="POST",
                    body=body,
                )
            except TimeoutError as exc:
                if attempt + 1 < attempts:
                    continue
                raise MCPTimeoutError(
                    "MCP_TIMEOUT",
                    "MCP provider timed out",
                    request_id=context.request_id,
                    retryable=True,
                ) from exc
            except (URLError, OSError) as exc:
                if attempt + 1 < attempts:
                    continue
                raise MCPUnavailableError(
                    "MCP_UNAVAILABLE",
                    "MCP provider is unavailable",
                    request_id=context.request_id,
                    retryable=True,
                ) from exc
            if response.status_code in {502, 503, 504} and attempt + 1 < attempts:
                time.sleep(0.01)
                continue
            echoed_request_id = response.headers.get("X-Request-ID")
            if echoed_request_id and echoed_request_id != context.request_id:
                raise MCPContractError(
                    "MCP_CONTRACT_ERROR",
                    "MCP provider returned an unexpected correlation identifier",
                    request_id=context.request_id,
                )
            if response.status_code >= 400:
                raise MCPProviderError(
                    "MCP_PROVIDER_ERROR",
                    "MCP provider rejected the request",
                    request_id=context.request_id,
                    retryable=response.status_code in {429, 500, 502, 503, 504},
                )
            try:
                return response_model.model_validate(json.loads(response.body))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise MCPContractError(
                    "MCP_CONTRACT_ERROR",
                    "MCP provider returned an invalid query contract",
                    request_id=context.request_id,
                ) from exc
        raise MCPUnavailableError(
            "MCP_UNAVAILABLE", "MCP provider is unavailable", request_id=context.request_id
        )

    @staticmethod
    def _headers(context: DiscoveryRequestContext) -> dict[str, str]:
        security = context.security
        headers = {
            "Accept": "application/json",
            "X-Request-ID": context.request_id,
            "X-Correlation-ID": context.request_id,
            "X-Security-Scopes": ",".join(security.scopes),
        }
        if security.actor_id:
            headers["X-Actor-ID"] = security.actor_id
        if security.role:
            headers["X-Role"] = security.role
        return headers
