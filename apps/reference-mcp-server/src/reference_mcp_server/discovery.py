"""Provider-neutral discovery catalog owned by the reference source adapter.

The physical mappings in this module intentionally stay inside the Reference
MCP Server. PeopleOps consumes the semantic identifiers and never imports this
module or the synthetic HRIS schema.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Sensitivity = Literal["public", "internal", "confidential", "restricted"]
SemanticRole = Literal[
    "identifier",
    "dimension",
    "metric",
    "date",
    "status",
    "amount",
    "quantity",
]
Operation = Literal["read", "aggregate"]
RelationshipType = Literal["many_to_one", "one_to_many"]


class DiscoveryError(BaseModel):
    code: Literal["ENTITY_NOT_FOUND", "DISCOVERY_ERROR"]
    message: str
    detail: str | None = None


class FieldMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str
    business_name: str
    description: str
    data_type: str
    unit: str | None = None
    nullable: bool
    physical_source: str
    semantic_role: SemanticRole
    sensitivity: Sensitivity
    is_primary_key: bool = False
    is_foreign_key: bool = False


class RelationshipMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_id: str
    from_entity: str
    to_entity: str
    relationship_type: RelationshipType
    join_semantics: str
    physical_mapping: str


class EntityMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    business_name: str
    description: str
    physical_source: str
    fields: list[FieldMetadata]
    relationships: list[str] = Field(default_factory=list)
    temporal_fields: list[str] = Field(default_factory=list)
    sensitivity: Sensitivity
    supported_operations: list[Operation]


class CapabilityMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    entities: list[str]
    supported_operations: list[Operation]
    sensitivity: Sensitivity


class CatalogMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_type: str
    catalog_version: str
    fingerprint: str
    capabilities: list[CapabilityMetadata]
    entities: list[EntityMetadata]
    relationships: list[RelationshipMetadata]


def _field(
    entity: str,
    field_id: str,
    business_name: str,
    description: str,
    data_type: str,
    role: SemanticRole,
    sensitivity: Sensitivity = "internal",
    *,
    nullable: bool = False,
    unit: str | None = None,
    primary_key: bool = False,
    foreign_key: bool = False,
) -> FieldMetadata:
    return FieldMetadata(
        field_id=field_id,
        business_name=business_name,
        description=description,
        data_type=data_type,
        unit=unit,
        nullable=nullable,
        physical_source=f"{entity}.{field_id}",
        semantic_role=role,
        sensitivity=sensitivity,
        is_primary_key=primary_key,
        is_foreign_key=foreign_key,
    )


def _entity(
    entity_id: str,
    business_name: str,
    description: str,
    physical_source: str,
    fields: list[FieldMetadata],
    sensitivity: Sensitivity = "internal",
    temporal_fields: list[str] | None = None,
    relationships: list[str] | None = None,
    operations: list[Operation] | None = None,
) -> EntityMetadata:
    return EntityMetadata(
        entity_id=entity_id,
        business_name=business_name,
        description=description,
        physical_source=physical_source,
        fields=fields,
        relationships=relationships or [],
        temporal_fields=temporal_fields or [],
        sensitivity=sensitivity,
        supported_operations=operations or ["read", "aggregate"],
    )


def build_catalog(catalog_version: str = "2026.08") -> CatalogMetadata:
    """Build the complete semantic catalog for the seeded reference HRIS."""

    entities = [
        _entity(
            "employee",
            "Employee",
            "Person employed by the organization.",
            "employee",
            [
                _field(
                    "employee",
                    "id",
                    "Employee record identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "employee",
                    "employee_code",
                    "Employee code",
                    "Business identifier used to reference an employee.",
                    "string",
                    "identifier",
                ),
                _field(
                    "employee",
                    "first_name",
                    "First name",
                    "Employee given name.",
                    "string",
                    "dimension",
                    "confidential",
                ),
                _field(
                    "employee",
                    "last_name",
                    "Last name",
                    "Employee family name.",
                    "string",
                    "dimension",
                    "confidential",
                ),
                _field(
                    "employee",
                    "status",
                    "Employment status",
                    "Current employment status.",
                    "string",
                    "status",
                ),
                _field(
                    "employee", "hire_date", "Hire date", "Date employment began.", "date", "date"
                ),
                _field(
                    "employee",
                    "department_id",
                    "Department reference",
                    "Reference to the organizational department.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
                _field(
                    "employee",
                    "position_id",
                    "Position reference",
                    "Reference to the employee position.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
            ],
            temporal_fields=["hire_date"],
            relationships=["employee_department", "employee_position"],
        ),
        _entity(
            "department",
            "Department",
            "Organizational department and cost center.",
            "department",
            [
                _field(
                    "department",
                    "id",
                    "Department identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "department",
                    "code",
                    "Department code",
                    "Business department code.",
                    "string",
                    "identifier",
                ),
                _field(
                    "department",
                    "name",
                    "Department name",
                    "Display name of the department.",
                    "string",
                    "dimension",
                ),
                _field(
                    "department",
                    "cost_center",
                    "Cost center",
                    "Financial cost center assigned to the department.",
                    "string",
                    "dimension",
                    "confidential",
                ),
            ],
        ),
        _entity(
            "position",
            "Position",
            "Organizational position held by an employee.",
            "position",
            [
                _field(
                    "position",
                    "id",
                    "Position identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "position",
                    "code",
                    "Position code",
                    "Business position code.",
                    "string",
                    "identifier",
                ),
                _field(
                    "position",
                    "name",
                    "Position name",
                    "Display name of the position.",
                    "string",
                    "dimension",
                ),
                _field(
                    "position",
                    "department_id",
                    "Department reference",
                    "Owning department reference.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
            ],
            relationships=["position_department"],
        ),
        _entity(
            "contract",
            "Employment contract",
            "Contract terms and end dates for an employee.",
            "contract",
            [
                _field(
                    "contract",
                    "id",
                    "Contract identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "contract",
                    "employee_id",
                    "Employee reference",
                    "Referenced employee.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
                _field(
                    "contract",
                    "contract_type",
                    "Contract type",
                    "Classification of the employment contract.",
                    "string",
                    "dimension",
                ),
                _field(
                    "contract",
                    "start_date",
                    "Start date",
                    "Contract effective start date.",
                    "date",
                    "date",
                ),
                _field(
                    "contract",
                    "end_date",
                    "End date",
                    "Contractual end date, if applicable.",
                    "date",
                    "date",
                    nullable=True,
                ),
                _field(
                    "contract",
                    "status",
                    "Contract status",
                    "Current contract status.",
                    "string",
                    "status",
                ),
            ],
            temporal_fields=["start_date", "end_date"],
            relationships=["contract_employee"],
        ),
        _entity(
            "attendance",
            "Attendance record",
            "Daily scheduled, worked and incident minutes.",
            "attendance_record",
            [
                _field(
                    "attendance_record",
                    "id",
                    "Attendance record identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "attendance_record",
                    "employee_id",
                    "Employee reference",
                    "Referenced employee.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
                _field(
                    "attendance_record",
                    "work_date",
                    "Work date",
                    "Date to which attendance applies.",
                    "date",
                    "date",
                ),
                _field(
                    "attendance_record",
                    "status",
                    "Attendance status",
                    "Daily attendance status.",
                    "string",
                    "status",
                ),
                _field(
                    "attendance_record",
                    "scheduled_minutes",
                    "Scheduled minutes",
                    "Minutes scheduled for the work date.",
                    "integer",
                    "quantity",
                    "internal",
                    unit="minutes",
                ),
                _field(
                    "attendance_record",
                    "worked_minutes",
                    "Worked minutes",
                    "Minutes worked on the work date.",
                    "integer",
                    "quantity",
                    "internal",
                    unit="minutes",
                ),
                _field(
                    "attendance_record",
                    "late_minutes",
                    "Late minutes",
                    "Minutes recorded as late.",
                    "integer",
                    "quantity",
                    "internal",
                    unit="minutes",
                ),
                _field(
                    "attendance_record",
                    "absence_minutes",
                    "Absence minutes",
                    "Minutes recorded as absent.",
                    "integer",
                    "quantity",
                    "internal",
                    unit="minutes",
                ),
            ],
            temporal_fields=["work_date"],
            relationships=["attendance_employee"],
        ),
        _entity(
            "attendance_incident",
            "Attendance incident",
            "Recorded attendance incident for an employee.",
            "attendance_incident",
            [
                _field(
                    "attendance_incident",
                    "id",
                    "Incident identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "attendance_incident",
                    "employee_id",
                    "Employee reference",
                    "Referenced employee.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
                _field(
                    "attendance_incident",
                    "incident_date",
                    "Incident date",
                    "Date of the incident.",
                    "date",
                    "date",
                ),
                _field(
                    "attendance_incident",
                    "incident_type",
                    "Incident type",
                    "Classification of the incident.",
                    "string",
                    "dimension",
                ),
                _field(
                    "attendance_incident",
                    "minutes",
                    "Incident minutes",
                    "Minutes associated with the incident.",
                    "integer",
                    "quantity",
                    "internal",
                    unit="minutes",
                ),
                _field(
                    "attendance_incident",
                    "status",
                    "Incident status",
                    "Current incident status.",
                    "string",
                    "status",
                ),
            ],
            temporal_fields=["incident_date"],
            relationships=["attendance_incident_employee"],
        ),
        _entity(
            "overtime",
            "Overtime record",
            "Approved overtime worked by an employee.",
            "overtime_record",
            [
                _field(
                    "overtime_record",
                    "id",
                    "Overtime record identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "overtime_record",
                    "employee_id",
                    "Employee reference",
                    "Referenced employee.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
                _field(
                    "overtime_record",
                    "work_date",
                    "Overtime date",
                    "Date overtime was worked.",
                    "date",
                    "date",
                ),
                _field(
                    "overtime_record",
                    "approved_minutes",
                    "Approved overtime",
                    "Approved overtime duration.",
                    "integer",
                    "quantity",
                    "internal",
                    unit="minutes",
                ),
                _field(
                    "overtime_record",
                    "status",
                    "Overtime status",
                    "Current approval or processing status.",
                    "string",
                    "status",
                ),
            ],
            temporal_fields=["work_date"],
            relationships=["overtime_employee"],
        ),
        _entity(
            "vacation_balance",
            "Vacation balance",
            "Annual earned, used and available vacation days.",
            "vacation_balance",
            [
                _field(
                    "vacation_balance",
                    "id",
                    "Balance identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "vacation_balance",
                    "employee_id",
                    "Employee reference",
                    "Referenced employee.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
                _field(
                    "vacation_balance",
                    "period_year",
                    "Balance year",
                    "Calendar year of the balance.",
                    "integer",
                    "date",
                ),
                _field(
                    "vacation_balance",
                    "earned_days",
                    "Earned vacation days",
                    "Days earned in the balance period.",
                    "decimal",
                    "quantity",
                    "internal",
                    unit="days",
                ),
                _field(
                    "vacation_balance",
                    "used_days",
                    "Used vacation days",
                    "Days already used.",
                    "decimal",
                    "quantity",
                    "internal",
                    unit="days",
                ),
                _field(
                    "vacation_balance",
                    "scheduled_days",
                    "Scheduled vacation days",
                    "Days reserved by approved or scheduled requests.",
                    "decimal",
                    "quantity",
                    "internal",
                    unit="days",
                ),
                _field(
                    "vacation_balance",
                    "available_days",
                    "Available vacation days",
                    "Days remaining after used and scheduled days.",
                    "decimal",
                    "quantity",
                    "internal",
                    unit="days",
                ),
            ],
            relationships=["vacation_balance_employee"],
        ),
        _entity(
            "vacation_request",
            "Vacation request",
            "Requested vacation period and approval status.",
            "vacation_request",
            [
                _field(
                    "vacation_request",
                    "id",
                    "Vacation request identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "vacation_request",
                    "employee_id",
                    "Employee reference",
                    "Referenced employee.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
                _field(
                    "vacation_request",
                    "start_date",
                    "Vacation start date",
                    "Requested period start.",
                    "date",
                    "date",
                ),
                _field(
                    "vacation_request",
                    "end_date",
                    "Vacation end date",
                    "Requested period end.",
                    "date",
                    "date",
                ),
                _field(
                    "vacation_request",
                    "requested_days",
                    "Requested vacation days",
                    "Number of requested days.",
                    "decimal",
                    "quantity",
                    "internal",
                    unit="days",
                ),
                _field(
                    "vacation_request",
                    "status",
                    "Vacation request status",
                    "Current request status.",
                    "string",
                    "status",
                ),
                _field(
                    "vacation_request",
                    "created_at",
                    "Request creation time",
                    "Time the request was created.",
                    "datetime",
                    "date",
                ),
            ],
            temporal_fields=["start_date", "end_date", "created_at"],
            relationships=["vacation_request_employee"],
        ),
        _entity(
            "leave_request",
            "Leave request",
            "Leave period, type and status for an employee.",
            "leave_request",
            [
                _field(
                    "leave_request",
                    "id",
                    "Leave request identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "leave_request",
                    "employee_id",
                    "Employee reference",
                    "Referenced employee.",
                    "integer",
                    "identifier",
                    foreign_key=True,
                ),
                _field(
                    "leave_request",
                    "leave_type",
                    "Leave type",
                    "Classification of leave.",
                    "string",
                    "dimension",
                ),
                _field(
                    "leave_request",
                    "start_date",
                    "Leave start date",
                    "Leave period start.",
                    "date",
                    "date",
                ),
                _field(
                    "leave_request",
                    "end_date",
                    "Leave end date",
                    "Leave period end.",
                    "date",
                    "date",
                ),
                _field(
                    "leave_request",
                    "status",
                    "Leave status",
                    "Current leave request status.",
                    "string",
                    "status",
                ),
            ],
            temporal_fields=["start_date", "end_date"],
            relationships=["leave_request_employee"],
        ),
        _entity(
            "payroll_period",
            "Payroll period",
            "Period and payment date for a payroll run.",
            "payroll_period",
            [
                _field(
                    "payroll_period",
                    "id",
                    "Payroll period identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    primary_key=True,
                ),
                _field(
                    "payroll_period",
                    "code",
                    "Payroll period code",
                    "Business payroll period code.",
                    "string",
                    "identifier",
                ),
                _field(
                    "payroll_period",
                    "start_date",
                    "Period start date",
                    "Payroll coverage start.",
                    "date",
                    "date",
                ),
                _field(
                    "payroll_period",
                    "end_date",
                    "Period end date",
                    "Payroll coverage end.",
                    "date",
                    "date",
                ),
                _field(
                    "payroll_period",
                    "payment_date",
                    "Payment date",
                    "Date payroll is paid.",
                    "date",
                    "date",
                ),
                _field(
                    "payroll_period",
                    "status",
                    "Payroll period status",
                    "Current processing status.",
                    "string",
                    "status",
                ),
            ],
            sensitivity="confidential",
            temporal_fields=["start_date", "end_date", "payment_date"],
        ),
        _entity(
            "payroll",
            "Employee payroll",
            "Employee payroll totals for a payroll period.",
            "employee_payroll",
            [
                _field(
                    "employee_payroll",
                    "id",
                    "Payroll record identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    "restricted",
                    primary_key=True,
                ),
                _field(
                    "employee_payroll",
                    "employee_id",
                    "Employee reference",
                    "Referenced employee.",
                    "integer",
                    "identifier",
                    "restricted",
                    foreign_key=True,
                ),
                _field(
                    "employee_payroll",
                    "payroll_period_id",
                    "Payroll period reference",
                    "Referenced payroll period.",
                    "integer",
                    "identifier",
                    "restricted",
                    foreign_key=True,
                ),
                _field(
                    "employee_payroll",
                    "gross_amount",
                    "Gross pay",
                    "Gross payroll amount before deductions.",
                    "decimal",
                    "amount",
                    "restricted",
                    unit="currency",
                ),
                _field(
                    "employee_payroll",
                    "deduction_amount",
                    "Deductions",
                    "Total deductions from gross pay.",
                    "decimal",
                    "amount",
                    "restricted",
                    unit="currency",
                ),
                _field(
                    "employee_payroll",
                    "net_amount",
                    "Net pay",
                    "Amount paid after deductions.",
                    "decimal",
                    "amount",
                    "restricted",
                    unit="currency",
                ),
                _field(
                    "employee_payroll",
                    "employer_cost",
                    "Employer cost",
                    "Total employer cost for the payroll record.",
                    "decimal",
                    "amount",
                    "restricted",
                    unit="currency",
                ),
                _field(
                    "employee_payroll",
                    "cost_center",
                    "Payroll cost center",
                    "Cost center charged for payroll.",
                    "string",
                    "dimension",
                    "restricted",
                ),
            ],
            "restricted",
            relationships=["payroll_employee", "payroll_period"],
            operations=["read", "aggregate"],
        ),
        _entity(
            "payroll_concept",
            "Payroll concept",
            "Definition of a payroll earning or deduction concept.",
            "payroll_concept",
            [
                _field(
                    "payroll_concept",
                    "id",
                    "Concept identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    "restricted",
                    primary_key=True,
                ),
                _field(
                    "payroll_concept",
                    "code",
                    "Concept code",
                    "Business payroll concept code.",
                    "string",
                    "identifier",
                    "restricted",
                ),
                _field(
                    "payroll_concept",
                    "name",
                    "Concept name",
                    "Display name of the concept.",
                    "string",
                    "dimension",
                    "restricted",
                ),
                _field(
                    "payroll_concept",
                    "concept_type",
                    "Concept type",
                    "Earning or deduction classification.",
                    "string",
                    "dimension",
                    "restricted",
                ),
                _field(
                    "payroll_concept",
                    "taxable",
                    "Taxable flag",
                    "Whether the concept is taxable.",
                    "boolean",
                    "status",
                    "restricted",
                ),
            ],
            "restricted",
            operations=["read"],
        ),
        _entity(
            "payroll_item",
            "Payroll item",
            "Payroll concept amount included in an employee payroll record.",
            "payroll_item",
            [
                _field(
                    "payroll_item",
                    "id",
                    "Payroll item identifier",
                    "Stable source identifier.",
                    "integer",
                    "identifier",
                    "restricted",
                    primary_key=True,
                ),
                _field(
                    "payroll_item",
                    "employee_payroll_id",
                    "Payroll record reference",
                    "Referenced employee payroll record.",
                    "integer",
                    "identifier",
                    "restricted",
                    foreign_key=True,
                ),
                _field(
                    "payroll_item",
                    "payroll_concept_id",
                    "Payroll concept reference",
                    "Referenced payroll concept.",
                    "integer",
                    "identifier",
                    "restricted",
                    foreign_key=True,
                ),
                _field(
                    "payroll_item",
                    "quantity",
                    "Concept quantity",
                    "Quantity associated with the concept.",
                    "decimal",
                    "quantity",
                    "restricted",
                ),
                _field(
                    "payroll_item",
                    "rate",
                    "Concept rate",
                    "Rate applied to the concept quantity.",
                    "decimal",
                    "amount",
                    "restricted",
                    unit="currency",
                ),
                _field(
                    "payroll_item",
                    "amount",
                    "Concept amount",
                    "Calculated amount for the concept.",
                    "decimal",
                    "amount",
                    "restricted",
                    unit="currency",
                ),
                _field(
                    "payroll_item",
                    "source_reference",
                    "Source reference",
                    "Reference supplied by the payroll source.",
                    "string",
                    "identifier",
                    "restricted",
                    nullable=True,
                ),
            ],
            "restricted",
            relationships=["payroll_item_payroll", "payroll_item_concept"],
        ),
    ]

    relationships = [
        (
            "employee_department",
            "employee",
            "department",
            "many_to_one",
            "Employee belongs to one department.",
            "employee.department_id = department.id",
        ),
        (
            "employee_position",
            "employee",
            "position",
            "many_to_one",
            "Employee holds one position.",
            "employee.position_id = position.id",
        ),
        (
            "position_department",
            "position",
            "department",
            "many_to_one",
            "Position belongs to one department.",
            "position.department_id = department.id",
        ),
        (
            "contract_employee",
            "contract",
            "employee",
            "many_to_one",
            "Contract belongs to one employee.",
            "contract.employee_id = employee.id",
        ),
        (
            "attendance_employee",
            "attendance",
            "employee",
            "many_to_one",
            "Attendance belongs to one employee.",
            "attendance_record.employee_id = employee.id",
        ),
        (
            "attendance_incident_employee",
            "attendance_incident",
            "employee",
            "many_to_one",
            "Incident belongs to one employee.",
            "attendance_incident.employee_id = employee.id",
        ),
        (
            "overtime_employee",
            "overtime",
            "employee",
            "many_to_one",
            "Overtime belongs to one employee.",
            "overtime_record.employee_id = employee.id",
        ),
        (
            "vacation_balance_employee",
            "vacation_balance",
            "employee",
            "many_to_one",
            "Balance belongs to one employee.",
            "vacation_balance.employee_id = employee.id",
        ),
        (
            "vacation_request_employee",
            "vacation_request",
            "employee",
            "many_to_one",
            "Request belongs to one employee.",
            "vacation_request.employee_id = employee.id",
        ),
        (
            "leave_request_employee",
            "leave_request",
            "employee",
            "many_to_one",
            "Leave belongs to one employee.",
            "leave_request.employee_id = employee.id",
        ),
        (
            "payroll_employee",
            "payroll",
            "employee",
            "many_to_one",
            "Payroll belongs to one employee.",
            "employee_payroll.employee_id = employee.id",
        ),
        (
            "payroll_period",
            "payroll",
            "payroll_period",
            "many_to_one",
            "Payroll belongs to one period.",
            "employee_payroll.payroll_period_id = payroll_period.id",
        ),
        (
            "payroll_item_payroll",
            "payroll_item",
            "payroll",
            "many_to_one",
            "Item belongs to one payroll record.",
            "payroll_item.employee_payroll_id = employee_payroll.id",
        ),
        (
            "payroll_item_concept",
            "payroll_item",
            "payroll_concept",
            "many_to_one",
            "Item uses one payroll concept.",
            "payroll_item.payroll_concept_id = payroll_concept.id",
        ),
    ]
    relation_models = [
        RelationshipMetadata(
            relationship_id=i,
            from_entity=f,
            to_entity=t,
            relationship_type=typ,
            join_semantics=sem,
            physical_mapping=map_,
        )
        for i, f, t, typ, sem, map_ in relationships
    ]
    capabilities = [
        CapabilityMetadata(
            name="workforce",
            description="Employee identity and employment structure.",
            entities=["employee", "department", "position"],
            supported_operations=["read", "aggregate"],
            sensitivity="confidential",
        ),
        CapabilityMetadata(
            name="employment",
            description="Contracts and contract dates.",
            entities=["contract"],
            supported_operations=["read", "aggregate"],
            sensitivity="confidential",
        ),
        CapabilityMetadata(
            name="attendance",
            description="Attendance records and incidents.",
            entities=["attendance", "attendance_incident"],
            supported_operations=["read", "aggregate"],
            sensitivity="confidential",
        ),
        CapabilityMetadata(
            name="overtime",
            description="Approved overtime records.",
            entities=["overtime"],
            supported_operations=["read", "aggregate"],
            sensitivity="confidential",
        ),
        CapabilityMetadata(
            name="time_off",
            description="Vacation balances, vacation requests and leave.",
            entities=["vacation_balance", "vacation_request", "leave_request"],
            supported_operations=["read", "aggregate"],
            sensitivity="confidential",
        ),
        CapabilityMetadata(
            name="payroll",
            description="Payroll periods, totals and concepts.",
            entities=["payroll_period", "payroll", "payroll_concept", "payroll_item"],
            supported_operations=["read", "aggregate"],
            sensitivity="restricted",
        ),
    ]
    provisional = CatalogMetadata(
        provider_type="reference_synthetic_hris",
        catalog_version=catalog_version,
        fingerprint="pending",
        capabilities=capabilities,
        entities=entities,
        relationships=relation_models,
    )
    canonical = provisional.model_dump(mode="json", exclude={"fingerprint"})
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return provisional.model_copy(update={"fingerprint": fingerprint})
