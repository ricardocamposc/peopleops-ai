# PeopleOps AI — Data Design (DATA)

## 1. Ownership
Tres categorías:
1. PeopleOps Application Data.
2. Synthetic Reference HRIS Data.
3. Evaluation Data.

## 2. PeopleOps Application Data

### Conversation
```text
id
created_at
updated_at
status
created_by
metadata JSONB
```

### AnalysisInteraction
```text
id
request_id UNIQUE
conversation_id FK nullable
question
status
current_stage
stage_history JSONB
semantic_request JSONB
analysis_goal
query_plan JSONB
provider_type
provider_catalog_version
validation JSONB
structured_result JSONB
policy_sources JSONB
policy_versions JSONB
evidence JSONB
human_review_status
human_review_id
response JSONB
warnings JSONB
model_name
latency_ms
error_type
error_detail
created_at
updated_at
completed_at
```

### HumanReviewRequest
```text
id
analysis_id FK
status
reason
recommendation_snapshot
evidence_snapshot
requested_at
reviewed_at
reviewed_by
decision
comments
```

### PolicyDocument
```text
id
document_key
title
document_type
department
confidentiality
status
created_at
```

### PolicyVersion
```text
id
policy_document_id
version
effective_from
effective_to
status
original_filename
storage_uri
checksum
metadata JSONB
created_at
```

### PolicyChunk
Debe preservar como mínimo:
```text
policy_version_id
text
page
section
chunk_index
embedding
metadata
```
El schema puede adaptarse al almacenamiento LlamaIndex/pgvector.

### IngestionJob
```text
id
policy_version_id
status
started_at
completed_at
chunk_count
error_type
error_detail
```

## 3. Synthetic Reference HRIS

### Employee
id, employee_code, first_name, last_name, status, hire_date, department_id, position_id.

### Department
id, code, name, cost_center.

### Position
id, code, name, department_id.

### Contract
id, employee_id, contract_type, start_date, end_date, status.

### AttendanceRecord
id, employee_id, work_date, status, scheduled_minutes, worked_minutes, late_minutes, absence_minutes.

### AttendanceIncident
id, employee_id, incident_date, incident_type, minutes, status.

### OvertimeRecord
id, employee_id, work_date, approved_minutes, status.

### VacationBalance
id, employee_id, period_year, earned_days, used_days, scheduled_days, available_days.

### VacationRequest
id, employee_id, start_date, end_date, requested_days, status, created_at.

### LeaveRequest
id, employee_id, leave_type, start_date, end_date, status.

### PayrollPeriod
id, code, start_date, end_date, payment_date, status.

### EmployeePayroll
id, employee_id, payroll_period_id, gross_amount, deduction_amount, net_amount, employer_cost, cost_center.

### PayrollConcept
id, code, name, concept_type, taxable.

### PayrollItem
id, employee_payroll_id, payroll_concept_id, quantity, rate, amount, source_reference.

Estas entidades son fixtures de referencia, no el contrato del producto.

## 4. MCP Semantic Catalog

### Capability
```text
name
description
entities[]
supported_operations[]
sensitivity
```

### EntityMetadata
```text
entity_id
business_name
description
physical_source
fields[]
relationships[]
temporal_fields[]
sensitivity
```

### FieldMetadata
```text
field_id
business_name
description
data_type
unit
nullable
physical_source
semantic_role
sensitivity
```

semantic_role candidato: identifier, dimension, metric, date, status, amount, quantity.

### RelationshipMetadata
```text
from_entity
to_entity
relationship_type
join_semantics
physical_mapping
```

## 5. Conceptual Query Model
Contrato candidato:
```json
{
  "goal": "reconcile_overtime_payroll",
  "entities": ["employee","overtime","payroll"],
  "select": [
    {"field":"employee.employee_code"},
    {"metric":"overtime.recorded_hours"},
    {"metric":"payroll.paid_overtime_hours"}
  ],
  "time_scope": {"type":"payroll_period","value":"current"},
  "conditions": [{
    "left":"overtime.recorded_hours",
    "operator":">",
    "right":"payroll.paid_overtime_hours"
  }],
  "limit": 100
}
```
Debe ser tipado, validable, provider-neutral y extensible.

## 6. Evidence

### StructuredDataEvidence
provider, catalog_version, query_id/hash, entities, fields/metrics, time_scope, row_count, result_reference.

### PolicyEvidence
policy_document_id, policy_version_id, title, version, page, section, chunk_id, retrieval_score, verified.

### HumanEvidence
review_id, reviewer, decision, reviewed_at.

## 7. Evaluation Data
Fuera de PeopleOps DB por defecto. JSONL recomendado:
case_id, question, language, scenario, expected_capabilities,
expected_query_features, expected_policy_sources, expected_facts,
expected_policy_facts, expected_human_review, expected_status, difficulty.

## 8. Alternate Schema
Schema físico alternativo pequeño:
```text
HR_PERSON
HR_CONTRACT
TIME_EVENT
PAY_RUN
PAY_MOVEMENT
```
El mapping reside en MCP/test adapter. PeopleOps no cambia.

## 9. Database Separation
Puede usarse una misma instancia PostgreSQL, pero con ownership separado:
```text
postgres
├─ peopleops_app
└─ synthetic_hris
```

Reference MCP Server: credenciales solo para synthetic_hris.
PeopleOps API: credenciales solo para peopleops_app.

Esta separación debe ser verificable por configuración.

## 10. Privacy Baseline
MVP: sin PII real, sin secretos, logs minimizados.
No implementar políticas legales específicas sin requerimiento real.
