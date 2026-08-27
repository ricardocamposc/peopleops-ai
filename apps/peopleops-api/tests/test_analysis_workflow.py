from dataclasses import dataclass
from uuid import uuid4

from peopleops_api.analysis_contracts import AnalysisPlan, SemanticRequest, StructuredAnswer
from peopleops_api.analysis_workflow import AnalysisWorkflow
from peopleops_api.mcp_contracts import SecurityContext
from peopleops_api.models import AnalysisInteraction
from peopleops_api.query_contracts import ConceptualQuery, QueryResult, QuerySelect, QueryValidation


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
        ]
    )
    interaction = _interaction()
    db_session.add(interaction)
    db_session.commit()
    result = AnalysisWorkflow(
        session=db_session, gateway=FakeGateway(empty=True), model=model, security=SecurityContext()
    ).run(interaction)
    assert result.status == "insufficient_data"
    assert result.response["warnings"]
