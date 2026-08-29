"""Deterministic temporal resolution using provider-owned calendar context."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from peopleops_api.analysis_contracts import TemporalIntent
from peopleops_api.mcp_contracts import TemporalContext
from peopleops_api.query_contracts import PeriodValue, QueryPeriod


def resolve_temporal_intent(
    intent: TemporalIntent | None,
    context: TemporalContext,
    *,
    field: str,
) -> list[tuple[str | None, QueryPeriod]]:
    """Resolve an intent into one or more complete provider-neutral periods."""
    if intent is None or intent.kind in {"unknown", "latest_available_period"}:
        return []
    source = context.source_current_date
    if intent.kind == "current_month":
        return [(None, _month_period(source.year, source.month, field))]
    if intent.kind == "previous_month":
        year, month = _shift_month(source.year, source.month, -1)
        return [(None, _month_period(year, month, field))]
    if intent.kind == "current_year":
        return [(None, QueryPeriod(type="date_range", field=field, start=date(source.year, 1, 1), end=date(source.year, 12, 31)))]
    if intent.kind == "year_to_date":
        return [(None, QueryPeriod(type="date_range", field=field, start=date(source.year, 1, 1), end=source))]
    if intent.kind == "explicit_month_year":
        year = intent.year or source.year
        if intent.month is None:
            return []
        return [(None, _month_period(year, intent.month, field))]
    if intent.kind == "period_list" and intent.months:
        year = intent.year or source.year
        return [(None, _month_period(year, month, field)) for month in intent.months]
    if intent.kind == "year_to_current_month":
        return [(None, QueryPeriod(
            type="date_range", field=field, start=date(source.year, 1, 1),
            end=date(source.year, source.month, calendar.monthrange(source.year, source.month)[1]),
        ))]
    if intent.kind == "explicit_date_range" and intent.start and intent.end:
        return [(None, QueryPeriod(type="date_range", field=field, start=intent.start, end=intent.end))]
    if intent.kind == "current_day":
        return [(None, QueryPeriod(type="date_range", field=field, start=source, end=source))]
    if intent.kind == "previous_day":
        previous = source - timedelta(days=1)
        return [(None, QueryPeriod(type="date_range", field=field, start=previous, end=previous))]
    if intent.kind == "current_vs_previous":
        current = _month_period(source.year, source.month, field)
        year, month = _shift_month(source.year, source.month, -1)
        return [("current", current), ("previous", _month_period(year, month, field))]
    if intent.kind == "same_month_previous_years":
        count = intent.years or 1
        return [("current", _month_period(source.year, source.month, field))] + [
            ("previous", _month_period(source.year - offset, source.month, field))
            for offset in range(1, count + 1)
        ]
    return []


def _month_period(year: int, month: int, field: str) -> QueryPeriod:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return QueryPeriod(
        type="period", field=field, period=PeriodValue(year=year, month=month),
        # Keep the resolved calendar bounds as auditable metadata; the provider
        # still chooses how PeriodValue is mapped physically.
        start=start, end=end,
    )


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + offset
    return index // 12, index % 12 + 1
