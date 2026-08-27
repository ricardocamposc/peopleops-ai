"""Schema-B source adapter used by the Slice 13 contract harness.

The semantic entity and field IDs intentionally match the reference catalog.
Only this MCP-side adapter knows that Schema B stores the data in a smaller,
structurally different set of source tables.
"""

from __future__ import annotations

from reference_mcp_server.discovery import CatalogMetadata, build_catalog

_TABLES = {
    "employee": "hr_person",
    "contract": "hr_contract",
    "overtime": "time_event",
    "payroll_period": "pay_run",
    "payroll": "pay_movement",
}

_COLUMNS = {
    "employee": {
        "id": "person_id",
        "employee_code": "person_no",
        "first_name": "given_name",
        "last_name": "family_name",
        "status": "employment_state",
        "hire_date": "joined_on",
    },
    "contract": {
        "id": "contract_id",
        "employee_id": "person_ref",
        "contract_type": "kind",
        "start_date": "valid_from",
        "end_date": "valid_to",
        "status": "contract_state",
    },
    "overtime": {
        "id": "event_id",
        "employee_id": "person_ref",
        "work_date": "event_day",
        "approved_minutes": "overtime_minutes",
        "status": "event_status",
    },
    "payroll_period": {
        "id": "run_id",
        "code": "period_code",
        "start_date": "period_start",
        "end_date": "period_end",
        "payment_date": "paid_on",
        "status": "run_status",
    },
    "payroll": {
        "id": "movement_id",
        "employee_id": "person_ref",
        "payroll_period_id": "run_id",
        "gross_amount": "gross_pay",
        "deduction_amount": "withheld_pay",
        "net_amount": "net_pay",
        "employer_cost": "employer_total",
        "cost_center": "cost_unit",
    },
}


def build_alternate_catalog(catalog_version: str = "2026.08-schema-b") -> CatalogMetadata:
    """Return a compatible semantic catalog backed by Schema B."""

    source = build_catalog()
    supported = set(_TABLES)
    entities = []
    for entity in source.entities:
        if entity.entity_id not in supported:
            continue
        columns = _COLUMNS[entity.entity_id]
        fields = [
            field.model_copy(
                update={
                    "physical_source": f"{_TABLES[entity.entity_id]}.{columns.get(field.field_id, field.field_id)}"
                }
            )
            for field in entity.fields
            if field.field_id in columns
        ]
        entities.append(
            entity.model_copy(
                update={"physical_source": _TABLES[entity.entity_id], "fields": fields}
            )
        )

    relation_specs = {
        "contract_employee": "hr_contract.person_ref = hr_person.person_id",
        "overtime_employee": "time_event.person_ref = hr_person.person_id",
        "payroll_employee": "pay_movement.person_ref = hr_person.person_id",
        "payroll_period": "pay_movement.run_id = pay_run.run_id",
    }
    relationships = [
        relationship.model_copy(
            update={"physical_mapping": relation_specs[relationship.relationship_id]}
        )
        for relationship in source.relationships
        if relationship.relationship_id in relation_specs
    ]
    capabilities = [
        capability.model_copy(
            update={"entities": [entity for entity in capability.entities if entity in supported]}
        )
        for capability in source.capabilities
    ]
    capabilities = [capability for capability in capabilities if capability.entities]
    provisional = CatalogMetadata(
        provider_type="reference_synthetic_hris_schema_b",
        catalog_version=catalog_version,
        fingerprint="pending",
        capabilities=capabilities,
        entities=entities,
        relationships=relationships,
    )
    import hashlib
    import json

    canonical = provisional.model_dump(mode="json", exclude={"fingerprint"})
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return provisional.model_copy(update={"fingerprint": fingerprint})


def schema_b_physical_sources(catalog: CatalogMetadata) -> set[str]:
    """Expose source names for adapter-level migration tests only."""

    return {entity.physical_source for entity in catalog.entities}
