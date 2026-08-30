from datetime import date, datetime

from peopleops_api.analysis_contracts import AnalysisPlan, PlannedQuery, TemporalIntent
from peopleops_api.mcp_contracts import DiscoveryCatalog, DiscoveryEntity, DiscoveryField, TemporalContext
from peopleops_api.query_contracts import ConceptualQuery, QueryFilter, QueryPeriod, QuerySelect
from peopleops_api.analysis_workflow import _apply_temporal_intent
from reference_mcp_server.discovery import build_catalog
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


def test_period_list_temporal_application_is_idempotent() -> None:
    catalog = DiscoveryCatalog(
        provider_type="test", catalog_version="1", fingerprint="test", capabilities=[],
        relationships=[], entities=[DiscoveryEntity(
            entity_id="overtime", business_name="Overtime", description="", sensitivity="internal",
            supported_operations=["read"], temporal_fields=["work_date"], fields=[
                DiscoveryField(field_id="approved_minutes", business_name="", description="", data_type="integer", nullable=False, semantic_role="metric", sensitivity="internal"),
                DiscoveryField(field_id="work_date", business_name="", description="", data_type="date", nullable=False, semantic_role="date", sensitivity="internal", temporal_kind="date"),
            ],
        )],
    )
    plan = AnalysisPlan(
        goal="overtime",
        queries=[PlannedQuery(
            purpose="overtime",
            query=ConceptualQuery(
                entities=["overtime"], select=[QuerySelect(field="overtime.approved_minutes")]
            ),
        )],
    )
    intent = TemporalIntent(kind="period_list", months=[1, 3, 6])
    first = _apply_temporal_intent(plan, intent, context(date(2026, 8, 29)), catalog)
    second = _apply_temporal_intent(first, intent, context(date(2026, 8, 29)), catalog)
    assert len(first.queries) == 3
    assert len(second.queries) == 3


def test_authoritative_period_replaces_model_temporal_filters() -> None:
    catalog = DiscoveryCatalog(
        provider_type="test", catalog_version="1", fingerprint="test",
        capabilities=[], relationships=[], entities=[DiscoveryEntity(
            entity_id="overtime", business_name="Overtime", description="", sensitivity="internal",
            supported_operations=["read"], temporal_fields=["work_date"], fields=[
                DiscoveryField(field_id="status", business_name="", description="", data_type="string", nullable=False, semantic_role="attribute", sensitivity="internal"),
                DiscoveryField(field_id="work_date", business_name="", description="", data_type="date", nullable=False, semantic_role="date", sensitivity="internal", temporal_kind="date"),
            ],
        )],
    )
    plan = AnalysisPlan(
        goal="overtime",
        queries=[PlannedQuery(purpose="overtime", query=ConceptualQuery(
            entities=["overtime"],
            select=[QuerySelect(field="overtime.status")],
            filters=[
                QueryFilter(field="overtime.work_date", operator="gte", value="2026-01-01"),
                QueryFilter(field="overtime.status", operator="eq", value="approved"),
            ],
        ))],
    )
    resolved = _apply_temporal_intent(
        plan, TemporalIntent(kind="period_list", months=[1, 3, 6]),
        context(date(2026, 8, 29)), catalog,
    )
    assert len(resolved.queries) == 3
    assert [q.query.time_scope.period.model_dump() for q in resolved.queries] == [
        {"year": 2026, "month": 1}, {"year": 2026, "month": 3}, {"year": 2026, "month": 6}
    ]
    assert all(
        [f.field for f in q.query.filters] == ["overtime.status"]
        for q in resolved.queries
    )


def test_period_list_replaces_wrong_payroll_field_with_subject_temporal_field() -> None:
    catalog = build_catalog()
    plan = AnalysisPlan(
        goal="overtime periods",
        queries=[PlannedQuery(
            purpose="overtime periods",
            query=ConceptualQuery(
                entities=["overtime", "payroll_period", "employee", "payroll"],
                select=[QuerySelect(field="overtime.approved_minutes")],
                relationships=["overtime_employee", "payroll_employee", "payroll_period"],
                time_scope=QueryPeriod(
                    type="payroll_period", field="payroll_period.code", value="2026-01",
                    period={"year": 2026, "month": 1},
                ),
            ),
        )],
    )
    resolved = _apply_temporal_intent(
        plan, TemporalIntent(kind="period_list", months=[1, 3, 6], year=2026),
        context(date(2026, 8, 29)), catalog,
    )
    assert len(resolved.queries) == 3
    assert [item.query.time_scope.field for item in resolved.queries] == [
        "overtime.work_date"
    ] * 3
    assert [item.query.time_scope.period.model_dump() for item in resolved.queries] == [
        {"year": 2026, "month": 1},
        {"year": 2026, "month": 3},
        {"year": 2026, "month": 6},
    ]


def test_genuine_payroll_period_scope_is_preserved_for_payroll_subject() -> None:
    catalog = build_catalog()
    plan = AnalysisPlan(
        goal="payroll period",
        queries=[PlannedQuery(
            purpose="payroll period",
            query=ConceptualQuery(
                entities=["payroll", "payroll_period"],
                select=[QuerySelect(field="payroll.gross_amount")],
                relationships=["payroll_period"],
                time_scope=QueryPeriod(
                    type="payroll_period", field="payroll_period.code", value="2026-01",
                    period={"year": 2026, "month": 1},
                ),
            ),
        )],
    )
    resolved = _apply_temporal_intent(
        plan, TemporalIntent(kind="explicit_month_year", month=1, year=2026),
        context(date(2031, 4, 17)), catalog,
    )
    assert resolved.queries[0].query.time_scope.field == "payroll_period.code"
