"""Operational observability primitives that do not replace functional audit."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from typing import Any, Iterator
from uuid import uuid4


request_correlation_id: ContextVar[str] = ContextVar("request_correlation_id", default="")
# Backwards-compatible name used by the API/workflow integration.
request_id_context = request_correlation_id
logger = logging.getLogger("peopleops.observability")


class JsonFormatter(logging.Formatter):
    """Small JSON formatter with an allow-list of safe operational fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "request_id": getattr(record, "request_id", request_correlation_id.get()) or "-",
        }
        for field in ("request_id", "stage", "status", "duration_ms", "run_id", "case_id"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, sort_keys=True)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(handler, _JsonHandler) for handler in root.handlers):
        handler = _JsonHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)


class _JsonHandler(logging.StreamHandler):
    pass


def new_request_id(candidate: str | None = None) -> str:
    value = candidate or str(uuid4())
    request_correlation_id.set(value)
    return value


def log_event(
    event_or_logger: Any,
    message: str | None = None,
    *,
    request_id: str | None = None,
    **fields: Any,
) -> None:
    event = fields.pop("event", None) or (
        event_or_logger if isinstance(event_or_logger, str) else message
    )
    if not event:
        event = "application.event"
    if "latency_ms" in fields and "duration_ms" not in fields:
        fields["duration_ms"] = fields.pop("latency_ms")
    logger.info(
        message or str(event),
        extra={
            "event": event,
            "request_id": request_id or request_correlation_id.get() or None,
            **{
                key: value
                for key, value in fields.items()
                if key in {"stage", "status", "duration_ms", "run_id", "case_id"}
            },
        },
    )


def request_id_from_header(candidate: str | None) -> str:
    return new_request_id(candidate)


@contextmanager
def optional_langsmith_trace(*, name: str, request_id: str) -> Iterator[None]:
    """Trace when LangSmith is explicitly configured; always remain functional offline."""

    start = monotonic()
    try:
        import os

        if os.getenv("LANGSMITH_TRACING", "false").lower() == "true":
            try:
                from langsmith import trace
            except ImportError:
                trace = None
            if trace is not None:
                with trace(
                    name=name,
                    run_type="chain",
                    project_name=os.getenv("LANGSMITH_PROJECT", "peopleops-ai"),
                    metadata={"request_id": request_id},
                ):
                    yield
            else:
                yield
        else:
            yield
    finally:
        log_event(
            "analysis.trace.completed",
            request_id=request_id,
            duration_ms=round((monotonic() - start) * 1000),
        )
        # LangSmith is best-effort tracing only; the workflow and
        # AnalysisInteraction remain functional when it is unavailable.
