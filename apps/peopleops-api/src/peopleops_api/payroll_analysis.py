"""Provider-neutral payroll analysis contracts and deterministic calculations.

The module deliberately accepts rows returned by conceptual queries rather than
ORM objects.  Physical source mappings remain owned by the MCP server.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from peopleops_api.query_contracts import (
    ConceptualQuery,
    QueryFilter,
    QueryPeriod,
    QuerySelect,
)


class PayrollConceptVariation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_code: str
    concept_name: str | None = None
    previous_amount: Decimal = Decimal("0")
    current_amount: Decimal = Decimal("0")
    change: Decimal


class PayrollPeriodComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_period: str
    current_period: str
    previous_gross: Decimal
    current_gross: Decimal
    gross_change: Decimal
    previous_deductions: Decimal
    current_deductions: Decimal
    deductions_change: Decimal
    previous_net: Decimal
    current_net: Decimal
    net_change: Decimal
    concepts: list[PayrollConceptVariation] = Field(default_factory=list)


class OvertimeReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_code: str | None = None
    period: str | None = None
    recorded_minutes: Decimal
    paid_hours: Decimal
    paid_minutes: Decimal
    difference_minutes: Decimal
    status: str


class PayrollAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    gross: Decimal
    deductions: Decimal
    net: Decimal
    employer_cost: Decimal
    record_count: int


def compare_payroll_periods(
    previous_rows: Iterable[Mapping[str, Any]],
    current_rows: Iterable[Mapping[str, Any]],
    *,
    previous_period: str,
    current_period: str,
    previous_items: Iterable[Mapping[str, Any]] = (),
    current_items: Iterable[Mapping[str, Any]] = (),
) -> PayrollPeriodComparison:
    """Compare one employee's two payroll snapshots without model arithmetic."""

    previous = _single_total(previous_rows, "previous")
    current = _single_total(current_rows, "current")
    concepts = explain_concept_variations(previous_items, current_items)
    return PayrollPeriodComparison(
        previous_period=previous_period,
        current_period=current_period,
        previous_gross=previous["gross_amount"],
        current_gross=current["gross_amount"],
        gross_change=current["gross_amount"] - previous["gross_amount"],
        previous_deductions=previous["deduction_amount"],
        current_deductions=current["deduction_amount"],
        deductions_change=current["deduction_amount"] - previous["deduction_amount"],
        previous_net=previous["net_amount"],
        current_net=current["net_amount"],
        net_change=current["net_amount"] - previous["net_amount"],
        concepts=concepts,
    )


def explain_concept_variations(
    previous_rows: Iterable[Mapping[str, Any]], current_rows: Iterable[Mapping[str, Any]]
) -> list[PayrollConceptVariation]:
    previous = _sum_by_concept(previous_rows)
    current = _sum_by_concept(current_rows)
    codes = sorted(set(previous) | set(current))
    return [
        PayrollConceptVariation(
            concept_code=code,
            concept_name=(current.get(code) or previous[code])["name"],
            previous_amount=previous.get(code, {"amount": Decimal("0")})["amount"],
            current_amount=current.get(code, {"amount": Decimal("0")})["amount"],
            change=current.get(code, {"amount": Decimal("0")})["amount"]
            - previous.get(code, {"amount": Decimal("0")})["amount"],
        )
        for code in codes
    ]


def reconcile_overtime(
    recorded_rows: Iterable[Mapping[str, Any]],
    paid_rows: Iterable[Mapping[str, Any]],
    *,
    employee_code: str | None = None,
    period: str | None = None,
) -> OvertimeReconciliation:
    """Match approved overtime minutes with payroll OT quantity in hours."""

    recorded = sum((_decimal(row.get("approved_minutes")) for row in recorded_rows), Decimal("0"))
    paid_hours = sum((_decimal(row.get("quantity")) for row in paid_rows), Decimal("0"))
    paid_minutes = paid_hours * Decimal("60")
    difference = recorded - paid_minutes
    return OvertimeReconciliation(
        employee_code=employee_code,
        period=period,
        recorded_minutes=recorded,
        paid_hours=paid_hours,
        paid_minutes=paid_minutes,
        difference_minutes=difference,
        status="matched" if difference == 0 else "discrepancy",
    )


def aggregate_payroll(
    rows: Iterable[Mapping[str, Any]], *, dimension_field: str = "cost_center"
) -> list[PayrollAggregate]:
    """Aggregate payroll totals by a returned semantic dimension."""

    totals: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {
            "gross": Decimal("0"),
            "deductions": Decimal("0"),
            "net": Decimal("0"),
            "employer_cost": Decimal("0"),
            "record_count": 0,
        }
    )
    for row in rows:
        dimension = str(row.get(dimension_field) or "unknown")
        bucket = totals[dimension]
        for target, source in (
            ("gross", "gross_amount"),
            ("deductions", "deduction_amount"),
            ("net", "net_amount"),
            ("employer_cost", "employer_cost"),
        ):
            bucket[target] = bucket[target] + _decimal(row.get(source))
        bucket["record_count"] = int(bucket["record_count"]) + 1
    return [PayrollAggregate(dimension=key, **value) for key, value in sorted(totals.items())]


def payroll_detail_query(employee_code: str, period_code: str) -> ConceptualQuery:
    """Build a generic detail query; only semantic IDs cross the PeopleOps boundary."""

    return ConceptualQuery(
        goal="payroll_detail",
        entities=["employee", "payroll", "payroll_period", "payroll_item", "payroll_concept"],
        select=[
            QuerySelect(field="employee.employee_code"),
            QuerySelect(field="payroll_period.code", alias="period"),
            QuerySelect(field="payroll.gross_amount"),
            QuerySelect(field="payroll.deduction_amount"),
            QuerySelect(field="payroll.net_amount"),
            QuerySelect(field="payroll.employer_cost"),
            QuerySelect(field="payroll.cost_center"),
            QuerySelect(field="payroll_concept.code", alias="concept_code"),
            QuerySelect(field="payroll_concept.name", alias="concept_name"),
            QuerySelect(field="payroll_item.quantity"),
            QuerySelect(field="payroll_item.amount"),
        ],
        filters=[QueryFilter(field="employee.employee_code", operator="eq", value=employee_code)],
        relationships=[
            "payroll_employee",
            "payroll_period",
            "payroll_item_payroll",
            "payroll_item_concept",
        ],
        time_scope=QueryPeriod(type="payroll_period", value=period_code),
    )


def overtime_query(start: Any, end: Any, employee_code: str | None = None) -> ConceptualQuery:
    filters = (
        [QueryFilter(field="employee.employee_code", operator="eq", value=employee_code)]
        if employee_code
        else []
    )
    return ConceptualQuery(
        goal="overtime_detail",
        entities=["employee", "overtime"],
        select=[
            QuerySelect(field="employee.employee_code"),
            QuerySelect(field="overtime.approved_minutes"),
        ],
        filters=filters,
        relationships=["overtime_employee"],
        time_scope=QueryPeriod(type="date_range", field="overtime.work_date", start=start, end=end),
    )


def derive_payroll_facts(query_results: Iterable[tuple[Any, Any]]) -> dict[str, Any]:
    """Derive auditable payroll facts from a set of planned query results.

    ``query_results`` contains the plan/query and its provider-neutral result.
    Classification uses the typed query entity set and returned field contract,
    never the user's wording or a physical table name.
    """

    payroll_rows: list[Mapping[str, Any]] = []
    overtime_rows: list[Mapping[str, Any]] = []
    for planned, result in query_results:
        entities = set(planned.query.entities)
        if "payroll" in entities and result.rows:
            payroll_rows.extend(result.rows)
        if "overtime" in entities and result.rows:
            overtime_rows.extend(result.rows)
    facts: dict[str, Any] = {}
    periods: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in payroll_rows:
        period = str(row.get("period") or row.get("payroll_period") or "unknown")
        periods[period].append(row)
    ordered_periods = sorted(key for key in periods if key != "unknown")
    if len(ordered_periods) >= 2:
        previous, current = ordered_periods[-2:]
        previous_rows = periods[previous]
        current_rows = periods[current]
        facts["period_comparison"] = compare_payroll_periods(
            previous_rows,
            current_rows,
            previous_period=previous,
            current_period=current,
            previous_items=previous_rows,
            current_items=current_rows,
        ).model_dump(mode="json")
    if payroll_rows and any("cost_center" in row for row in payroll_rows):
        unique: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        for row in payroll_rows:
            key = (row.get("employee_code"), row.get("period"), row.get("net_amount"))
            unique.setdefault(key, row)
        facts["aggregates"] = [
            item.model_dump(mode="json") for item in aggregate_payroll(unique.values())
        ]
    paid_ot = [row for row in payroll_rows if str(row.get("concept_code", "")).upper() == "OT"]
    if overtime_rows or paid_ot:
        facts["overtime_reconciliation"] = reconcile_overtime(
            overtime_rows,
            paid_ot,
            employee_code=(overtime_rows[0].get("employee_code") if overtime_rows else None),
            period=(paid_ot[0].get("period") if paid_ot else None),
        ).model_dump(mode="json")
    return facts


def _single_total(rows: Iterable[Mapping[str, Any]], label: str) -> dict[str, Decimal]:
    materialized = list(rows)
    if not materialized:
        raise ValueError(f"{label} payroll result is empty")
    row = materialized[0]
    return {
        field: _decimal(row.get(field))
        for field in ("gross_amount", "deduction_amount", "net_amount", "employer_cost")
    }


def _sum_by_concept(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("concept_code") or row.get("code") or "unknown")
        if code not in result:
            result[code] = {
                "name": row.get("concept_name") or row.get("name"),
                "amount": Decimal("0"),
            }
        result[code]["amount"] += _decimal(row.get("amount"))
    return result


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("payroll numeric value is invalid") from exc
