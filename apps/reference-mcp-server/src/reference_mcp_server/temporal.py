"""Provider-authoritative temporal context."""

from __future__ import annotations

from datetime import date, datetime

import psycopg
from pydantic import BaseModel

from reference_mcp_server.audit import record_interaction, monotonic_started
from reference_mcp_server.config import Settings


class TemporalContext(BaseModel):
    source_current_date: date
    source_current_timestamp: datetime
    source_timezone: str | None = None
    current_year: int
    current_month: int


def get_temporal_context(settings: Settings, *, request_id: str) -> TemporalContext:
    started_at, _ = monotonic_started()
    context: TemporalContext | None = None
    error: Exception | None = None
    try:
        with psycopg.connect(_database_url(settings), connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT CURRENT_DATE, CURRENT_TIMESTAMP, current_setting('TIMEZONE')")
                current_date, current_timestamp, timezone = cursor.fetchone()
        context = TemporalContext(
            source_current_date=current_date,
            source_current_timestamp=current_timestamp,
            source_timezone=timezone,
            current_year=current_date.year,
            current_month=current_date.month,
        )
        return context
    except Exception as exc:
        error = exc
        raise
    finally:
        record_interaction(
            settings,
            tool_name="get_temporal_context",
            request_id=request_id,
            started_at=started_at,
            status="completed" if context else "failed",
            source_current_date=context.source_current_date if context else None,
            source_current_timestamp=context.source_current_timestamp if context else None,
            error_code="SOURCE_UNAVAILABLE" if error else None,
            error_message_safe="temporal source unavailable" if error else None,
        )


def _database_url(settings: Settings) -> str:
    return f"postgresql://{settings.synthetic_hris_database_user}:{settings.synthetic_hris_database_password}@{settings.synthetic_hris_database_host}:{settings.synthetic_hris_database_port}/{settings.synthetic_hris_database_name}"
