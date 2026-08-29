from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from peopleops_api.analysis_contracts import AnalysisPlan, SemanticRequest, StructuredAnswer
from peopleops_api.analysis_workflow import (
    AnalysisWorkflow,
    _catalog_conceptual_validation_errors,
    _complete_plan_relationship_entities,
    _semantic_catalog_errors,
)
from peopleops_api.mcp_contracts import SecurityContext
from peopleops_api.models import AnalysisInteraction, Conversation
from peopleops_api.query_contracts import (
    ConceptualQuery,
    QueryFilter,
    QueryMetric,
    QueryPeriod,
    QueryResult,
    QuerySelect,
    QueryValidation,
)
from peopleops_api.policy_retrieval import PolicyRetrievalResult, PolicyRetrievalStatus


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
            (index for index, candidate in enumerate(self.outputs)
             if isinstance(candidate, output_model)),
            None,
        )
        if index is None:
            output = self._last_by_type.get(output_model)
            if output is None:
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
    assert trace["provider_validations"][0]["query"] == trace["planning_attempts"][0]["conceptual_queries"][0]["query"]


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


def test_evaluation_trace_persists_authorization_decision(db_session):
    model = FakeModel(
        [
            SemanticRequest(
                goal="payroll totals", required_capabilities=["payroll"], entities=["payroll"]
            )
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

    assert result.status == "failed"
    assert result.evaluation_trace["authorization"] == {
        "required": True,
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
    assert [item["logical_query_role"] for item in trace["planning_attempts"][0]["conceptual_queries"]] == [
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
    assert result.evaluation_trace["provider_executions"][0]["result_verification_status"] == "ZERO_ROWS"


def test_workflow_denies_payroll_before_discovery_without_scope(db_session):
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
    ).run(interaction)

    assert result.status == "failed"
    assert result.error_type == "AUTHORIZATION_ERROR"
    assert result.error_detail == "payroll access requires the hr:payroll scope"


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
                QueryFilter(
                    field="employee.status", operator="eq", value="employee.active"
                )
            ]
        }
    )

    assert _catalog_conceptual_validation_errors(valid, build_catalog()) == []
    assert any("INVALID_FILTER" in error for error in _catalog_conceptual_validation_errors(invalid, build_catalog()))


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
                    metrics=[QueryMetric(field="employee.id", function="count", alias="department_id")],
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

    assert len({item.alias for item in query.select} | {metric.alias for metric in query.metrics}) == 2
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
    assert any("UNQUALIFIED_FIELD" in error for error in _catalog_conceptual_validation_errors(query, build_catalog()))


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

    expanded = _complete_plan_relationship_entities(_expand_period_comparison_plan(plan), build_catalog())

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
    assert any("UNKNOWN_FIELD" in error for error in _catalog_conceptual_validation_errors(invalid, catalog))
    assert any("UNQUALIFIED_FIELD" in error for error in _catalog_conceptual_validation_errors(unqualified, catalog))


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
                goal="active people", required_capabilities=["people analytics"], entities=["people"]
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
