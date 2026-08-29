from datetime import date

import pytest

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


def test_aggregate_groups_all_selected_non_metric_fields() -> None:
    query = ConceptualQuery(
        entities=["department", "employee", "overtime"],
        select=[
            QuerySelect(field="department.id", alias="department_id"),
            QuerySelect(field="department.name", alias="Department Name"),
        ],
        metrics=[QueryMetric(field="overtime.approved_minutes", function="sum", alias="Total Approved Overtime")],
        relationships=["employee_department", "overtime_employee"],
        dimensions=["department.name"],
        order_by=[],
        limit=10,
    )
    physical = translate_query(query, CATALOG)
    assert '"Department Name"' in physical.sql
    assert '"Total Approved Overtime"' in physical.sql
    assert 'GROUP BY t0."id", t0."name"' in physical.sql


def test_output_aliases_are_quoted_without_rejecting_valid_labels() -> None:
    query = ConceptualQuery(
        entities=["employee"],
        select=[QuerySelect(field="employee.employee_code", alias="Employee code")],
        metrics=[QueryMetric(field="employee.id", function="count", alias="Employee count")],
        limit=10,
    )
    physical = translate_query(query, CATALOG)
    assert 'AS "Employee code"' in physical.sql
    assert 'AS "Employee count"' in physical.sql


def test_duplicate_projection_labels_are_rejected_before_sql_execution() -> None:
    query = ConceptualQuery(
        entities=["employee"],
        select=[QuerySelect(field="employee.id", alias="value")],
        metrics=[QueryMetric(field="employee.id", function="count", alias="value")],
        limit=10,
    )
    validation = validate_query(query, CATALOG, [])
    assert validation.valid is False
    assert "aliases must be unique" in validation.errors[0]


def test_generated_metric_label_collides_with_select_alias() -> None:
    query = ConceptualQuery(
        entities=["employee"],
        select=[QuerySelect(field="employee.name", alias="count_id")],
        metrics=[QueryMetric(field="employee.id", function="count")],
        limit=10,
    )
    validation = validate_query(query, CATALOG, [])
    assert validation.valid is False
    assert "aliases must be unique" in validation.errors[0]


def test_order_by_uses_generated_metric_label_when_alias_is_omitted() -> None:
    query = ConceptualQuery(
        entities=["employee"],
        metrics=[QueryMetric(field="employee.id", function="count")],
        order_by=[{"reference": "count_id", "direction": "desc"}],
        limit=10,
    )
    physical = translate_query(query, CATALOG)
    assert 'ORDER BY "count_id" DESC' in physical.sql


def test_join_planner_defers_disconnected_relationships_until_reachable() -> None:
    query = ConceptualQuery(
        entities=["overtime", "department", "employee", "position"],
        select=[QuerySelect(field="department.name", alias="Department Name")],
        metrics=[QueryMetric(field="overtime.approved_minutes", function="sum", alias="Overtime")],
        filters=[QueryFilter(field="overtime.status", operator="eq", value="approved")],
        relationships=[
            "overtime_employee",
            "position_department",
            "employee_department",
            "employee_position",
        ],
        dimensions=["department.name"],
        limit=10,
    )
    physical = translate_query(query, CATALOG)
    assert 'JOIN "employee"' in physical.sql
    assert 'JOIN "department"' in physical.sql
    assert 'JOIN "position"' in physical.sql


def test_malformed_reference_is_rejected_safely() -> None:
    invalid = ConceptualQuery.model_construct(
        entities=["employee"], select=[QuerySelect(field="not-a-reference")], limit=1
    )
    validation = validate_query(invalid, CATALOG, [])
    assert validation.valid is False
    assert "invalid field reference" in validation.errors[0]



@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO employee (employee_code) VALUES ('MUTATION')",
        "UPDATE employee SET status = 'inactive'",
        "DELETE FROM employee",
        "DROP TABLE employee",
        "ALTER TABLE employee ADD COLUMN unsafe text",
        "CREATE TABLE unsafe (id integer)",
        "TRUNCATE employee",
        "SELECT 1; UPDATE employee SET status = 'inactive'",
        "SELECT 1 /* bypass */; DELETE FROM employee",
    ],
)
def test_physical_write_and_bypass_statements_are_rejected(statement: str) -> None:
    with pytest.raises(QueryExecutionError, match="non-read-only") as exc_info:
        validate_physical_query(PhysicalQuery(statement, (), []))
    assert exc_info.value.code == "PHYSICAL_QUERY_INVALID"


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
