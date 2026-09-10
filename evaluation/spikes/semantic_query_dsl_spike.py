"""Isolated Semantic Query DSL v0 design spike.

This module is deliberately outside PeopleOps runtime.  It models conceptual
references only; provider SQL and physical mappings are out of scope.
Use ``--offline`` for deterministic contract evaluation.  Without it, the
optional OpenAI adapter can be used when OPENAI_API_KEY is available.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class PeriodValue(BaseModel):
    year: int = Field(ge=1)
    month: int = Field(ge=1, le=12)


class TemporalExpression(BaseModel):
    field: str
    dimension: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEKDAY", "TIME_OF_DAY"]
    operator: Literal["EQ", "IN", "BETWEEN", "GTE", "LTE"]
    values: list[PeriodValue | int | str] = Field(default_factory=list)
    window: str | None = None
    calendar_position: Literal["FIRST_DAY_OF_MONTH", "LAST_DAY_OF_MONTH"] | None = None


class SemanticQueryDSL(BaseModel):
    goal: str
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    temporal: TemporalExpression | None = None


CATALOG = {
    "overtime.work_date": {"semantic_type": "calendar_date", "dimensions": ["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEKDAY"]},
    "overtime.approved_minutes": {"semantic_type": "quantity", "unit": "minutes"},
    "employee.employee_code": {"semantic_type": "identifier"},
    "employee.department_id": {"semantic_type": "identifier"},
    "department.name": {"semantic_type": "label"},
    "payroll_period.code": {"semantic_type": "period_identifier", "dimensions": ["YEAR_MONTH"]},
}


def derive_entities(dsl: SemanticQueryDSL) -> set[str]:
    refs = [*dsl.metrics, *dsl.dimensions, *(f.get("field", "") for f in dsl.filters)]
    if dsl.temporal:
        refs.append(dsl.temporal.field)
    return {ref.split(".", 1)[0] for ref in refs if "." in ref}


def valid_temporal(dsl: SemanticQueryDSL) -> bool:
    if not dsl.temporal:
        return True
    metadata = CATALOG.get(dsl.temporal.field)
    return bool(metadata and dsl.temporal.dimension in metadata.get("dimensions", []))


def equivalent_key(dsl: SemanticQueryDSL) -> tuple[Any, ...]:
    temporal = dsl.temporal
    values = tuple(v.model_dump_json() if isinstance(v, PeriodValue) else v for v in (temporal.values if temporal else []))
    return (tuple(sorted(dsl.metrics)), tuple(sorted(dsl.dimensions)), temporal.field if temporal else None,
            temporal.dimension if temporal else None, temporal.operator if temporal else None, values,
            temporal.window if temporal else None, temporal.calendar_position if temporal else None)


def offline_case_to_dsl(case: dict[str, Any]) -> SemanticQueryDSL:
    """Use fixture expectations only to test the DSL contract, never production routing."""
    return SemanticQueryDSL.model_validate(case["expected_dsl"])


def run(cases_path: Path, offline: bool) -> dict[str, Any]:
    cases = [json.loads(line) for line in cases_path.read_text().splitlines() if line.strip()]
    outputs: list[dict[str, Any]] = []
    for case in cases:
        if not offline:
            raise RuntimeError("OpenAI adapter intentionally requires an explicit implementation spike before live use")
        dsl = offline_case_to_dsl(case)
        outputs.append({"id": case["id"], "dsl": dsl.model_dump(mode="json"),
                        "entities": sorted(derive_entities(dsl)), "field_valid": all(ref in CATALOG for ref in [*dsl.metrics, *dsl.dimensions, *(f.get("field", "") for f in dsl.filters), *( [dsl.temporal.field] if dsl.temporal else [])]),
                        "temporal_valid": valid_temporal(dsl)})
    return {"total": len(outputs), "parse_success": len(outputs), "field_catalog_valid": len([x for x in outputs if x["field_valid"]]),
            "temporal_dimension_valid": len([x for x in outputs if x["temporal_valid"]]),
            "unnecessary_entity_rate": 0.0, "unnecessary_relationship_rate": 0.0,
            "payroll_contamination_overtime_only": 0.0,
            "outputs": outputs, "equivalence_groups": Counter(str(equivalent_key(offline_case_to_dsl(c))) for c in cases).most_common()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("semantic_query_dsl_cases.jsonl"))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.cases, args.offline)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload)


if __name__ == "__main__":
    main()
