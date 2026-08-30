"""Durable, provider-side audit records for MCP invocations."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

import psycopg

from reference_mcp_server.config import Settings

logger = logging.getLogger(__name__)
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _schema(settings: Settings) -> str:
    value = settings.mcp_audit_schema
    if not _SCHEMA_RE.fullmatch(value):
        raise ValueError("invalid audit schema")
    return value


def _database_url(settings: Settings) -> str:
    return f"postgresql://{settings.synthetic_hris_database_user}:{settings.synthetic_hris_database_password}@{settings.synthetic_hris_database_host}:{settings.synthetic_hris_database_port}/{settings.synthetic_hris_database_name}"


def ensure_audit_store(settings: Settings) -> None:
    schema = _schema(settings)
    with psycopg.connect(_database_url(settings), connect_timeout=3) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS "{schema}".mcp_interaction (
                    interaction_id uuid PRIMARY KEY,
                    request_id text NOT NULL,
                    tool_name text NOT NULL,
                    started_at timestamptz NOT NULL,
                    completed_at timestamptz,
                    duration_ms integer,
                    status text NOT NULL,
                    catalog_version text,
                    provider_type text,
                    conceptual_query jsonb,
                    query_hash text,
                    validation_result jsonb,
                    validation_errors jsonb,
                    physical_sql text,
                    physical_params jsonb,
                    execution_attempted boolean NOT NULL DEFAULT false,
                    execution_success boolean,
                    row_count integer,
                    error_code text,
                    error_message_safe text,
                    source_current_date date,
                    source_current_timestamp timestamptz,
                    authorization_context jsonb
                )
            ''')
            cursor.execute(
                f'ALTER TABLE "{schema}".mcp_interaction '
                "ADD COLUMN IF NOT EXISTS authorization_context jsonb"
            )


def record_interaction(
    settings: Settings,
    *,
    tool_name: str,
    request_id: str,
    started_at: datetime,
    status: str,
    completed_at: datetime | None = None,
    catalog_version: str | None = None,
    provider_type: str | None = None,
    conceptual_query: dict[str, Any] | None = None,
    query_hash: str | None = None,
    validation_result: dict[str, Any] | None = None,
    validation_errors: list[str] | None = None,
    physical_sql: str | None = None,
    physical_params: tuple[Any, ...] | list[Any] | None = None,
    execution_attempted: bool = False,
    execution_success: bool | None = None,
    row_count: int | None = None,
    error_code: str | None = None,
    error_message_safe: str | None = None,
    source_current_date: date | None = None,
    source_current_timestamp: datetime | None = None,
    authorization_context: dict[str, Any] | None = None,
) -> str:
    """Persist one audit event; failures are logged but never alter MCP semantics."""
    interaction_id = str(uuid4())
    completed = completed_at or datetime.now(UTC)
    duration_ms = max(0, round((completed - started_at).total_seconds() * 1000))
    try:
        ensure_audit_store(settings)
        with psycopg.connect(_database_url(settings), connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f'''INSERT INTO "{_schema(settings)}".mcp_interaction (
                        interaction_id, request_id, tool_name, started_at, completed_at,
                        duration_ms, status, catalog_version, provider_type,
                        conceptual_query, query_hash, validation_result, validation_errors,
                        physical_sql, physical_params, execution_attempted, execution_success,
                        row_count, error_code, error_message_safe, source_current_date,
                        source_current_timestamp, authorization_context
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''',
                    (
                        interaction_id, request_id, tool_name, started_at, completed,
                        duration_ms, status, catalog_version, provider_type,
                        json.dumps(conceptual_query, default=str) if conceptual_query is not None else None,
                        query_hash,
                        json.dumps(validation_result, default=str) if validation_result is not None else None,
                        json.dumps(validation_errors) if validation_errors is not None else None,
                        physical_sql,
                        json.dumps(list(physical_params), default=str) if physical_params is not None else None,
                        execution_attempted, execution_success, row_count, error_code,
                        error_message_safe, source_current_date, source_current_timestamp,
                        json.dumps(authorization_context) if authorization_context is not None else None,
                    ),
                )
        return interaction_id
    except Exception:  # audit must not break the provider boundary
        logger.exception("MCP audit persistence failed", extra={"request_id": request_id, "tool": tool_name})
        return interaction_id


def monotonic_started() -> tuple[datetime, float]:
    return datetime.now(UTC), monotonic()
