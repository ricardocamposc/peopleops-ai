from peopleops_api.analysis_contracts import AnalysisPlan, StructuredAnswer
from peopleops_api.mcp_contracts import (
    DiscoveryCatalog,
    DiscoveryEntity,
    DiscoveryRelationship,
)
from peopleops_api.analysis_workflow import (
    _decode_structured_json,
    _normalize_analysis_plan_payload,
    _openai_strict_schema,
)


def test_openai_schema_closes_nested_objects_and_dynamic_items():
    schema = _openai_strict_schema(StructuredAnswer.model_json_schema())

    def assert_strict(value):
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
                assert value["required"] == list(value.get("properties", {}))
            for child in value.values():
                assert_strict(child)
        elif isinstance(value, list):
            for child in value:
                assert_strict(child)

    assert_strict(schema)


def test_openai_schema_supports_nested_analysis_contracts():
    schema = _openai_strict_schema(AnalysisPlan.model_json_schema())
    assert schema["additionalProperties"] is False
    assert "policy" in schema["required"]


def test_structured_decoder_accepts_json_markdown_fence():
    assert _decode_structured_json('```json\n{"status": "ok"}\n```') == {"status": "ok"}


def test_structured_decoder_accepts_trailing_provider_content():
    assert _decode_structured_json('{"status": "ok"}\n{"ignored": true}') == {
        "status": "ok"
    }


def test_analysis_plan_removes_incomplete_optional_time_scope():
    payload = {
        "goal": "overtime",
        "queries": [
            {
                "purpose": "aggregate",
                "query": {
                    "entities": ["overtime"],
                    "metrics": [{"function": "count"}],
                    "time_scope": {"type": "date_range", "start": None, "end": None},
                },
            }
        ],
    }
    normalized = _normalize_analysis_plan_payload(payload)
    assert "time_scope" not in normalized["queries"][0]["query"]


def test_analysis_plan_normalizes_group_by_to_canonical_dimensions():
    payload = {
        "goal": "overtime",
        "queries": [
            {
                "purpose": "aggregate",
                "query": {"entities": ["overtime"], "group_by": ["department"]},
            }
        ],
    }
    normalized = _normalize_analysis_plan_payload(payload)
    assert normalized["queries"][0]["query"]["dimensions"] == ["department"]
    assert "group_by" not in normalized["queries"][0]["query"]


def test_analysis_plan_adds_intermediate_relationship_entities():
    from peopleops_api.analysis_workflow import _complete_plan_relationship_entities

    plan = AnalysisPlan.model_validate(
        {
            "goal": "overtime",
            "queries": [
                {
                    "purpose": "aggregate",
                    "query": {
                        "entities": ["overtime", "department"],
                        "metrics": [{"field": "overtime.approved_minutes", "function": "sum"}],
                        "relationships": ["overtime_employee", "employee_department"],
                        "dimensions": ["department.name"],
                    },
                }
            ],
        }
    )
    catalog = DiscoveryCatalog(
        provider_type="test",
        catalog_version="1",
        fingerprint="test",
        capabilities=[],
        entities=[],
        relationships=[
            DiscoveryRelationship(
                relationship_id="overtime_employee",
                from_entity="overtime",
                to_entity="employee",
                relationship_type="many_to_one",
                join_semantics="overtime.employee_id = employee.id",
            ),
            DiscoveryRelationship(
                relationship_id="employee_department",
                from_entity="employee",
                to_entity="department",
                relationship_type="many_to_one",
                join_semantics="employee.department_id = department.id",
            ),
        ],
    )
    completed = _complete_plan_relationship_entities(plan, catalog)
    assert completed.queries[0].query.entities == ["overtime", "department", "employee"]


def test_analysis_plan_normalizes_metric_expression_in_ordering():
    from peopleops_api.analysis_workflow import _complete_plan_relationship_entities

    plan = AnalysisPlan.model_validate(
        {
            "goal": "overtime",
            "queries": [
                {
                    "purpose": "aggregate",
                    "query": {
                        "entities": ["overtime"],
                        "metrics": [
                            {
                                "field": "overtime.approved_minutes",
                                "function": "sum",
                                "alias": "total_overtime",
                            }
                        ],
                        "order_by": [
                            {"reference": "SUM(overtime.approved_minutes)", "direction": "desc"}
                        ],
                    },
                }
            ],
        }
    )
    catalog = DiscoveryCatalog(
        provider_type="test",
        catalog_version="1",
        fingerprint="test",
        capabilities=[],
        entities=[],
        relationships=[],
    )
    completed = _complete_plan_relationship_entities(plan, catalog)
    assert completed.queries[0].query.order_by[0].reference == "total_overtime"


def test_analysis_plan_resolves_entity_aliases_from_catalog():
    from peopleops_api.analysis_workflow import _complete_plan_relationship_entities

    plan = AnalysisPlan.model_validate(
        {
            "goal": "overtime",
            "queries": [
                {
                    "purpose": "aggregate",
                    "query": {
                        "entities": ["overtime"],
                        "metrics": [{"field": "overtime.approved_minutes", "function": "sum"}],
                        "filters": [{"field": "overtime.status", "operator": "eq", "value": "approved"}],
                    },
                }
            ],
        }
    )
    catalog = DiscoveryCatalog(
        provider_type="test",
        catalog_version="1",
        fingerprint="test",
        capabilities=[],
        entities=[
            DiscoveryEntity(
                entity_id="overtime_record",
                business_name="Overtime record",
                description="Overtime",
                fields=[],
                sensitivity="internal",
                supported_operations=["read"],
            )
        ],
        relationships=[],
    )
    completed = _complete_plan_relationship_entities(plan, catalog)
    query = completed.queries[0].query
    assert query.entities == ["overtime_record"]
    assert query.metrics[0].field == "overtime_record.approved_minutes"
    assert query.filters[0].field == "overtime_record.status"
