from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4

from peopleops_api.analysis_contracts import (
    AnalysisPlan,
    SeniorReview,
    SeniorReviewIssue,
    SemanticRequest,
    StructuredAnswer,
)
from peopleops_api.analysis_workflow import (
    AnalysisWorkflow,
    _apply_structured_multi_query_plan,
    _apply_semantic_coverage_to_review,
    _answer_mentions_structured_row_values,
    _append_structured_result_summary,
    _catalog_conceptual_validation_errors,
    _complete_plan_relationship_entities,
    _answer_needs_structured_result_summary,
    _deterministic_result_facts,
    _semantic_catalog_errors,
)
from peopleops_api.functional_analyst_agent import (
    _authorization_blocked_discovery,
    _clarification_from_failed_submission,
    _infer_semantic_entities,
    _qualify_semantic_operational_conditions,
    _semantic_submission_errors,
)
from peopleops_api.mcp_client import MCPProviderError, _provider_error_code_from_exception, _provider_error_code_from_text
from peopleops_api.mcp_contracts import SecurityContext, TemporalContext
from peopleops_api.models import AnalysisInteraction, Conversation
from peopleops_api.repositories import record_human_review_decision
from peopleops_api.query_contracts import (
    ConceptualQuery,
    QueryFilter,
    QueryFilterGroup,
    QueryMetric,
    QueryPeriod,
    QueryResult,
    QuerySelect,
    QueryValidation,
)
from peopleops_api.query_programmer_agent import _normalize_query_payload, _validate_tool_args
from peopleops_api.senior_reviewer_agent import _review_query_args
from peopleops_api.semantic_coverage import verify_semantic_coverage
from peopleops_api.policy_retrieval import PolicyRetrievalResult, PolicyRetrievalStatus


def test_deterministic_result_facts_expose_numeric_totals_to_synthesis() -> None:
    result = QueryResult(
        request_id="req",
        validation=QueryValidation(valid=True, query_hash="hash", catalog_version="v1"),
        columns=["approved_minutes"],
        rows=[{"approved_minutes": 60}, {"approved_minutes": 120}],
    )
    assert _deterministic_result_facts(result) == {
        "row_count": 2,
        "numeric_sums": {"approved_minutes": 180},
    }


def test_synthesis_row_guard_appends_count_summary_when_answer_omits_table_values() -> None:
    evidence = [
        {
            "type": "structured_data",
            "result": {
                "rows": [
                    {"business_identifier": "SUBJ-001", "display_name": "Ada"},
                    {"business_identifier": "SUBJ-002", "display_name": "Grace"},
                ]
            },
        }
    ]
    response = StructuredAnswer(answer="Matching records are:")

    assert _answer_mentions_structured_row_values(response, evidence) is False
    assert _answer_needs_structured_result_summary(response, evidence) is True
    appended = _append_structured_result_summary(response.answer, evidence)

    assert "2 registros" in appended
    assert "tabla de evidencia de datos" in appended
    assert "SUBJ-001" not in appended
    assert "Grace" not in appended


def test_deterministic_result_facts_expose_declared_metric_conversion() -> None:
    result = QueryResult(
        request_id="req",
        validation=QueryValidation(valid=True, query_hash="hash", catalog_version="v1"),
        columns=["approved_minutes"],
        rows=[{"approved_minutes": 60}, {"approved_minutes": 120}],
    )
    query = ConceptualQuery(
        entities=["overtime"],
        metrics=[
            QueryMetric(
                field="overtime.approved_minutes",
                function="sum",
                alias="total_overtime_hours",
                conversion={
                    "from_unit": "minutes",
                    "to_unit": "hours",
                    "operation": "divide",
                    "factor": 60.0,
                },
            )
        ],
    )

    facts = _deterministic_result_facts(result, query=query)

    assert facts["numeric_sums"] == {"approved_minutes": 180}
    assert facts["derived_numeric_values"] == {"total_overtime_hours": 3.0}


def test_semantic_coverage_rejects_status_only_when_operational_conditions_require_dates() -> None:
    reference_date = date(2026, 9, 11)
    semantic = SemanticRequest(
        goal="current contracts",
        required_capabilities=["employment"],
        entities=["contract", "employee"],
        operational_conditions=[
            QueryFilter(field="contract.status", operator="eq", value="active"),
            QueryFilter(field="contract.start_date", operator="lte", value=reference_date),
            QueryFilterGroup(
                operator="or",
                conditions=[
                    QueryFilter(field="contract.end_date", operator="is_null"),
                    QueryFilter(field="contract.end_date", operator="gte", value=reference_date),
                ],
            ),
        ],
    )
    plan = AnalysisPlan(
        goal="current contracts",
        queries=[
            {
                "purpose": "status-only contract query",
                "query": ConceptualQuery(
                    entities=["contract", "employee"],
                    select=[QuerySelect(field="employee.employee_code")],
                    filters=[QueryFilter(field="contract.status", operator="eq", value="active")],
                    relationships=["contract_employee"],
                ),
            }
        ],
    )

    coverage = verify_semantic_coverage(semantic, plan, [])

    assert coverage.status == "INCOMPLETE"
    assert coverage.checked_conditions == 3
    assert len(coverage.missing_conditions) == 2


def test_semantic_coverage_accepts_grouped_effective_interval_query() -> None:
    reference_date = date(2026, 9, 11)
    semantic = SemanticRequest(
        goal="current contracts",
        required_capabilities=["employment"],
        entities=["contract", "employee"],
        operational_conditions=[
            QueryFilter(field="contract.status", operator="eq", value="active"),
            QueryFilter(field="contract.start_date", operator="lte", value=reference_date),
            QueryFilterGroup(
                operator="or",
                conditions=[
                    QueryFilter(field="contract.end_date", operator="is_null"),
                    QueryFilter(field="contract.end_date", operator="gte", value=reference_date),
                ],
            ),
        ],
    )
    plan = AnalysisPlan(
        goal="current contracts",
        queries=[
            {
                "purpose": "current contract query",
                "query": ConceptualQuery(
                    entities=["contract", "employee"],
                    select=[
                        QuerySelect(field="employee.employee_code"),
                        QuerySelect(field="contract.start_date"),
                        QuerySelect(field="contract.end_date"),
                    ],
                    filters=[QueryFilter(field="contract.status", operator="eq", value="active")],
                    where=QueryFilterGroup(
                        operator="and",
                        conditions=[
                            QueryFilter(
                                field="contract.start_date",
                                operator="lte",
                                value=reference_date,
                            ),
                            QueryFilterGroup(
                                operator="or",
                                conditions=[
                                    QueryFilter(field="contract.end_date", operator="is_null"),
                                    QueryFilter(
                                        field="contract.end_date",
                                        operator="gte",
                                        value=reference_date,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    relationships=["contract_employee"],
                ),
            }
        ],
    )
    result = QueryResult(
        request_id="req",
        validation=QueryValidation(valid=True, query_hash="hash", catalog_version="v1"),
        columns=["employee_code", "start_date", "end_date"],
        rows=[
            {"employee_code": "E-101", "start_date": "2024-01-08", "end_date": None},
            {"employee_code": "E-103", "start_date": "2023-05-02", "end_date": None},
        ],
    )

    coverage = verify_semantic_coverage(semantic, plan, [(plan.queries[0], result)])

    assert coverage.status == "COMPLETE"
    assert coverage.missing_conditions == []
    assert coverage.contradictory_rows == []


def test_semantic_coverage_accepts_union_plan_covering_or_conditions() -> None:
    reference_date = date(2026, 9, 11)
    semantic = SemanticRequest(
        goal="records with open-ended or future end",
        operational_conditions=[
            QueryFilterGroup(
                operator="or",
                conditions=[
                    QueryFilter(field="record.valid_to", operator="is_null"),
                    QueryFilter(field="record.valid_to", operator="gte", value=reference_date),
                ],
            )
        ],
    )
    plan = AnalysisPlan(
        goal="records with open-ended or future end",
        combination={
            "strategy": "union",
            "deduplication_keys": ["record.id"],
            "partial_failure_policy": "fail_analysis",
            "reason": "The condition is covered by separate alternative evidence sets.",
        },
        queries=[
            {
                "purpose": "open-ended records",
                "query": ConceptualQuery(
                    entities=["record"],
                    select=[QuerySelect(field="record.id")],
                    filters=[QueryFilter(field="record.valid_to", operator="is_null")],
                ),
            },
            {
                "purpose": "future-ended records",
                "query": ConceptualQuery(
                    entities=["record"],
                    select=[QuerySelect(field="record.id")],
                    filters=[
                        QueryFilter(field="record.valid_to", operator="gte", value=reference_date)
                    ],
                ),
            },
        ],
    )

    coverage = verify_semantic_coverage(semantic, plan, [])

    assert coverage.status == "COMPLETE"
    assert coverage.missing_conditions == []


def test_semantic_coverage_handles_non_comparable_row_values() -> None:
    semantic = SemanticRequest(
        goal="threshold records",
        operational_conditions=[
            QueryFilter(field="vacation_balance.available_days", operator="lt", value=10)
        ],
    )
    plan = AnalysisPlan(
        goal="threshold records",
        queries=[
            {
                "purpose": "threshold records",
                "query": ConceptualQuery(
                    entities=["vacation_balance"],
                    select=[QuerySelect(field="vacation_balance.available_days")],
                    filters=[
                        QueryFilter(
                            field="vacation_balance.available_days",
                            operator="lt",
                            value=10,
                        )
                    ],
                ),
            }
        ],
    )
    result = QueryResult(
        request_id="req",
        validation=QueryValidation(valid=True, query_hash="hash", catalog_version="v1"),
        columns=["available_days"],
        rows=[{"available_days": "not numeric"}],
    )

    coverage = verify_semantic_coverage(semantic, plan, [(plan.queries[0], result)])

    assert coverage.status == "CONTRADICTED"
    assert coverage.contradictory_rows == [
        {
            "purpose": "threshold records",
            "row_index": 0,
            "condition": {
                "field": "vacation_balance.available_days",
                "operator": "lt",
                "value": 10,
            },
        }
    ]


def test_query_programmer_validation_tool_accepts_direct_query_args() -> None:
    direct_args = {
        "entities": ["employee"],
        "select": [{"field": "employee.employee_code"}],
        "time_scope": {
            "type": "date_range",
            "field": "employee.hire_date",
            "start": "2026-01-01",
            "end": "2026-12-31",
        },
        "order_by": [],
        "dimensions": [],
    }

    assert _validate_tool_args(direct_args) == {"query": direct_args}
    assert _validate_tool_args({"query": direct_args}) == {"query": direct_args}
    assert _validate_tool_args({"unexpected": "shape"}) == {"unexpected": "shape"}


def test_query_programmer_normalizes_equivalent_query_payload_shapes() -> None:
    from reference_mcp_server.discovery import build_catalog

    catalog = build_catalog()
    payload = {
        "entities": ["attendance"],
        "metrics": [
            {"alias": "total_absence", "field": "sum(absence_minutes)"},
        ],
        "filters": [{"field": "work_date", "operator": "gte", "value": "2026-01-01"}],
        "time_scope": {
            "type": "date_range",
            "field": "work_date",
            "start": "2026-01-01",
            "end": "2026-12-31",
        },
        "order_by": [{"reference": "work_date", "direction": "asc"}],
        "grouping_requirements": ["month(work_date)"],
        "ordering_requirements": ["month(work_date)"],
        "where": {
            "operator": "and",
            "conditions": [
                {"field": "work_date", "operator": "eq", "value": "2026-01-15"},
                {"field": "work_date", "operator": "eq", "value": "2026-02-15"},
            ],
        },
    }

    normalized = _normalize_query_payload(payload, catalog)

    assert "grouping_requirements" not in normalized
    assert "ordering_requirements" not in normalized
    assert normalized["metrics"] == [
        {"alias": "total_absence", "field": "attendance.absence_minutes", "function": "sum"}
    ]
    assert normalized["filters"][0]["field"] == "attendance.work_date"
    assert normalized["time_scope"]["field"] == "attendance.work_date"
    assert normalized["dimensions"] == ["month(attendance.work_date)"]
    assert normalized["order_by"] == [
        {"reference": "month(attendance.work_date)", "direction": "asc"}
    ]
    assert normalized["where"] == {
        "field": "attendance.work_date",
        "operator": "in",
        "value": ["2026-01-15", "2026-02-15"],
    }


def test_query_programmer_does_not_duplicate_selected_grouping_fields() -> None:
    from reference_mcp_server.discovery import build_catalog

    payload = {
        "entities": ["attendance_incident", "employee"],
        "select": [
            {"field": "employee.id"},
            {"field": "employee.first_name"},
            {"field": "employee.last_name"},
        ],
        "metrics": [
            {"alias": "incident_count", "field": "attendance_incident.id", "function": "count"}
        ],
        "grouping_requirements": ["employee.id", "employee.first_name", "employee.last_name"],
        "order_by": [{"reference": "incident_count", "direction": "desc"}],
    }

    normalized = _normalize_query_payload(payload, build_catalog())

    assert normalized["dimensions"] == []


def test_structured_comparison_expands_current_period_query_to_multi_query() -> None:
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="compare current and previous period totals",
        comparison_requirements=["compare both requested periods"],
    )
    plan = AnalysisPlan(
        goal="compare current and previous period totals",
        queries=[
            {
                "purpose": "period total",
                "query": ConceptualQuery(
                    entities=["overtime"],
                    metrics=[
                        QueryMetric(
                            field="overtime.approved_minutes",
                            function="sum",
                            alias="total_approved_minutes",
                        )
                    ],
                    filters=[
                        QueryFilter(field="overtime.work_date", operator="gte", value="2026-09-01")
                    ],
                    where=QueryFilterGroup(
                        operator="and",
                        conditions=[
                            QueryFilter(
                                field="overtime.work_date",
                                operator="lte",
                                value="2026-09-30",
                            )
                        ],
                    ),
                    time_scope=QueryPeriod(
                        type="date_range",
                        field="overtime.work_date",
                        start=date(2026, 9, 1),
                        end=date(2026, 9, 30),
                    ),
                    order_by=[{"reference": "overtime.work_date", "direction": "asc"}],
                ),
            }
        ],
    )
    context = TemporalContext(
        source_current_date=date(2026, 9, 11),
        source_current_timestamp=datetime(2026, 9, 11, tzinfo=UTC),
        current_year=2026,
        current_month=9,
    )

    expanded = _apply_structured_multi_query_plan(plan, semantic, context, build_catalog())

    assert expanded.combination.strategy == "comparison"
    assert [item.logical_role for item in expanded.queries] == ["current", "previous"]
    assert [item.query.time_scope.period.month for item in expanded.queries] == [9, 8]
    assert all(not item.query.filters for item in expanded.queries)
    assert all(item.query.where is None for item in expanded.queries)
    assert all(not item.query.order_by for item in expanded.queries)


def test_structured_comparison_expands_multiple_temporal_filter_windows() -> None:
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="compare two closed periods",
        comparison_requirements=["compare both requested periods"],
    )
    plan = AnalysisPlan(
        goal="compare two closed periods",
        queries=[
            {
                "purpose": "period total",
                "query": ConceptualQuery(
                    entities=["overtime"],
                    metrics=[
                        QueryMetric(
                            field="overtime.approved_minutes",
                            function="sum",
                            alias="total_approved_minutes",
                        )
                    ],
                    filters=[
                        QueryFilter(field="overtime.work_date", operator="gte", value="2026-09-01"),
                        QueryFilter(field="overtime.work_date", operator="lte", value="2026-09-30"),
                        QueryFilter(field="overtime.work_date", operator="gte", value="2026-08-01"),
                        QueryFilter(field="overtime.work_date", operator="lte", value="2026-08-31"),
                    ],
                    order_by=[{"reference": "overtime.work_date", "direction": "asc"}],
                ),
            }
        ],
    )
    context = TemporalContext(
        source_current_date=date(2026, 9, 11),
        source_current_timestamp=datetime(2026, 9, 11, tzinfo=UTC),
        current_year=2026,
        current_month=9,
    )

    expanded = _apply_structured_multi_query_plan(plan, semantic, context, build_catalog())

    assert expanded.combination.strategy == "comparison"
    assert [item.logical_role for item in expanded.queries] == ["previous", "current"]
    assert [(item.query.time_scope.start, item.query.time_scope.end) for item in expanded.queries] == [
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
    ]
    assert all(not item.query.filters for item in expanded.queries)
    assert all(not item.query.order_by for item in expanded.queries)


def test_structured_comparison_uses_month_grain_for_multi_month_range() -> None:
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="compare multiple periods",
        comparison_requirements=["compare requested periods"],
    )
    plan = AnalysisPlan(
        goal="compare multiple periods",
        queries=[
            {
                "purpose": "period series",
                "query": ConceptualQuery(
                    entities=["overtime"],
                    metrics=[
                        QueryMetric(
                            field="overtime.approved_minutes",
                            function="sum",
                            alias="total_approved_minutes",
                        )
                    ],
                    dimensions=["overtime.work_date"],
                    order_by=[{"reference": "overtime.work_date", "direction": "asc"}],
                    time_scope=QueryPeriod(
                        type="date_range",
                        field="overtime.work_date",
                        start=date(2026, 1, 1),
                        end=date(2026, 3, 31),
                    ),
                ),
            }
        ],
    )

    normalized = _apply_structured_multi_query_plan(plan, semantic, None, build_catalog())

    assert normalized.queries[0].query.dimensions == ["month(overtime.work_date)"]
    assert normalized.queries[0].query.order_by[0].reference == "month(overtime.work_date)"


def test_functional_analyst_converts_rejected_submission_to_clarification() -> None:
    semantic = _clarification_from_failed_submission(
        [
            {
                "tool": "submit_semantic_request",
                "output": {
                    "reason": "INCOMPLETE_SEMANTIC_REQUEST",
                    "errors": ["comparison requires a measurable business subject"],
                },
            }
        ],
        "Compare January with the previous period.",
    )

    assert semantic is not None
    assert semantic.needs_clarification is True
    assert semantic.requires_structured_data is False
    assert semantic.questions_or_missing_information == [
        "comparison requires a measurable business subject"
    ]


def test_functional_analyst_authorization_block_survives_later_unrelated_catalog() -> None:
    denied = {
        "tool": "discover_scoped_catalog",
        "output": {"status": "error", "error": {"code": "AUTHORIZATION_DENIED"}},
    }
    wrapped_denied = {
        "tool": "discover_scoped_catalog",
        "output": {"status": "error", "error": {"code": "ToolException", "message": "AUTHORIZATION_DENIED"}},
    }
    success = {"tool": "discover_scoped_catalog", "output": {"status": "success"}}

    assert _authorization_blocked_discovery([denied]) is True
    assert _authorization_blocked_discovery([wrapped_denied]) is True
    assert _authorization_blocked_discovery([denied, success]) is True


def test_mcp_provider_error_code_is_preserved_from_exception_text() -> None:
    assert (
        _provider_error_code_from_text("Error executing tool: AUTHORIZATION_DENIED")
        == "AUTHORIZATION_DENIED"
    )
    grouped = ExceptionGroup(
        "transport wrapper",
        [ExceptionGroup("task wrapper", [MCPProviderError("AUTHORIZATION_DENIED", "denied", request_id="r")])],
    )
    assert _provider_error_code_from_exception(grouped) == "AUTHORIZATION_DENIED"


def test_senior_reviewer_query_tools_accept_direct_query_args() -> None:
    direct_args = {
        "entities": ["employee"],
        "select": [{"field": "employee.employee_code"}],
    }

    assert _review_query_args(None, {}, direct_args) == (0, direct_args)
    assert _review_query_args(1, direct_args, {}) == (1, direct_args)


def test_senior_review_approval_is_overridden_when_semantic_coverage_is_incomplete() -> None:
    reference_date = date(2026, 9, 11)
    semantic = SemanticRequest(
        goal="current contracts",
        entities=["contract", "employee"],
        operational_conditions=[
            QueryFilter(field="contract.status", operator="eq", value="active"),
            QueryFilter(field="contract.start_date", operator="lte", value=reference_date),
        ],
    )
    plan = AnalysisPlan(
        goal="current contracts",
        queries=[
            {
                "purpose": "status-only contract query",
                "query": ConceptualQuery(
                    entities=["contract", "employee"],
                    select=[QuerySelect(field="employee.employee_code")],
                    filters=[QueryFilter(field="contract.status", operator="eq", value="active")],
                    relationships=["contract_employee"],
                ),
            }
        ],
    )
    review = SeniorReview(status="APPROVE", summary="Looks valid.", confidence=1.0)

    revised, coverage = _apply_semantic_coverage_to_review(review, semantic, plan)

    assert coverage.status == "INCOMPLETE"
    assert revised.status == "REVISE"
    assert revised.confidence == 0.4
    assert revised.issues[0].category == "semantic_coverage"


@dataclass
class FakeModel:
    outputs: list[object]
    model_name: str = "fake-structured-model"
    _last_by_type: dict[type[object], object] | None = None

    def parse(self, *, purpose, instructions, output_model):
        # The production workflow performs a second, catalog-grounded
        # SemanticRequest pass before planning. Keep these unit fixtures
        # compatible with the older one-pass setup without changing the
        # workflow contract: only consume the next queued artifact when it is
        # for the requested typed output.
        if self._last_by_type is None:
            self._last_by_type = {}
        index = next(
            (
                index
                for index, candidate in enumerate(self.outputs)
                if isinstance(candidate, output_model)
            ),
            None,
        )
        if index is None:
            output = self._last_by_type.get(output_model)
            if output is None:
                if output_model is SeniorReview:
                    output = SeniorReview(
                        status="APPROVE",
                        summary="Fake reviewer approval for existing workflow fixture.",
                        confidence=1.0,
                    )
                    self._last_by_type[output_model] = output
                    return output
                raise AssertionError(f"no fake output for {output_model.__name__}")
        else:
            output = self.outputs.pop(index)
            self._last_by_type[output_model] = output
        assert isinstance(output, output_model)
        return output


class FakeGateway:
    def __init__(self, *, invalid_first: bool = False, empty: bool = False):
        self.catalog_calls = 0
        self.validation_calls = 0
        self.execution_calls = 0
        self.invalid_first = invalid_first
        self.empty = empty

    def discover_catalog(self, *, request_id, security):
        from reference_mcp_server.discovery import build_catalog

        self.catalog_calls += 1
        return build_catalog()

    def validate_query(self, query, *, request_id, security):
        self.validation_calls += 1
        invalid = self.invalid_first and self.validation_calls == 1
        return QueryValidation(
            request_id=request_id,
            valid=not invalid,
            query_hash="hash",
            catalog_version="2026.08",
            errors=["invalid proposed query"] if invalid else [],
        )

    def execute_query(self, query, *, request_id, security):
        self.execution_calls += 1
        rows = [] if self.empty else [{"employee_code": "E001"}]
        return QueryResult(
            request_id=request_id,
            validation=QueryValidation(
                request_id=request_id, valid=True, query_hash="hash", catalog_version="2026.08"
            ),
            columns=["employee_code"],
            rows=rows,
        )


@dataclass
class FakePolicyProvider:
    result: PolicyRetrievalResult

    def __post_init__(self):
        self.calls = []

    def retrieve(self, query, *, as_of, filters, top_k):
        self.calls.append({"query": query, "as_of": as_of, "filters": filters, "top_k": top_k})
        return self.result


def _interaction(*, question="Which employees are active?", evaluation=True):
    conversation = (
        Conversation(metadata_={"evaluation_structured_hr": True}) if evaluation else None
    )
    return AnalysisInteraction(
        request_id=uuid4(),
        question=question,
        stage_history=[],
        conversation=conversation,
    )


def _plan():
    return AnalysisPlan(
        goal="active employees",
        queries=[
            {
                "purpose": "active workforce",
                "query": ConceptualQuery(
                    entities=["employee"], select=[QuerySelect(field="employee.employee_code")]
                ),
            }
        ],
    )


def _policy_semantic(*, structured: bool, status_query: str = "Vacation approval"):
    return SemanticRequest(
        goal="evaluate vacation request",
        required_capabilities=["vacation"] if structured else [],
        entities=["vacation"] if structured else [],
        requires_structured_data=structured,
        requires_policy=True,
        policy_query=status_query,
        policy_as_of=date(2026, 11, 1),
    )


def _policy_plan():
    return AnalysisPlan(
        goal="evaluate vacation request",
        queries=[_plan().queries[0]],
        policy={"query": "Vacation approval", "as_of": date(2026, 11, 1)},
    )


def test_functional_analyst_accepts_filtered_list_requests_with_grounded_required_sources():
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="Retrieve active contracts",
        required_information=["database access"],
        required_sources=["contract"],
        filters=["contract.status = active"],
        data_retrieval_request="Retrieve employee identifiers and contract details for active contracts.",
        entities=[],
        measures=[],
        dimensions=[],
        requires_structured_data=True,
        requires_policy=False,
    )

    assert _semantic_submission_errors(semantic, build_catalog()) == []


def test_functional_analyst_accepts_capability_required_sources():
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="Retrieve contracts ending soon",
        required_information=["database access"],
        required_sources=["employment"],
        filters=["contract.end_date between reference date and next 60 days"],
        data_retrieval_request="Retrieve contracts ending in the next 60 days.",
        entities=["contract"],
        measures=[],
        dimensions=[],
        requires_structured_data=True,
        requires_policy=False,
    )

    assert _semantic_submission_errors(semantic, build_catalog()) == []


def test_functional_analyst_round_budget_tracks_tool_count():
    from peopleops_api.functional_analyst_agent import (
        FUNCTIONAL_ANALYST_EXTRA_SUBMISSION_ROUNDS,
        MIN_FUNCTIONAL_ANALYST_ROUNDS,
        _round_budget_for_tool_count,
    )

    assert _round_budget_for_tool_count(3) == 3 + FUNCTIONAL_ANALYST_EXTRA_SUBMISSION_ROUNDS
    assert _round_budget_for_tool_count(6) == 6 + FUNCTIONAL_ANALYST_EXTRA_SUBMISSION_ROUNDS
    assert _round_budget_for_tool_count(6, configured=2) == MIN_FUNCTIONAL_ANALYST_ROUNDS
    assert _round_budget_for_tool_count(6, configured=9) == 9


def test_functional_analyst_qualifies_unambiguous_operational_condition_fields():
    from reference_mcp_server.discovery import build_catalog

    catalog = build_catalog()
    scoped_catalog = catalog.model_copy(
        update={
            "entities": [
                entity for entity in catalog.entities if entity.entity_id == "contract"
            ],
            "capabilities": [
                capability
                for capability in catalog.capabilities
                if capability.name == "employment"
            ],
        }
    )
    semantic = SemanticRequest(
        goal="contracts ending soon",
        required_information=["database access"],
        required_sources=["employment"],
        entities=["contract"],
        filters=["end_date in the next 60 days"],
        data_retrieval_request="Retrieve contracts ending in the next 60 days.",
        operational_conditions=[
            QueryFilter(field="end_date", operator="gte", value=date(2026, 9, 11))
        ],
    )

    qualified = _qualify_semantic_operational_conditions(semantic, scoped_catalog)

    assert qualified.operational_conditions == [
        QueryFilter(field="contract.end_date", operator="gte", value=date(2026, 9, 11))
    ]
    assert _semantic_submission_errors(qualified, scoped_catalog) == []


def test_functional_analyst_rejects_ambiguous_unqualified_operational_condition_fields():
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="records by status",
        required_information=["database access"],
        required_sources=["employment"],
        entities=[],
        filters=["status active"],
        data_retrieval_request="Retrieve records by status.",
        operational_conditions=[QueryFilter(field="status", operator="eq", value="active")],
    )

    qualified = _qualify_semantic_operational_conditions(semantic, build_catalog())

    assert qualified.operational_conditions == [
        QueryFilter(field="status", operator="eq", value="active")
    ]
    assert (
        "UNQUALIFIED_FIELD: operational_conditions:status"
        in _semantic_submission_errors(qualified, build_catalog())
    )


def test_functional_analyst_qualifies_fields_using_semantic_entity_scope():
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="active records in an organization unit",
        required_information=["database access"],
        required_sources=["employee", "department"],
        entities=[],
        filters=["active status"],
        data_retrieval_request="Retrieve active subject records for the organization unit.",
        operational_conditions=[QueryFilter(field="status", operator="eq", value="active")],
    )

    qualified = _qualify_semantic_operational_conditions(semantic, build_catalog())

    assert qualified.operational_conditions == [
        QueryFilter(field="employee.status", operator="eq", value="active")
    ]
    assert _semantic_submission_errors(qualified, build_catalog()) == []


def test_functional_analyst_rejects_flat_mutually_exclusive_operational_conditions():
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="records effective as of a reference date",
        required_information=["database access"],
        required_sources=["employment"],
        entities=["contract"],
        filters=["records effective as of a reference date"],
        data_retrieval_request="Retrieve records effective as of the reference date.",
        operational_conditions=[
            QueryFilter(field="contract.end_date", operator="is_null"),
            QueryFilter(field="contract.end_date", operator="gte", value=date(2026, 9, 11)),
        ],
    )

    errors = _semantic_submission_errors(semantic, build_catalog())

    assert any("CONTRADICTORY_OPERATIONAL_CONDITIONS" in error for error in errors)


def test_functional_analyst_accepts_grouped_alternative_operational_conditions():
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="records effective as of a reference date",
        required_information=["database access"],
        required_sources=["employment"],
        entities=["contract"],
        filters=["records effective as of a reference date"],
        data_retrieval_request="Retrieve records effective as of the reference date.",
        operational_conditions=[
            QueryFilterGroup(
                operator="or",
                conditions=[
                    QueryFilter(field="contract.end_date", operator="is_null"),
                    QueryFilter(
                        field="contract.end_date",
                        operator="gte",
                        value=date(2026, 9, 11),
                    ),
                ],
            )
        ],
    )

    assert _semantic_submission_errors(semantic, build_catalog()) == []


def test_functional_analyst_infers_entities_from_grounded_operational_conditions():
    from reference_mcp_server.discovery import build_catalog

    catalog = build_catalog()
    semantic = SemanticRequest(
        goal="records effective as of a reference date",
        required_information=["database access"],
        required_sources=["employment"],
        entities=[],
        filters=["records effective as of a reference date"],
        data_retrieval_request="Retrieve records effective as of the reference date.",
        operational_conditions=[
            QueryFilter(field="contract.start_date", operator="lte", value=date(2026, 9, 11)),
            QueryFilterGroup(
                operator="or",
                conditions=[
                    QueryFilter(field="contract.end_date", operator="is_null"),
                    QueryFilter(
                        field="contract.end_date",
                        operator="gte",
                        value=date(2026, 9, 11),
                    ),
                ],
            ),
        ],
    )

    inferred = _infer_semantic_entities(semantic, catalog)

    assert inferred.entities == ["contract"]
    assert _semantic_submission_errors(inferred, catalog) == []


def test_finalize_response_persists_insufficient_data_status(db_session):
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    workflow = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(), model=FakeModel([]), security=SecurityContext()
    )

    result = workflow._finalize_response(
        {
            "interaction": interaction,
            "question": interaction.question,
            "workflow_error": {
                "stage": "understanding",
                "code": "FUNCTIONAL_ANALYST_FAILED",
                "detail": "FUNCTIONAL_ANALYST_ROUND_BUDGET_EXHAUSTED",
            },
        }
    )["interaction"]

    assert result.status == "insufficient_data"
    assert result.response["status"] == "insufficient_data"
    assert result.error_type == "FUNCTIONAL_ANALYST_FAILED"
    assert result.error_detail == "FUNCTIONAL_ANALYST_ROUND_BUDGET_EXHAUSTED"
    assert "FUNCTIONAL_ANALYST_ROUND_BUDGET_EXHAUSTED" not in result.response["answer"]
    assert all(
        "FUNCTIONAL_ANALYST_ROUND_BUDGET_EXHAUSTED" not in warning
        for warning in result.response["warnings"]
    )
    assert (
        result.evaluation_trace["workflow_error"]["detail"]
        == "FUNCTIONAL_ANALYST_ROUND_BUDGET_EXHAUSTED"
    )


def test_boundary_failure_is_closed_by_final_response_node(db_session):
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    workflow = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(), model=FakeModel([]), security=SecurityContext()
    )

    result = workflow._fail(
        interaction,
        "FUNCTIONAL_ANALYST_FAILED",
        "FUNCTIONAL_ANALYST_ROUND_BUDGET_EXHAUSTED",
    )

    assert result.status == "failed"
    assert result.response["status"] == "insufficient_data"
    assert "FUNCTIONAL_ANALYST_ROUND_BUDGET_EXHAUSTED" not in result.response["answer"]
    assert [event["stage"] for event in result.stage_history][-1] == "finalize_response"
    assert result.stage_history[-1]["status"] == "completed"
    assert result.error_detail == "FUNCTIONAL_ANALYST_ROUND_BUDGET_EXHAUSTED"


def test_workflow_uses_typed_model_gateway_and_persists_observable_stages(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            StructuredAnswer(answer="The matching employee is E001.", key_findings=["E001"]),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(),
    ).run(interaction)

    assert result.status == "completed"
    assert result.semantic_request["goal"] == "active employees"
    assert result.evidence[0]["type"] == "structured_data"
    assert {event["stage"] for event in result.stage_history} >= {
        "workflow",
        "understanding",
        "discovery",
        "planning",
        "query_execution",
        "evidence_merge",
        "synthesis",
    }
    assert "chain" not in str(result.response).lower()


def test_workflow_does_not_complete_when_structured_evidence_lacks_semantic_coverage(
    db_session,
):
    reference_date = date(2026, 9, 11)
    semantic = SemanticRequest(
        goal="current contracts",
        required_capabilities=["employment"],
        entities=["contract", "employee"],
        operational_conditions=[
            QueryFilter(field="contract.status", operator="eq", value="active"),
            QueryFilter(field="contract.start_date", operator="lte", value=reference_date),
            QueryFilterGroup(
                operator="or",
                conditions=[
                    QueryFilter(field="contract.end_date", operator="is_null"),
                    QueryFilter(field="contract.end_date", operator="gte", value=reference_date),
                ],
            ),
        ],
    )
    plan = AnalysisPlan(
        goal="current contracts",
        queries=[
            {
                "purpose": "status-only contract query",
                "query": ConceptualQuery(
                    entities=["contract", "employee"],
                    select=[QuerySelect(field="employee.employee_code")],
                    filters=[QueryFilter(field="contract.status", operator="eq", value="active")],
                    relationships=["contract_employee"],
                ),
            }
        ],
    )
    model = FakeModel([semantic, plan])
    interaction = _interaction(question="Que empleados tienen contrato vigente?")
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(),
    ).run(interaction)

    assert result.status == "insufficient_data"
    assert result.response["status"] == "insufficient_data"
    assert result.evidence == []
    assert result.evaluation_trace["senior_reviews"][0]["semantic_coverage"]["status"] == "INCOMPLETE"


def test_evaluation_trace_correlates_happy_path_plan_validation_and_execution(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            StructuredAnswer(answer="The matching employee is E001."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(), model=model, security=SecurityContext()
    ).run(interaction)

    trace = result.evaluation_trace
    assert len(trace["planning_attempts"]) == 1
    assert len(trace["planning_attempts"][0]["conceptual_queries"]) == 1
    assert trace["provider_validations"][0]["accepted"] is True
    assert trace["provider_executions"][0]["success"] is True
    assert trace["provider_validations"][0]["query"] == trace["provider_executions"][0]["query"]
    assert (
        trace["provider_validations"][0]["query"]
        == trace["planning_attempts"][0]["conceptual_queries"][0]["query"]
    )


def test_evaluation_trace_keeps_validation_rejection_out_of_execution(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    gateway = FakeGateway(invalid_first=True)
    result = AnalysisWorkflow(
        session=db_session,
        gateway=gateway,
        model=model,
        security=SecurityContext(),
        max_replans=0,
    ).run(interaction)

    assert result.status == "insufficient_data"
    assert result.evaluation_trace["provider_validations"][0]["accepted"] is False
    assert result.evaluation_trace["provider_executions"] == []
    assert gateway.execution_calls == 0


def test_evaluation_trace_records_replanning_attempts_and_feedback(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            _plan(),
            StructuredAnswer(answer="The matching employee is E001."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(invalid_first=True),
        model=model,
        security=SecurityContext(),
    ).run(interaction)

    trace = result.evaluation_trace
    assert len(trace["planning_attempts"]) == 2
    assert trace["planning_attempts"][1]["provider_feedback"] == ["invalid proposed query"]
    assert trace["provider_validations"][0]["accepted"] is False
    assert trace["provider_validations"][1]["accepted"] is True
    assert trace["provider_executions"][0]["attempt_number"] == 2
    assert trace["replan_count"] == 1


def test_final_senior_revise_is_persisted_as_failed_after_replan_budget(db_session):
    revision = SeniorReview(
        status="REVISE",
        issues=[
            SeniorReviewIssue(
                category="logic",
                severity="high",
                issue="The plan needs correction.",
                correction_guidance="Return a corrected plan.",
            )
        ],
        summary="The plan needs correction.",
        confidence=0.9,
    )
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            revision,
            _plan(),
            revision.model_copy(deep=True),
            StructuredAnswer(answer="No executable plan was approved."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(),
        max_replans=1,
    ).run(interaction)

    senior_reviews = result.evaluation_trace["senior_reviews"]
    assert [item["status"] for item in senior_reviews] == ["REVISE", "FAILED"]
    assert senior_reviews[-1]["model_status"] == "REVISE"
    assert senior_reviews[-1]["failure_reason"] == "SENIOR_REVIEW_REPAIR_BUDGET_EXHAUSTED"
    assert len(result.evaluation_trace["planning_attempts"]) == 2
    senior_stage_statuses = [
        event["status"]
        for event in result.stage_history
        if event["stage"] == "senior_review" and event["status"] != "running"
    ]
    # The first REVISE is an intermediate transition; the final decision is
    # the second review and must be terminal FAILED.
    assert senior_stage_statuses[-1] == "failed"


def test_evaluation_trace_persists_authorization_decision(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="payroll totals", required_capabilities=["payroll"], entities=["payroll"]
            ),
            AnalysisPlan(
                goal="payroll totals",
                queries=[
                    {
                        "purpose": "payroll totals",
                        "query": ConceptualQuery(
                            entities=["payroll"],
                            select=[QuerySelect(field="payroll.net_amount")],
                        ),
                    }
                ],
            ),
        ]
    )
    interaction = _interaction(question="What are the payroll totals?")
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(scopes=["hr:read"]),
    ).run(interaction)

    assert result.status == "pending_human_review"
    assert result.human_review_id is not None
    assert result.response["answer"] == (
        "La solicitud requiere permisos adicionales para consultar esos datos."
    )
    assert result.error_detail == "payroll access requires the hr:payroll scope"
    assert result.warnings == [
        "La solicitud requiere permisos adicionales para consultar esos datos."
    ]
    assert result.evaluation_trace["authorization"] == {
        "required": True,
        "enforcement_enabled": True,
        "granted": False,
        "decision": "denied",
        "scope_present": False,
    }


def test_evaluation_trace_records_independent_period_queries(db_session):
    period_plan = AnalysisPlan(
        goal="compare workforce periods",
        queries=[
            {"purpose": "period A", "logical_role": "current", "query": _plan().queries[0].query},
            {"purpose": "period B", "logical_role": "previous", "query": _plan().queries[0].query},
        ],
    )
    model = FakeModel(
        [
            SemanticRequest(
                goal="compare workforce periods",
                required_capabilities=["workforce"],
                entities=["employee"],
            ),
            period_plan,
            StructuredAnswer(answer="The periods were compared."),
        ]
    )
    interaction = _interaction(question="Compare this period with the previous period.")
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(), model=model, security=SecurityContext()
    ).run(interaction)

    trace = result.evaluation_trace
    assert [
        item["logical_query_role"] for item in trace["planning_attempts"][0]["conceptual_queries"]
    ] == [
        "current",
        "previous",
    ]
    assert len(trace["provider_validations"]) == 2
    assert len(trace["provider_executions"]) == 2
    assert {item["query_index"] for item in trace["provider_executions"]} == {0, 1}


def test_evaluation_trace_marks_zero_row_execution_as_valid(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            StructuredAnswer(answer="No records matched the requested criteria."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(empty=True), model=model, security=SecurityContext()
    ).run(interaction)

    assert result.status == "completed"
    assert result.evaluation_trace["provider_executions"][0]["success"] is True
    assert (
        result.evaluation_trace["provider_executions"][0]["result_verification_status"]
        == "ZERO_ROWS"
    )


def test_payroll_without_scope_is_denied_even_when_review_is_enabled(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="payroll explanation",
                required_capabilities=["payroll"],
                entities=["payroll"],
            ),
            AnalysisPlan(
                goal="payroll explanation",
                queries=[
                    {
                        "purpose": "payroll totals",
                        "query": ConceptualQuery(
                            entities=["payroll"],
                            select=[QuerySelect(field="payroll.net_amount")],
                        ),
                    }
                ],
            ),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(scopes=["hr:read"]),
    ).run(interaction)

    assert result.status == "pending_human_review"
    assert result.error_type == "AUTHORIZATION_ERROR"
    assert result.error_detail == "payroll access requires the hr:payroll scope"
    assert result.human_review_id is not None
    assert result.human_review_status == "pending"
    assert result.evaluation_trace["provider_validations"] == []
    assert result.evaluation_trace["provider_executions"] == []


def test_payroll_entity_without_capability_is_denied_before_planning(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="workers earning more than 1000",
                required_capabilities=[],
                entities=["payroll"],
                operational_conditions=[
                    QueryFilter(field="payroll.gross_amount", operator="gt", value=1000)
                ],
            ),
        ]
    )
    interaction = _interaction(question="Que trabajadores ganan más de 1000?")
    db_session.add(interaction)
    db_session.commit()
    gateway = FakeGateway()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=gateway,
        model=model,
        security=SecurityContext(scopes=["hr:read"]),
    ).run(interaction)

    assert result.status == "pending_human_review"
    assert result.error_type == "AUTHORIZATION_ERROR"
    assert result.human_review_id is not None
    assert result.evaluation_trace["authorization"]["required"] is True
    assert result.evaluation_trace["authorization"]["decision"] == "denied"
    assert result.query_plan is None
    assert gateway.validation_calls == 0
    assert gateway.execution_calls == 0


def test_restricted_payroll_plan_is_denied_when_semantic_capability_is_omitted(
    db_session,
):
    model = FakeModel(
        [
            SemanticRequest(
                goal="workers earning more than 1000",
                required_capabilities=["workforce"],
                entities=["employee"],
            ),
            AnalysisPlan(
                goal="workers earning more than 1000",
                queries=[
                    {
                        "purpose": "workers above salary threshold",
                        "query": ConceptualQuery(
                            entities=["payroll"],
                            select=[QuerySelect(field="payroll.net_amount")],
                            filters=[
                                QueryFilter(
                                    field="payroll.net_amount", operator="gt", value=1000
                                )
                            ],
                        ),
                    }
                ],
            ),
        ]
    )
    interaction = _interaction(question="Que trabajadores ganan más de 1000?")
    db_session.add(interaction)
    db_session.commit()
    gateway = FakeGateway()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=gateway,
        model=model,
        security=SecurityContext(scopes=["hr:read"]),
    ).run(interaction)

    assert result.status == "pending_human_review"
    assert result.error_type == "AUTHORIZATION_ERROR"
    assert result.error_detail == "payroll access requires the hr:payroll scope"
    assert result.human_review_id is not None
    assert result.human_review.reason == "payroll access requires the hr:payroll scope"
    assert gateway.validation_calls == 0
    assert gateway.execution_calls == 0


def test_human_review_approval_reruns_payroll_with_scoped_authorization(db_session):
    semantic = SemanticRequest(
        goal="payroll explanation", required_capabilities=["payroll"], entities=["payroll"]
    )
    plan = AnalysisPlan(
        goal="payroll explanation",
        queries=[
            {
                "purpose": "payroll totals",
                "query": ConceptualQuery(
                    entities=["payroll"], select=[QuerySelect(field="payroll.net_amount")]
                ),
            }
        ],
    )
    initial_interaction = _interaction()
    db_session.add(initial_interaction)
    db_session.commit()
    gateway = FakeGateway()

    answer = StructuredAnswer(answer="Approved payroll analysis.")
    workflow = AnalysisWorkflow(
        session=db_session,
        gateway=gateway,
        model=FakeModel([semantic, plan, semantic.model_copy(deep=True), plan.model_copy(deep=True), answer]),
        security=SecurityContext(scopes=["hr:read"]),
    )
    pending = workflow.run(initial_interaction)
    assert pending.status == "pending_human_review"
    assert pending.error_type == "AUTHORIZATION_ERROR"
    assert pending.human_review_id is not None
    assert gateway.execution_calls == 0

    record_human_review_decision(
        db_session,
        pending.human_review_id,
        decision="approve",
        reviewed_by="reviewer@example.test",
        comments="Authorize payroll read for this analysis.",
    )
    db_session.commit()

    resumed = workflow.resume(pending, force=True)

    assert resumed.request_id == pending.request_id
    assert resumed.status == "completed"
    assert resumed.human_review_status == "approve"
    assert resumed.error_type is None
    assert resumed.error_detail is None
    assert resumed.response["answer"].startswith("Approved payroll analysis.")
    assert gateway.validation_calls > 0
    assert gateway.execution_calls > 0
    assert "hr:payroll" in resumed.evaluation_trace["authorization_resume"][0]["scope_added"]


def test_workflow_denies_payroll_without_scope_when_human_review_is_disabled(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="payroll explanation",
                required_capabilities=["payroll"],
                entities=["payroll"],
            )
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(scopes=["hr:read"]),
        read_analysis_human_review_enabled=False,
    ).run(interaction)

    assert result.status == "insufficient_data"
    assert result.error_type == "AUTHORIZATION_ERROR"
    assert result.error_detail == "payroll access requires the hr:payroll scope"
    assert "permisos adicionales" in result.response["answer"]
    assert "workflow stopped" not in result.response["answer"]


def test_payroll_read_authorization_can_be_disabled_for_trusted_demo(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="payroll totals", required_capabilities=["payroll"], entities=["payroll"]
            ),
            _plan(),
            StructuredAnswer(answer="Payroll totals available."),
        ]
    )
    interaction = _interaction(question="What are the payroll totals?")
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(scopes=["hr:read"]),
        payroll_read_authorization_enabled=False,
    ).run(interaction)

    assert result.evaluation_trace["authorization"] == {
        "required": True,
        "enforcement_enabled": False,
        "granted": True,
        "decision": "allowed_by_configuration",
        "scope_present": False,
    }


def test_payroll_read_authorization_helper_requires_scope_when_enabled():
    from peopleops_api.analysis_workflow import payroll_read_allowed

    assert not payroll_read_allowed(SecurityContext(scopes=["hr:read"]), True)
    assert payroll_read_allowed(SecurityContext(scopes=["hr:read", "hr:payroll"]), True)
    assert payroll_read_allowed(SecurityContext(scopes=["hr:read"]), False)


def test_restricted_read_only_analysis_reviews_when_enabled(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="restricted analysis",
                required_capabilities=["workforce"],
                entities=["employee"],
                sensitivity="restricted",
            ),
            _plan(),
            StructuredAnswer(answer="The matching employee is E001."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(),
        read_analysis_human_review_enabled=True,
    ).run(interaction)

    assert result.status == "pending_human_review"
    assert result.evaluation_trace["human_review_decision"] == {
        "semantic_sensitivity": "restricted",
        "semantic_requires_human_review": False,
        "operation_type": "read_only_structured_analysis",
        "enforcement_enabled": True,
        "evidence_available": True,
        "review_required": True,
        "reason": "semantic_review_required",
    }


def test_approved_human_review_can_resume_after_prior_resume_failure(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="restricted analysis",
                required_capabilities=["workforce"],
                entities=["employee"],
                sensitivity="restricted",
            ),
            _plan(),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()

    workflow = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(),
        read_analysis_human_review_enabled=True,
    )
    paused = workflow.run(interaction)
    assert paused.status == "pending_human_review"
    assert paused.human_review_id is not None

    record_human_review_decision(
        db_session,
        paused.human_review_id,
        decision="approve",
        reviewed_by="reviewer@example.test",
        comments=None,
    )
    paused.status = "insufficient_data"
    paused.current_stage = "finalize_response"
    paused.error_type = "HUMAN_REVIEW_ERROR"
    paused.error_detail = "analysis resume failed"
    db_session.commit()

    resumed = workflow.resume(paused, force=True)

    assert resumed.status == "completed"
    assert resumed.response is not None
    assert "aprobó continuar" in resumed.response["answer"]
    assert resumed.response["facts"]
    assert resumed.human_review_status == "approve"
    assert resumed.error_type is None
    assert resumed.error_detail is None


def test_restricted_read_only_analysis_skips_review_when_disabled(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="restricted analysis",
                required_capabilities=["workforce"],
                entities=["employee"],
                sensitivity="restricted",
            ),
            _plan(),
            StructuredAnswer(answer="The matching employee is E001."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(),
        read_analysis_human_review_enabled=False,
    ).run(interaction)

    assert result.status == "completed"
    assert result.human_review_id is None
    assert result.evaluation_trace["human_review_decision"]["review_required"] is False
    assert result.evaluation_trace["human_review_decision"]["reason"] == (
        "read_only_review_disabled_by_configuration"
    )


def test_restricted_analysis_without_evidence_never_routes_to_review(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="restricted analysis",
                required_capabilities=["workforce"],
                entities=["employee"],
                sensitivity="restricted",
            ),
            _plan(),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(invalid_first=True),
        model=model,
        security=SecurityContext(),
        max_replans=0,
        read_analysis_human_review_enabled=True,
    ).run(interaction)

    assert result.status == "insufficient_data"
    assert result.human_review_id is None
    assert result.evaluation_trace["human_review_decision"]["evidence_available"] is False
    assert result.evaluation_trace["human_review_decision"]["reason"] == ("no_reviewable_evidence")


def test_invalid_query_is_replanned_once_and_does_not_loop(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            _plan(),
            StructuredAnswer(answer="The matching employee is E001."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    gateway = FakeGateway(invalid_first=True)
    result = AnalysisWorkflow(
        session=db_session, gateway=gateway, model=model, security=SecurityContext()
    ).run(interaction)

    assert result.status == "completed"
    assert gateway.validation_calls == 2
    assert gateway.execution_calls == 1


def test_empty_structured_result_is_insufficient_data(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            StructuredAnswer(answer="No employees matched the requested criteria."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(empty=True), model=model, security=SecurityContext()
    ).run(interaction)
    assert result.status == "completed"
    assert "No employees matched" in result.response["answer"]
    assert result.evidence[0]["result_verification"]["status"] == "ZERO_ROWS"


def test_nonempty_result_below_requested_limit_is_completed(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="recent employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            StructuredAnswer(
                answer="Only four employees were found.",
                status="insufficient_data",
            ),
        ]
    )
    interaction = _interaction(question="List the 5 most recent employees.")
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(), model=model, security=SecurityContext()
    ).run(interaction)

    assert result.status == "completed"
    assert result.response["status"] == "completed"
    assert "four employees" in result.response["answer"]


def test_plan_preserves_unknown_fields_for_provider_feedback(db_session):
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="unknown field",
        queries=[
            {
                "purpose": "test provider validation",
                "query": ConceptualQuery(
                    entities=["employee"],
                    select=[QuerySelect(field="employee.not_in_catalog")],
                ),
            }
        ],
    )

    normalized = _complete_plan_relationship_entities(plan, build_catalog())

    assert normalized.queries[0].query.select[0].field == "employee.not_in_catalog"


def test_relationship_completion_removes_unreferenced_sensitive_entities():
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="employees by department",
        queries=[
            {
                "purpose": "minimal workforce query",
                "query": ConceptualQuery(
                    entities=["employee", "department", "payroll"],
                    select=[QuerySelect(field="employee.employee_code")],
                    dimensions=["department.name"],
                    relationships=["employee_department", "payroll_employee"],
                ),
            }
        ],
    )

    query = _complete_plan_relationship_entities(plan, build_catalog()).queries[0].query

    assert set(query.entities) == {"employee", "department"}
    assert query.relationships == ["employee_department"]


def test_relationship_completion_keeps_minimal_multi_hop_path():
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="payroll periods by employee",
        queries=[
            {
                "purpose": "multi-hop query",
                "query": ConceptualQuery(
                    entities=["employee", "payroll_period"],
                    select=[
                        QuerySelect(field="employee.employee_code"),
                        QuerySelect(field="payroll_period.code"),
                    ],
                    metrics=[QueryMetric(field="payroll.net_amount", function="sum")],
                ),
            }
        ],
    )

    query = _complete_plan_relationship_entities(plan, build_catalog()).queries[0].query

    assert {"employee", "payroll", "payroll_period"}.issubset(query.entities)
    assert set(query.relationships) == {"payroll_employee", "payroll_period"}


def test_filter_literals_are_not_conceptual_references():
    from reference_mcp_server.discovery import build_catalog

    valid = ConceptualQuery(
        entities=["employee"],
        select=[QuerySelect(field="employee.employee_code")],
        filters=[QueryFilter(field="employee.status", operator="eq", value="active")],
    )
    invalid = valid.model_copy(
        update={
            "filters": [
                QueryFilter(field="employee.status", operator="eq", value="employee.active")
            ]
        }
    )

    assert _catalog_conceptual_validation_errors(valid, build_catalog()) == []
    assert any(
        "INVALID_FILTER" in error
        for error in _catalog_conceptual_validation_errors(invalid, build_catalog())
    )


def test_relationship_completion_uses_grouped_where_references():
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="filtered related records",
        queries=[
            {
                "purpose": "filtered related records",
                "query": ConceptualQuery(
                    entities=["employee"],
                    select=[QuerySelect(field="employee.employee_code")],
                    filters=[QueryFilter(field="employee.status", operator="eq", value="active")],
                    where=QueryFilterGroup(
                        operator="and",
                        conditions=[
                            QueryFilter(
                                field="department.name",
                                operator="eq",
                                value="Operations",
                            )
                        ],
                    ),
                ),
            }
        ],
    )

    query = _complete_plan_relationship_entities(plan, build_catalog()).queries[0].query

    assert query.entities == ["employee", "department"]
    assert query.relationships == ["employee_department"]
    assert _catalog_conceptual_validation_errors(query, build_catalog()) == []


def test_projection_aliases_are_unique_across_select_and_metrics():
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="alias collision",
        queries=[
            {
                "purpose": "alias collision",
                "query": ConceptualQuery(
                    entities=["employee"],
                    select=[
                        QuerySelect(field="employee.department_id", alias="department_id"),
                        QuerySelect(field="employee.status", alias="department_id"),
                    ],
                    metrics=[
                        QueryMetric(field="employee.id", function="count", alias="department_id")
                    ],
                ),
            }
        ],
    )

    query = _complete_plan_relationship_entities(plan, build_catalog()).queries[0].query

    labels = [item.alias for item in query.select] + [item.alias for item in query.metrics]
    assert len(labels) == len(set(labels))
    assert _catalog_conceptual_validation_errors(query, build_catalog()) == []
    assert [item.field for item in query.select] == [
        "employee.department_id",
        "employee.status",
    ]
    assert query.metrics[0].field == "employee.id"


def test_generated_metric_alias_is_disambiguated_from_explicit_select_alias():
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="generated alias collision",
        queries=[
            {
                "purpose": "generated alias collision",
                "query": ConceptualQuery(
                    entities=["employee"],
                    select=[
                        QuerySelect(field="employee.id", alias="count_id"),
                        QuerySelect(field="count(employee.id)"),
                    ],
                ),
            }
        ],
    )

    query = _complete_plan_relationship_entities(plan, build_catalog()).queries[0].query

    assert (
        len({item.alias for item in query.select} | {metric.alias for metric in query.metrics}) == 2
    )
    assert _catalog_conceptual_validation_errors(query, build_catalog()) == []


def test_catalog_repair_uses_only_unique_field_identifier():
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="worked minutes",
        queries=[
            {
                "purpose": "unique catalog repair",
                "query": ConceptualQuery(
                    entities=["attendance_incident"],
                    select=[QuerySelect(field="attendance_incident.worked_minutes")],
                ),
            }
        ],
    )

    query = _complete_plan_relationship_entities(plan, build_catalog()).queries[0].query

    assert query.select[0].field == "attendance.worked_minutes"
    assert query.entities == ["attendance"]


def test_catalog_repair_does_not_guess_ambiguous_field_identifier():
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="status",
        queries=[
            {
                "purpose": "ambiguous catalog reference",
                "query": ConceptualQuery(
                    entities=["employee"],
                    select=[QuerySelect(field="employee.status")],
                    dimensions=["status"],
                ),
            }
        ],
    )

    query = _complete_plan_relationship_entities(plan, build_catalog()).queries[0].query

    assert query.dimensions == ["status"]
    assert any(
        "UNQUALIFIED_FIELD" in error
        for error in _catalog_conceptual_validation_errors(query, build_catalog())
    )


def test_period_comparison_expansion_preserves_complete_independent_scopes():
    from peopleops_api.analysis_workflow import _expand_period_comparison_plan
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="compare payroll periods",
        queries=[
            {
                "purpose": "period comparison",
                "query": ConceptualQuery(
                    entities=["payroll"],
                    metrics=[QueryMetric(field="payroll.net_amount", function="sum")],
                    time_scope=QueryPeriod(
                        type="period_comparison",
                        current=QueryPeriod(type="payroll_period", value="2025-02"),
                        previous=QueryPeriod(type="payroll_period", value="2025-01"),
                    ),
                ),
            }
        ],
    )

    expanded = _complete_plan_relationship_entities(
        _expand_period_comparison_plan(plan), build_catalog()
    )

    assert [item.logical_role for item in expanded.queries] == ["current", "previous"]
    assert [item.query.time_scope.value for item in expanded.queries] == ["2025-02", "2025-01"]
    assert all(item.query.time_scope.type == "payroll_period" for item in expanded.queries)


def test_payroll_period_scope_adds_required_conceptual_entity():
    from peopleops_api.analysis_workflow import _complete_plan_relationship_entities
    from reference_mcp_server.discovery import build_catalog

    plan = AnalysisPlan(
        goal="payroll period",
        queries=[
            {
                "purpose": "period scoped query",
                "query": ConceptualQuery(
                    entities=["payroll"],
                    metrics=[QueryMetric(field="payroll.net_amount", function="sum")],
                    time_scope=QueryPeriod(type="payroll_period", value="2025-02"),
                ),
            }
        ],
    )

    query = _complete_plan_relationship_entities(plan, build_catalog()).queries[0].query

    assert "payroll_period" in query.entities
    assert "payroll_period" in query.relationships


def test_catalog_preflight_accepts_only_discovered_qualified_fields():
    from reference_mcp_server.discovery import build_catalog

    catalog = build_catalog()
    valid = ConceptualQuery(
        entities=["employee"],
        select=[QuerySelect(field="employee.employee_code")],
    )
    invalid = ConceptualQuery(
        entities=["employee"],
        select=[QuerySelect(field="employee.not_in_catalog")],
    )
    unqualified = ConceptualQuery(
        entities=["employee"],
        select=[QuerySelect(field="employee_code")],
    )

    assert _catalog_conceptual_validation_errors(valid, catalog) == []
    assert any(
        "UNKNOWN_FIELD" in error
        for error in _catalog_conceptual_validation_errors(invalid, catalog)
    )
    assert any(
        "UNQUALIFIED_FIELD" in error
        for error in _catalog_conceptual_validation_errors(unqualified, catalog)
    )


def test_catalog_preflight_checks_grouped_where_fields_and_literal_values():
    from reference_mcp_server.discovery import build_catalog

    catalog = build_catalog()
    valid = ConceptualQuery(
        entities=["contract"],
        select=[QuerySelect(field="contract.id")],
        where=QueryFilterGroup(
            operator="or",
            conditions=[
                QueryFilter(field="contract.end_date", operator="is_null"),
                QueryFilter(field="contract.end_date", operator="gte", value=date(2026, 9, 11)),
            ],
        ),
    )
    invalid_field = valid.model_copy(
        update={
            "where": QueryFilterGroup(
                operator="or",
                conditions=[
                    QueryFilter(field="contract.end_date", operator="is_null"),
                    QueryFilter(
                        field="contract.not_in_catalog",
                        operator="gte",
                        value=date(2026, 9, 11),
                    ),
                ],
            )
        }
    )
    invalid_value = valid.model_copy(
        update={
            "where": QueryFilter(
                field="contract.status",
                operator="eq",
                value="employee.status",
            )
        }
    )

    assert _catalog_conceptual_validation_errors(valid, catalog) == []
    assert any(
        "UNKNOWN_FIELD: where:contract.not_in_catalog" in error
        for error in _catalog_conceptual_validation_errors(invalid_field, catalog)
    )
    assert any(
        "INVALID_FILTER: contract.status value must be a literal" in error
        for error in _catalog_conceptual_validation_errors(invalid_value, catalog)
    )


def test_temporal_non_policy_request_routes_to_structured_workflow():
    semantic = SemanticRequest(
        goal="Retrieve overtime for the requested period",
        temporal_intent={"kind": "explicit_month_year", "month": 1, "year": 2026},
        required_capabilities=[],
        entities=[],
        requires_structured_data=False,
        requires_policy=False,
    )

    assert AnalysisWorkflow._after_understanding({"semantic_request": semantic}) == "discover"


def test_catalog_grounding_rejects_noncanonical_semantic_identifiers():
    from reference_mcp_server.discovery import build_catalog

    semantic = SemanticRequest(
        goal="payroll",
        required_capabilities=["payroll data access"],
        entities=["salary_history"],
        requires_structured_data=True,
    )
    errors = _semantic_catalog_errors(semantic, build_catalog())

    assert "UNKNOWN_CAPABILITY: payroll data access" in errors
    assert "UNKNOWN_ENTITY: salary_history" in errors


def test_catalog_preflight_rejects_malformed_period_comparison_shape():
    from reference_mcp_server.discovery import build_catalog

    query = ConceptualQuery.model_validate(
        {
            "entities": ["payroll_period"],
            "metrics": [{"function": "count"}],
            "time_scope": {
                "type": "date_range",
                "field": "payroll_period.start_date",
                "start": "2025-01-01",
                "end": "2025-01-31",
                "current": {"type": "payroll_period", "value": "2025-01"},
            },
        }
    )

    assert any(
        "INVALID_TIME_SCOPE" in error
        for error in _catalog_conceptual_validation_errors(query, build_catalog())
    )


def test_invalid_catalog_plan_is_replanned_before_provider_call(db_session):
    invalid_plan = AnalysisPlan(
        goal="active employees",
        queries=[
            {
                "purpose": "invalid field",
                "query": ConceptualQuery(
                    entities=["employee"],
                    select=[QuerySelect(field="employee.not_in_catalog")],
                ),
            }
        ],
    )
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            invalid_plan,
            _plan(),
            StructuredAnswer(answer="The matching employee is E001."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    gateway = FakeGateway()
    result = AnalysisWorkflow(
        session=db_session, gateway=gateway, model=model, security=SecurityContext()
    ).run(interaction)

    assert result.status == "completed"
    assert gateway.validation_calls == 1
    assert gateway.execution_calls == 1
    assert result.evaluation_trace["catalog_preflight"][0]["accepted"] is False
    assert result.evaluation_trace["planning_attempts"][1]["provider_feedback"]


def test_noncanonical_semantic_identifiers_are_refined_from_safe_catalog(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="active people",
                required_capabilities=["people analytics"],
                entities=["people"],
            ),
            SemanticRequest(
                goal="active people", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            StructuredAnswer(answer="The matching employee is E001."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(), model=model, security=SecurityContext()
    ).run(interaction)

    assert result.status == "completed"
    assert result.semantic_request["required_capabilities"] == ["workforce"]
    assert result.semantic_request["entities"] == ["employee"]


def test_valid_zero_rows_are_not_classified_as_missing_evidence(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="active employees", required_capabilities=["workforce"], entities=["employee"]
            ),
            _plan(),
            StructuredAnswer(answer="No records matched the requested criteria."),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()

    result = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(empty=True), model=model, security=SecurityContext()
    ).run(interaction)

    assert result.status == "completed"
    assert result.response["status"] == "completed"
    assert result.evidence[0]["result_verification"] == {"status": "ZERO_ROWS", "row_count": 0}


def test_combined_workflow_preserves_fact_policy_and_inference_provenance(db_session):
    from peopleops_api.policy_retrieval import PolicyEvidence

    policy = PolicyEvidence(
        document_id=uuid4(),
        document_key="vacation-policy",
        title="Vacation Policy",
        policy_version_id=uuid4(),
        version="2026.1",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        page=3,
        section="Requests",
        chunk_id=uuid4(),
        chunk_index=0,
        fragment="Vacation requests require manager approval.",
        score=0.94,
    )
    model = FakeModel(
        [
            _policy_semantic(structured=True),
            _policy_plan(),
            StructuredAnswer(
                answer="The request is supported by the available facts and policy.",
                inference=["Manager approval is required."],
            ),
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(),
        policy_provider=FakePolicyProvider(
            PolicyRetrievalResult(status=PolicyRetrievalStatus.COMPLETED, evidence=[policy])
        ),
    ).run(interaction)

    assert result.status == "completed"
    assert result.response["facts"][0]["type"] == "structured_data"
    assert result.response["policies"][0]["document_key"] == "vacation-policy"
    assert result.policy_sources[0]["document_key"] == "vacation-policy"
    assert result.policy_versions[0]["version"] == "2026.1"
    assert {item["type"] for item in result.evidence} == {"structured_data", "policy"}
    assert "policy_retrieval" in {event["stage"] for event in result.stage_history}


def test_policy_only_workflow_does_not_call_structured_provider(db_session):
    provider = FakePolicyProvider(
        PolicyRetrievalResult(status=PolicyRetrievalStatus.POLICY_NOT_FOUND, reason="policy absent")
    )
    model = FakeModel([_policy_semantic(structured=False), AnalysisPlan(goal="policy only")])
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    gateway = FakeGateway()
    result = AnalysisWorkflow(
        session=db_session,
        gateway=gateway,
        model=model,
        security=SecurityContext(),
        policy_provider=provider,
    ).run(interaction)

    assert result.status == "policy_not_found"
    assert gateway.catalog_calls == 0
    assert gateway.execution_calls == 0
    assert result.policy_sources == []
    assert result.response["warnings"]


def test_policy_conflict_is_not_resolved_by_the_workflow(db_session):
    provider = FakePolicyProvider(
        PolicyRetrievalResult(
            status=PolicyRetrievalStatus.POLICY_CONFLICT,
            reason="two active versions apply",
        )
    )
    model = FakeModel([_policy_semantic(structured=False), AnalysisPlan(goal="policy conflict")])
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session,
        gateway=FakeGateway(),
        model=model,
        security=SecurityContext(),
        policy_provider=provider,
    ).run(interaction)

    assert result.status == "policy_conflict"
    assert result.response["policies"] == []
    assert "two active versions apply" in result.response["warnings"]
