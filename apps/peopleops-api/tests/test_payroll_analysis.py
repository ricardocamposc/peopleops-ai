from datetime import date
from decimal import Decimal

from peopleops_api.payroll_analysis import (
    aggregate_payroll,
    compare_payroll_periods,
    explain_concept_variations,
    overtime_query,
    payroll_detail_query,
    reconcile_overtime,
)
from reference_mcp_server.discovery import build_catalog
from reference_mcp_server.execution import validate_query


def test_period_and_concept_calculations_are_deterministic() -> None:
    previous = [
        {
            "gross_amount": "4000.00",
            "deduction_amount": "600",
            "net_amount": "3400",
            "employer_cost": "4800",
        }
    ]
    current = [
        {
            "gross_amount": "4000.00",
            "deduction_amount": "1000",
            "net_amount": "3000",
            "employer_cost": "4800",
        }
    ]
    items_previous = [
        {"concept_code": "BASE", "concept_name": "Base salary", "amount": "4000"},
        {"concept_code": "TAX", "concept_name": "Income tax", "amount": "400"},
        {"concept_code": "HEALTH", "concept_name": "Health contribution", "amount": "200"},
    ]
    items_current = [
        {"concept_code": "BASE", "concept_name": "Base salary", "amount": "4000"},
        {"concept_code": "TAX", "concept_name": "Income tax", "amount": "700"},
        {"concept_code": "HEALTH", "concept_name": "Health contribution", "amount": "300"},
    ]
    result = compare_payroll_periods(
        previous,
        current,
        previous_period="2025-01",
        current_period="2025-02",
        previous_items=items_previous,
        current_items=items_current,
    )
    assert result.net_change == Decimal("-400")
    assert result.deductions_change == Decimal("400")
    assert {item.concept_code: item.change for item in result.concepts} == {
        "BASE": Decimal("0"),
        "HEALTH": Decimal("100"),
        "TAX": Decimal("300"),
    }


def test_overtime_reconciliation_identifies_unpaid_minutes() -> None:
    result = reconcile_overtime(
        [{"approved_minutes": 600}],
        [{"concept_code": "OT", "quantity": 0}],
        employee_code="E-103",
        period="2025-02",
    )
    assert result.recorded_minutes == Decimal("600")
    assert result.paid_minutes == Decimal("0")
    assert result.difference_minutes == Decimal("600")
    assert result.status == "discrepancy"


def test_aggregate_payroll_by_cost_center_uses_decimal_totals() -> None:
    result = aggregate_payroll(
        [
            {
                "cost_center": "CC-100",
                "gross_amount": "5000",
                "deduction_amount": "750",
                "net_amount": "4250",
                "employer_cost": "6000",
            },
            {
                "cost_center": "CC-100",
                "gross_amount": "4000",
                "deduction_amount": "1000",
                "net_amount": "3000",
                "employer_cost": "4800",
            },
        ]
    )
    assert result[0].dimension == "CC-100"
    assert result[0].gross == Decimal("9000")
    assert result[0].net == Decimal("7250")
    assert result[0].record_count == 2


def test_payroll_queries_are_conceptual_and_payroll_sensitive() -> None:
    catalog = build_catalog()
    detail = payroll_detail_query("E-103", "2025-02")
    assert validate_query(detail, catalog, ["hr:payroll"]).valid
    assert not validate_query(detail, catalog, ["hr:read"]).valid
    overtime = overtime_query(date(2025, 2, 1), date(2025, 2, 28), "E-103")
    assert validate_query(overtime, catalog, ["hr:read"]).valid
    assert all("." in item.field for item in detail.select)
    assert not any("employee_payroll" in item.field for item in detail.select)


def test_concept_variations_include_added_and_removed_concepts() -> None:
    result = explain_concept_variations(
        [{"code": "ABSENCE", "name": "Unpaid absence", "amount": 100}],
        [{"code": "OT", "name": "Overtime", "amount": 200}],
    )
    assert [(item.concept_code, item.change) for item in result] == [
        ("ABSENCE", Decimal("-100")),
        ("OT", Decimal("200")),
    ]
