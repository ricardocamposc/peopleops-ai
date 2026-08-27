from datetime import date

from reference_mcp_server.discovery import build_catalog
from reference_mcp_server.execution import (
    PhysicalQuery,
    QueryExecutionError,
    query_hash,
    translate_query,
    validate_physical_query,
    validate_query,
)
from reference_mcp_server.query_contracts import (
    ConceptualQuery,
    QueryFilter,
    QueryMetric,
    QueryPeriod,
    QuerySelect,
)

CATALOG = build_catalog()


def test_validate_query_checks_fields_filters_periods_and_authorization() -> None:
    query = ConceptualQuery(
        entities=["employee"],
        select=[QuerySelect(field="employee.employee_code")],
        filters=[QueryFilter(field="employee.status", operator="eq", value="active")],
        time_scope=QueryPeriod(
            type="date_range",
            field="employee.hire_date",
            start=date(2020, 1, 1),
            end=date(2026, 1, 1),
        ),
    )
    result = validate_query(query, CATALOG, [], request_id="req-1")
    assert result.valid is True
    assert result.request_id == "req-1"
    assert result.query_hash == query_hash(query)

    invalid = ConceptualQuery.model_construct(
        entities=["employee"], select=[QuerySelect(field="employee.no_such_field")], limit=1
    )
    validation = validate_query(invalid, CATALOG, [], request_id="req-2")
    assert validation.valid is False
    assert any("unknown field" in error for error in validation.errors)


def test_translate_join_aggregate_is_parameterized_and_allowlisted() -> None:
    query = ConceptualQuery(
        entities=["employee", "department"],
        select=[QuerySelect(field="department.code")],
        metrics=[QueryMetric(field="employee.id", function="count", alias="headcount")],
        relationships=["employee_department"],
        filters=[QueryFilter(field="department.code", operator="in", value=["ENG", "OPS"])],
        order_by=[],
        limit=10,
    )
    assert validate_query(query, CATALOG, []).valid
    physical = translate_query(query, CATALOG)
    validate_physical_query(physical)
    assert "SELECT" in physical.sql
    assert "employee_code" not in physical.sql
    assert physical.params == ("ENG", "OPS")
    assert "LIMIT 10" in physical.sql


def test_malformed_reference_and_write_like_physical_query_are_rejected_safely() -> None:
    invalid = ConceptualQuery.model_construct(
        entities=["employee"], select=[QuerySelect(field="not-a-reference")], limit=1
    )
    validation = validate_query(invalid, CATALOG, [])
    assert validation.valid is False
    assert "invalid field reference" in validation.errors[0]

    try:
        validate_physical_query(PhysicalQuery("UPDATE employee SET status = 'x'", (), []))
    except QueryExecutionError as error:
        assert error.code == "PHYSICAL_QUERY_INVALID"
    else:
        raise AssertionError("write SQL must be rejected")


def test_validation_rejects_oversized_limit_and_restricted_scope() -> None:
    query = ConceptualQuery(
        entities=["payroll"],
        select=[QuerySelect(field="payroll.gross_amount")],
        limit=5,
    )
    validation = validate_query(query, CATALOG, [], max_result_rows=2)
    assert validation.valid is False
    assert any("scope hr:payroll" in error for error in validation.errors)
    assert any("maximum of 2" in error for error in validation.errors)
