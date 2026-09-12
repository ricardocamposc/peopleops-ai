"""Semantic coverage checks for provider-neutral structured-data evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from peopleops_api.analysis_contracts import AnalysisPlan, SemanticRequest
from peopleops_api.query_contracts import ConceptualQuery, QueryFilter, QueryFilterGroup, QueryResult

CoverageStatus = Literal["NOT_APPLICABLE", "COMPLETE", "INCOMPLETE", "CONTRADICTED"]


@dataclass(frozen=True)
class SemanticCoverageResult:
    status: CoverageStatus
    checked_conditions: int
    missing_conditions: list[dict[str, Any]]
    contradictory_rows: list[dict[str, Any]]
    warnings: list[str]

    def model_dump(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked_conditions": self.checked_conditions,
            "missing_conditions": self.missing_conditions,
            "contradictory_rows": self.contradictory_rows,
            "warnings": self.warnings,
        }


def verify_semantic_coverage(
    semantic: SemanticRequest | None,
    plan: AnalysisPlan | None,
    results: list[tuple[Any, QueryResult]],
) -> SemanticCoverageResult:
    """Verify that planned queries cover structured operational conditions.

    This is intentionally not an MCP validation pass. It does not discover
    schema, authorize, execute, translate SQL, or interpret natural language.
    It compares typed semantic requirements against typed conceptual queries
    and, when projected fields are available, checks returned rows for direct
    contradictions.
    """

    if semantic is None or not semantic.operational_conditions:
        return SemanticCoverageResult(
            status="NOT_APPLICABLE",
            checked_conditions=0,
            missing_conditions=[],
            contradictory_rows=[],
            warnings=[],
        )
    queries = [planned.query for planned in plan.queries] if plan is not None else []
    strategy = plan.combination.strategy if plan is not None else "independent"
    missing = [
        _condition_payload(condition)
        for condition in semantic.operational_conditions
        if not _plan_covers_condition(queries, condition, strategy)
    ]
    contradictions: list[dict[str, Any]] = []
    for planned, result in results:
        for index, row in enumerate(result.rows):
            for condition in semantic.operational_conditions:
                if _row_contradicts_condition(row, condition):
                    contradictions.append(
                        {
                            "purpose": getattr(planned, "purpose", ""),
                            "row_index": index,
                            "condition": _condition_payload(condition),
                        }
                    )
                    break
    warnings: list[str] = []
    if missing:
        warnings.append("Structured evidence does not cover all operational semantic conditions.")
    if contradictions:
        warnings.append("Structured evidence contains rows that contradict operational conditions.")
    if contradictions:
        status: CoverageStatus = "CONTRADICTED"
    elif missing:
        status = "INCOMPLETE"
    else:
        status = "COMPLETE"
    return SemanticCoverageResult(
        status=status,
        checked_conditions=len(semantic.operational_conditions),
        missing_conditions=missing,
        contradictory_rows=contradictions,
        warnings=warnings,
    )


def _query_covers_condition(
    query: ConceptualQuery, required: QueryFilter | QueryFilterGroup
) -> bool:
    available: list[QueryFilter | QueryFilterGroup] = [*query.filters]
    if query.where is not None:
        available.append(query.where)
    return any(_condition_covers(candidate, required) for candidate in available)


def _plan_covers_condition(
    queries: list[ConceptualQuery],
    required: QueryFilter | QueryFilterGroup,
    strategy: str,
) -> bool:
    if any(_query_covers_condition(query, required) for query in queries):
        return True
    if isinstance(required, QueryFilter):
        return False
    if required.operator == "and":
        return all(_plan_covers_condition(queries, child, strategy) for child in required.conditions)
    if required.operator == "or" and strategy == "union":
        return all(_plan_covers_condition(queries, child, strategy) for child in required.conditions)
    return False


def _condition_covers(
    candidate: QueryFilter | QueryFilterGroup, required: QueryFilter | QueryFilterGroup
) -> bool:
    if _condition_payload(candidate) == _condition_payload(required):
        return True
    if isinstance(required, QueryFilter):
        if isinstance(candidate, QueryFilter):
            return False
        return any(_condition_covers(child, required) for child in candidate.conditions)
    if isinstance(candidate, QueryFilter):
        return False
    if any(_condition_covers(child, required) for child in candidate.conditions):
        return True
    if required.operator == "and":
        return all(
            any(_condition_covers(candidate_child, required_child) for candidate_child in candidate.conditions)
            for required_child in required.conditions
        )
    if required.operator != candidate.operator:
        return False
    if len(required.conditions) != len(candidate.conditions):
        return False
    unmatched = list(candidate.conditions)
    for required_child in required.conditions:
        match_index = next(
            (
                index
                for index, candidate_child in enumerate(unmatched)
                if _condition_covers(candidate_child, required_child)
            ),
            None,
        )
        if match_index is None:
            return False
        unmatched.pop(match_index)
    return True


def _row_contradicts_condition(row: dict[str, Any], condition: QueryFilter | QueryFilterGroup) -> bool:
    result = _row_condition_result(row, condition)
    return result is False


def _row_condition_result(
    row: dict[str, Any], condition: QueryFilter | QueryFilterGroup
) -> bool | None:
    if isinstance(condition, QueryFilter):
        column = condition.field.rsplit(".", 1)[-1]
        if column not in row:
            return None
        return _predicate_matches(row[column], condition.operator, condition.value)
    child_results = [_row_condition_result(row, child) for child in condition.conditions]
    known = [value for value in child_results if value is not None]
    if not known:
        return None
    if condition.operator == "and":
        return all(known) if len(known) == len(child_results) else None
    if condition.operator == "or":
        if any(value is True for value in known):
            return True
        return False if len(known) == len(child_results) else None
    child = known[0] if len(known) == 1 and len(child_results) == 1 else None
    return None if child is None else not child


def _predicate_matches(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "is_null":
        return actual is None
    if operator == "not_null":
        return actual is not None
    if operator == "in":
        return actual in (expected or [])
    if operator == "not_in":
        return actual not in (expected or [])
    actual_value = _coerce_comparable(actual)
    expected_value = _coerce_comparable(expected)
    if operator == "eq":
        return actual_value == expected_value
    if operator == "neq":
        return actual_value != expected_value
    if actual_value is None or expected_value is None:
        return False
    try:
        if operator == "gt":
            return actual_value > expected_value
        if operator == "gte":
            return actual_value >= expected_value
        if operator == "lt":
            return actual_value < expected_value
        if operator == "lte":
            return actual_value <= expected_value
    except TypeError:
        return False
    return False


def _coerce_comparable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date | Decimal | int | float | bool) or value is None:
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value
    return value


def _condition_payload(condition: QueryFilter | QueryFilterGroup) -> dict[str, Any]:
    return condition.model_dump(mode="json")
