from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from peopleops_api.analysis_contracts import AnalysisPlan, SemanticRequest, StructuredAnswer
from peopleops_api.analysis_workflow import AnalysisWorkflow, _complete_plan_relationship_entities
from peopleops_api.mcp_contracts import SecurityContext
from peopleops_api.models import AnalysisInteraction
from peopleops_api.query_contracts import ConceptualQuery, QueryResult, QuerySelect, QueryValidation
from peopleops_api.policy_retrieval import PolicyRetrievalResult, PolicyRetrievalStatus


@dataclass
class FakeModel:
    outputs: list[object]
    model_name: str = "fake-structured-model"

    def parse(self, *, purpose, instructions, output_model):
        output = self.outputs.pop(0)
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


def _interaction():
    return AnalysisInteraction(
        request_id=uuid4(), question="Which employees are active?", stage_history=[]
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
