from datetime import date, datetime

from peopleops_api.analysis_contracts import TemporalIntent
from peopleops_api.mcp_contracts import TemporalContext
from peopleops_api.temporal import resolve_temporal_intent


def context(day: date) -> TemporalContext:
    return TemporalContext(
        source_current_date=day,
        source_current_timestamp=datetime(day.year, day.month, day.day, 12),
        current_year=day.year,
        current_month=day.month,
    )


def test_current_and_previous_month_use_provider_date() -> None:
    current = resolve_temporal_intent(
        TemporalIntent(kind="current_month"), context(date(2026, 8, 29)), field="overtime.work_date"
    )[0][1]
    previous = resolve_temporal_intent(
        TemporalIntent(kind="previous_month"), context(date(2026, 1, 5)), field="overtime.work_date"
    )[0][1]
    assert (current.start, current.end) == (date(2026, 8, 1), date(2026, 8, 31))
    assert (previous.start, previous.end) == (date(2025, 12, 1), date(2025, 12, 31))


def test_explicit_month_does_not_use_current_month() -> None:
    result = resolve_temporal_intent(
        TemporalIntent(kind="explicit_month_year", month=1, year=2025),
        context(date(2026, 8, 29)), field="overtime.work_date",
    )[0][1]
    assert (result.start, result.end) == (date(2025, 1, 1), date(2025, 1, 31))


def test_current_vs_previous_returns_independent_structured_roles() -> None:
    result = resolve_temporal_intent(
        TemporalIntent(kind="current_vs_previous"), context(date(2026, 8, 29)), field="overtime.work_date"
    )
    assert [role for role, _ in result] == ["current", "previous"]
    assert result[0][1].start != result[1][1].start


def test_same_month_previous_years_handles_leap_year() -> None:
    result = resolve_temporal_intent(
        TemporalIntent(kind="same_month_previous_years", years=2),
        context(date(2024, 2, 29)), field="overtime.work_date",
    )
    assert [(period.start, period.end) for _, period in result] == [
        (date(2024, 2, 1), date(2024, 2, 29)),
        (date(2023, 2, 1), date(2023, 2, 28)),
        (date(2022, 2, 1), date(2022, 2, 28)),
    ]


def test_period_list_uses_reference_year_without_contiguous_range() -> None:
    result = resolve_temporal_intent(
        TemporalIntent(kind="period_list", months=[1, 3, 6]),
        context(date(2026, 8, 29)), field="overtime.work_date",
    )
    assert [period.period.model_dump() for _, period in result] == [
        {"year": 2026, "month": 1},
        {"year": 2026, "month": 3},
        {"year": 2026, "month": 6},
    ]
