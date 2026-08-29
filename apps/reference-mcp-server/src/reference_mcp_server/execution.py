"""Semantic validation and controlled PostgreSQL execution for conceptual queries."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from dataclasses import dataclass
from typing import Any

import psycopg

from reference_mcp_server.config import Settings
from reference_mcp_server.audit import monotonic_started, record_interaction
from reference_mcp_server.discovery import CatalogMetadata, EntityMetadata, RelationshipMetadata
from reference_mcp_server.query_contracts import (
    ConceptualQuery,
    QueryEvidence,
    QueryMetric,
    QueryPeriod,
    QueryResult,
    QueryValidation,
)


class QueryExecutionError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def query_hash(query: ConceptualQuery) -> str:
    payload = json.dumps(query.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def validate_query(
    query: ConceptualQuery,
    catalog: CatalogMetadata,
    scopes: list[str],
    *,
    request_id: str | None = None,
    max_result_rows: int = 1000,
) -> QueryValidation:
    errors: list[str] = []
    entities = {entity.entity_id: entity for entity in catalog.entities}
    relations = {relation.relationship_id: relation for relation in catalog.relationships}
    selected_entities = set(query.entities)
    for entity_id in query.entities:
        if entity_id not in entities:
            errors.append(f"unknown entity: {entity_id}")
    if len(selected_entities) != len(query.entities):
        errors.append("entities must be unique")
    if len(set(query.relationships)) != len(query.relationships):
        errors.append("relationships must be unique")
    projection_labels = [
        item.alias or item.field.rsplit(".", 1)[-1] for item in query.select
    ] + [_metric_label(metric) for metric in query.metrics]
    if len(set(projection_labels)) != len(projection_labels):
        errors.append("select and metric aliases must be unique")
    for relation_id in query.relationships:
        relation = relations.get(relation_id)
        if relation is None:
            errors.append(f"unknown relationship: {relation_id}")
        elif (
            relation.from_entity not in selected_entities
            or relation.to_entity not in selected_entities
        ):
            errors.append(f"relationship does not connect selected entities: {relation_id}")

    refs = [item.field for item in query.select]
    refs += [metric.field for metric in query.metrics if metric.field]
    refs += [item.field for item in query.filters]
    refs += [item.left for item in query.comparisons] + [item.right for item in query.comparisons]
    metric_labels = {_metric_label(metric) for metric in query.metrics}
    refs += [item.reference for item in query.order_by if item.reference not in metric_labels]
    refs += query.dimensions
    if query.time_scope:
        refs += _period_fields(query.time_scope)
        _validate_temporal_scope(query.time_scope, entities, selected_entities, errors)
    sensitive = False
    for reference in refs:
        try:
            entity_id, field_id = _split_reference(reference)
        except QueryExecutionError as exc:
            errors.append(str(exc))
            continue
        entity = entities.get(entity_id)
        if entity is None or entity_id not in selected_entities:
            errors.append(f"reference is not in selected entities: {reference}")
            continue
        field = next((field for field in entity.fields if field.field_id == field_id), None)
        if field is None:
            errors.append(f"unknown field: {reference}")
        elif field.sensitivity == "restricted":
            sensitive = True
    sensitive = sensitive or any(
        entity_id in entities and entities[entity_id].sensitivity == "restricted"
        for entity_id in selected_entities
    )
    sensitive = sensitive or any(
        entities.get(_safe_entity_id(reference), _empty_entity()).sensitivity == "restricted"
        for reference in refs
        if "." in reference
    )
    if sensitive and "hr:payroll" not in scopes:
        errors.append("authorization scope hr:payroll is required for restricted data")
    if query.limit > max_result_rows:
        errors.append(f"limit must not exceed provider maximum of {max_result_rows}")
    if (
        query.time_scope
        and query.time_scope.type == "payroll_period"
        and "payroll_period" not in selected_entities
    ):
        errors.append("payroll_period time scope requires the payroll_period entity")
    return QueryValidation(
        request_id=request_id,
        valid=not errors,
        query_hash=query_hash(query),
        catalog_version=catalog.catalog_version,
        errors=errors,
    )


@dataclass(frozen=True)
class PhysicalQuery:
    sql: str
    params: tuple[Any, ...]
    columns: list[str]


def validate_physical_query(physical: PhysicalQuery) -> None:
    """Defence-in-depth check for the SQL generated by the source adapter."""
    normalized = physical.sql.strip().lower()
    if (
        not normalized.startswith("select ")
        or ";" in normalized
        or "--" in normalized
        or "/*" in normalized
        or "*/" in normalized
        or " for update" in normalized
        or " into " in normalized
    ):
        raise QueryExecutionError(
            "PHYSICAL_QUERY_INVALID", "provider generated a non-read-only query"
        )
    if any(
        token in normalized
        for token in (
            " insert ",
            " update ",
            " delete ",
            " drop ",
            " alter ",
            " truncate ",
            " copy ",
            " pg_sleep",
        )
    ):
        raise QueryExecutionError(
            "PHYSICAL_QUERY_INVALID", "provider generated a non-read-only query"
        )


def translate_query(query: ConceptualQuery, catalog: CatalogMetadata) -> PhysicalQuery:
    """Translate only catalog-allowlisted semantic references to parameterized SQL."""
    entities = {entity.entity_id: entity for entity in catalog.entities}
    relations = {relation.relationship_id: relation for relation in catalog.relationships}
    aliases = {entity_id: f"t{index}" for index, entity_id in enumerate(query.entities)}
    tables = (
        f"{_identifier(entities[query.entities[0]].physical_source)} {aliases[query.entities[0]]}"
    )
    joins: list[str] = []
    joined_entities = {query.entities[0]}
    pending_relationships = [relations[relation_id] for relation_id in query.relationships]
    while pending_relationships:
        progress = False
        remaining: list[RelationshipMetadata] = []
        for relation in pending_relationships:
            join = _join_sql(relation, entities, aliases, joined_entities)
            if join is None:
                remaining.append(relation)
                continue
            if join:
                joins.append(join)
            progress = True
        if not progress:
            raise QueryExecutionError(
                "QUERY_VALIDATION_ERROR", "relationships do not form a connected join path"
            )
        pending_relationships = remaining
    params: list[Any] = []
    projections: list[str] = []
    columns: list[str] = []
    for item in query.select:
        expression, label = _field_sql(item.field, entities, aliases)
        label = item.alias or label
        projections.append(f"{expression} AS {_output_identifier(label)}")
        columns.append(label)
    for metric in query.metrics:
        expression, field_label = _metric_sql(metric, entities, aliases)
        label = _metric_label(metric, field_label)
        projections.append(f"{expression} AS {_output_identifier(label)}")
        columns.append(label)
    predicates: list[str] = []
    for item in query.filters:
        predicates.append(_filter_sql(item, entities, aliases, params))
    if query.time_scope:
        predicates.extend(_period_sql(query.time_scope, entities, aliases, params))
    for comparison in query.comparisons:
        left, _ = _field_sql(comparison.left, entities, aliases)
        right, _ = _field_sql(comparison.right, entities, aliases)
        predicates.append(f"{left} {_comparison_operator(comparison.operator)} {right}")
    # Every non-aggregate projection must be grouped.  Dimensions are an
    # additional grouping contract, not a replacement for selected fields.
    # Omitting a selected field produces a valid-looking query that PostgreSQL
    # correctly rejects with a GROUP BY error.
    group_refs = list(dict.fromkeys(
        [item.field for item in query.select] + list(query.dimensions)
    ))
    group_by = (
        " GROUP BY " + ", ".join(_field_sql(ref, entities, aliases)[0] for ref in group_refs)
        if query.metrics and group_refs
        else ""
    )
    order = ""
    if query.order_by:
        order = " ORDER BY " + ", ".join(
            f"{_order_sql(item.reference, query, entities, aliases)} {item.direction.upper()}"
            for item in query.order_by
        )
    where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
    sql = f"SELECT {', '.join(projections)} FROM {tables}{''.join(joins)}{where}{group_by}{order} LIMIT {query.limit}"
    return PhysicalQuery(sql=sql, params=tuple(params), columns=columns)


def execute_query(
    query: ConceptualQuery,
    *,
    catalog: CatalogMetadata,
    settings: Settings,
    request_id: str,
    scopes: list[str],
) -> QueryResult:
    started_at, _ = monotonic_started()
    query_payload = query.model_dump(mode="json")
    physical: PhysicalQuery | None = None
    validation: QueryValidation | None = None
    validation = validate_query(
        query, catalog, scopes, request_id=request_id, max_result_rows=settings.max_result_rows
    )
    if not validation.valid:
        if settings.mcp_audit_enabled:
            record_interaction(
                settings, tool_name="execute_conceptual_query", request_id=request_id,
                started_at=started_at, status="validation_rejected",
                catalog_version=validation.catalog_version, provider_type=catalog.provider_type,
                conceptual_query=query_payload, query_hash=validation.query_hash,
                validation_result=validation.model_dump(mode="json"),
                validation_errors=validation.errors, execution_attempted=False,
                error_code="QUERY_VALIDATION_ERROR", error_message_safe="query validation failed",
            )
        return QueryResult(request_id=request_id, validation=validation)
    try:
        physical = translate_query(query, catalog)
        validate_physical_query(physical)
    except QueryExecutionError as exc:
        if settings.mcp_audit_enabled:
            record_interaction(
                settings, tool_name="execute_conceptual_query", request_id=request_id,
                started_at=started_at, status="physical_validation_failed",
                catalog_version=validation.catalog_version, provider_type=catalog.provider_type,
                conceptual_query=query_payload, query_hash=validation.query_hash,
                validation_result=validation.model_dump(mode="json"),
                physical_sql=physical.sql if physical else None,
                physical_params=physical.params if physical else None,
                execution_attempted=False, error_code=exc.code,
                error_message_safe="physical query validation failed",
            )
        raise
    result_limit = min(query.limit, settings.max_result_rows)
    try:
        with (
            psycopg.connect(
                _database_url(settings), connect_timeout=max(1, int(settings.query_timeout_seconds))
            ) as connection,
            connection.transaction(),
        ):
            connection.execute("SET LOCAL transaction_read_only = on")
            connection.execute(
                f"SET LOCAL statement_timeout = {int(settings.query_timeout_seconds * 1000)}"
            )
            with connection.cursor() as cursor:
                cursor.execute(f"EXPLAIN {physical.sql}", physical.params)
                cursor.fetchall()
                cursor.execute(physical.sql, physical.params)
                rows = [
                    dict(zip(physical.columns, row, strict=True))
                    for row in cursor.fetchmany(result_limit)
                ]
                if (
                    len(json.dumps(rows, default=str, separators=(",", ":")).encode())
                    > settings.max_result_bytes
                ):
                    raise QueryExecutionError(
                        "RESULT_LIMIT_EXCEEDED", "query result exceeded the provider size limit"
                    )
    except psycopg.errors.QueryCanceled as exc:
        if settings.mcp_audit_enabled:
            record_interaction(
                settings, tool_name="execute_conceptual_query", request_id=request_id,
                started_at=started_at, status="execution_failed",
                catalog_version=validation.catalog_version, provider_type=catalog.provider_type,
                conceptual_query=query_payload, query_hash=validation.query_hash,
                validation_result=validation.model_dump(mode="json"), physical_sql=physical.sql,
                physical_params=physical.params, execution_attempted=True,
                execution_success=False, error_code="QUERY_TIMEOUT",
                error_message_safe="query exceeded provider timeout",
            )
        raise QueryExecutionError(
            "QUERY_TIMEOUT", "query exceeded the provider timeout", retryable=True
        ) from exc
    except (psycopg.errors.SyntaxError, psycopg.errors.UndefinedColumn, psycopg.errors.UndefinedTable) as exc:
        if settings.mcp_audit_enabled:
            record_interaction(
                settings, tool_name="execute_conceptual_query", request_id=request_id,
                started_at=started_at, status="execution_failed",
                catalog_version=validation.catalog_version, provider_type=catalog.provider_type,
                conceptual_query=query_payload, query_hash=validation.query_hash,
                validation_result=validation.model_dump(mode="json"), physical_sql=physical.sql,
                physical_params=physical.params, execution_attempted=True,
                execution_success=False, error_code="QUERY_VALIDATION_FAILED",
                error_message_safe="provider rejected the validated query",
            )
        raise QueryExecutionError(
            "QUERY_VALIDATION_FAILED", "provider rejected the validated physical query"
        ) from exc
    except (psycopg.Error, OSError) as exc:
        if settings.mcp_audit_enabled:
            record_interaction(
                settings, tool_name="execute_conceptual_query", request_id=request_id,
                started_at=started_at, status="execution_failed",
                catalog_version=validation.catalog_version, provider_type=catalog.provider_type,
                conceptual_query=query_payload, query_hash=validation.query_hash,
                validation_result=validation.model_dump(mode="json"), physical_sql=physical.sql,
                physical_params=physical.params, execution_attempted=True,
                execution_success=False, error_code="QUERY_EXECUTION_ERROR",
                error_message_safe="provider failed to execute the query",
            )
        raise QueryExecutionError(
            "QUERY_EXECUTION_ERROR", "provider failed to execute the validated query"
        ) from exc
    evidence = QueryEvidence(
        provider=catalog.provider_type,
        catalog_version=catalog.catalog_version,
        query_hash=validation.query_hash,
        entities=query.entities,
        fields=_evidence_fields(query),
        metrics=[metric.alias or metric.field or metric.function for metric in query.metrics],
        time_scope=query.time_scope.model_dump(mode="json") if query.time_scope else None,
        row_count=len(rows),
        result_reference=f"mcp://{catalog.provider_type}/query/{validation.query_hash}",
        request_id=request_id,
    )
    if settings.mcp_audit_enabled:
        record_interaction(
            settings, tool_name="execute_conceptual_query", request_id=request_id,
            started_at=started_at, status="completed",
            catalog_version=validation.catalog_version, provider_type=catalog.provider_type,
            conceptual_query=query_payload, query_hash=validation.query_hash,
            validation_result=validation.model_dump(mode="json"), physical_sql=physical.sql,
            physical_params=physical.params, execution_attempted=True,
            execution_success=True, row_count=len(rows),
        )
    return QueryResult(
        request_id=request_id,
        validation=validation,
        columns=physical.columns,
        rows=rows,
        evidence=evidence,
    )


def _database_url(settings: Settings) -> str:
    return f"postgresql://{settings.synthetic_hris_database_user}:{settings.synthetic_hris_database_password}@{settings.synthetic_hris_database_host}:{settings.synthetic_hris_database_port}/{settings.synthetic_hris_database_name}"


def _split_reference(reference: str) -> tuple[str, str]:
    if reference.count(".") != 1:
        raise QueryExecutionError("QUERY_VALIDATION_ERROR", f"invalid field reference: {reference}")
    entity_id, field_id = reference.split(".", 1)
    return entity_id, field_id


def _safe_entity_id(reference: str) -> str:
    return reference.split(".", 1)[0] if "." in reference else ""


def _evidence_fields(query: ConceptualQuery) -> list[str]:
    fields = [item.field for item in query.select]
    fields.extend(metric.field for metric in query.metrics if metric.field)
    fields.extend(item.field for item in query.filters)
    fields.extend(query.dimensions)
    fields.extend(_period_fields(query.time_scope) if query.time_scope else [])
    for comparison in query.comparisons:
        fields.extend([comparison.left, comparison.right])
    return list(dict.fromkeys(fields))


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise QueryExecutionError("QUERY_VALIDATION_ERROR", "invalid allowlisted identifier")
    return f'"{value}"'


def _output_identifier(value: str) -> str:
    """Quote a model-provided output label without treating it as SQL."""
    if not value or len(value) > 128 or "\x00" in value:
        raise QueryExecutionError("QUERY_VALIDATION_ERROR", "invalid output alias")
    return '"' + value.replace('"', '""') + '"'


def _field_sql(
    reference: str, entities: dict[str, EntityMetadata], aliases: dict[str, str]
) -> tuple[str, str]:
    entity_id, field_id = _split_reference(reference)
    entity = entities.get(entity_id)
    if entity is None or entity_id not in aliases:
        raise QueryExecutionError("QUERY_VALIDATION_ERROR", f"unknown field reference: {reference}")
    field = next((item for item in entity.fields if item.field_id == field_id), None)
    if field is None:
        raise QueryExecutionError("QUERY_VALIDATION_ERROR", f"unknown field reference: {reference}")
    physical_column = field.physical_source.rsplit(".", 1)[-1]
    return f"{aliases[entity_id]}.{_identifier(physical_column)}", field_id


def _metric_sql(
    metric: QueryMetric, entities: dict[str, EntityMetadata], aliases: dict[str, str]
) -> tuple[str, str]:
    if metric.function == "count" and metric.field is None:
        return "COUNT(*)", "rows"
    field_sql, label = _field_sql(metric.field or "", entities, aliases)
    return f"{metric.function.upper()}({field_sql})", label


def _metric_label(metric: QueryMetric, field_label: str | None = None) -> str:
    if metric.alias:
        return metric.alias
    if metric.field:
        return f"{metric.function}_{field_label or metric.field.rsplit('.', 1)[-1]}"
    return "rows"


def _filter_sql(
    item: Any, entities: dict[str, EntityMetadata], aliases: dict[str, str], params: list[Any]
) -> str:
    field, _ = _field_sql(item.field, entities, aliases)
    operators = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if item.operator in {"is_null", "not_null"}:
        return f"{field} IS {'NOT ' if item.operator == 'not_null' else ''}NULL"
    if item.operator in {"in", "not_in"}:
        params.extend(item.value)
        markers = ", ".join(["%s"] * len(item.value))
        return f"{field} {'NOT IN' if item.operator == 'not_in' else 'IN'} ({markers})"
    params.append(item.value)
    return f"{field} {operators[item.operator]} %s"


def _join_sql(
    relation: RelationshipMetadata,
    entities: dict[str, EntityMetadata],
    aliases: dict[str, str],
    joined_entities: set[str],
) -> str | None:
    parts = re.fullmatch(
        r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
        relation.physical_mapping,
    )
    if not parts:
        raise QueryExecutionError("QUERY_VALIDATION_ERROR", "invalid provider relationship mapping")
    left_table, left_column, right_table, right_column = parts.groups()
    source_tables = {entities[entity].physical_source: aliases[entity] for entity in aliases}
    if left_table not in source_tables or right_table not in source_tables:
        raise QueryExecutionError(
            "QUERY_VALIDATION_ERROR", "relationship mapping is outside selected entities"
        )
    if relation.from_entity not in joined_entities and relation.to_entity not in joined_entities:
        return None
    if relation.to_entity not in joined_entities:
        join_entity = relation.to_entity
    elif relation.from_entity not in joined_entities:
        join_entity = relation.from_entity
    else:
        return ""
    joined_entities.add(join_entity)
    return f" JOIN {_identifier(entities[join_entity].physical_source)} {aliases[join_entity]} ON {source_tables[left_table]}.{_identifier(left_column)} = {source_tables[right_table]}.{_identifier(right_column)}"


def _period_fields(period: QueryPeriod) -> list[str]:
    if period.type == "period_comparison":
        return _period_fields(period.current) + _period_fields(period.previous)  # type: ignore[arg-type]
    return [period.field] if period.field else []


def _validate_temporal_scope(
    period: QueryPeriod,
    entities: dict[str, EntityMetadata],
    selected_entities: set[str],
    errors: list[str],
) -> None:
    if period.type == "period_comparison":
        if period.current:
            _validate_temporal_scope(period.current, entities, selected_entities, errors)
        if period.previous:
            _validate_temporal_scope(period.previous, entities, selected_entities, errors)
        return
    if period.type == "payroll_period" and not period.field:
        return
    if not period.field:
        errors.append("INVALID_TIME_FIELD: temporal scope requires a field")
        return
    try:
        entity_id, field_id = _split_reference(period.field)
    except QueryExecutionError as exc:
        errors.append(str(exc))
        return
    entity = entities.get(entity_id)
    field = next((item for item in entity.fields if item.field_id == field_id), None) if entity else None
    if entity_id not in selected_entities or field is None:
        errors.append(f"INVALID_TIME_FIELD: unknown temporal field: {period.field}")
        return
    temporal = field.temporal_kind in {"date", "datetime"} or field_id in entity.temporal_fields
    period_capable = entity.supports_period_filter or field.temporal_kind == "period"
    if period.type == "date_range" and not temporal:
        errors.append(f"INVALID_TIME_FIELD: date_range requires date/datetime field: {period.field}")
    if period.type in {"period", "period_list", "payroll_period"} and not (temporal or period_capable):
        errors.append(f"INVALID_TIME_FIELD: period is not supported by field: {period.field}")


def _period_sql(
    period: QueryPeriod,
    entities: dict[str, EntityMetadata],
    aliases: dict[str, str],
    params: list[Any],
) -> list[str]:
    if period.type == "date_range":
        field, _ = _field_sql(period.field or "", entities, aliases)
        params.extend([period.start, period.end])
        return [f"{field} BETWEEN %s AND %s"]
    if period.type in {"period", "period_list"}:
        values = [period.period] if period.type == "period" else period.periods
        predicates: list[str] = []
        for value in values:
            if value is None:
                continue
            start = date(value.year, value.month, 1)
            next_month = value.month % 12 + 1
            next_year = value.year + (1 if value.month == 12 else 0)
            end = date(next_year, next_month, 1)
            field, _ = _field_sql(period.field or "", entities, aliases)
            params.extend([start, end])
            predicates.append(f"{field} >= %s AND {field} < %s")
        return ["(" + " OR ".join(predicates) + ")"] if predicates else []
    if period.type == "payroll_period":
        field, _ = _field_sql("payroll_period.code", entities, aliases)
        params.append(period.value)
        return [f"{field} = %s"]
    return _period_sql(period.current, entities, aliases, params) + _period_sql(
        period.previous, entities, aliases, params
    )  # type: ignore[arg-type]


def _comparison_operator(operator: str) -> str:
    return {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[operator]


def _order_sql(
    reference: str,
    query: ConceptualQuery,
    entities: dict[str, EntityMetadata],
    aliases: dict[str, str],
) -> str:
    if any(
        _metric_label(metric) == reference for metric in query.metrics
    ):
        return _output_identifier(reference)
    return _field_sql(reference, entities, aliases)[0]


def _empty_entity() -> EntityMetadata:
    return EntityMetadata(
        entity_id="",
        business_name="",
        description="",
        physical_source="",
        fields=[],
        sensitivity="internal",
        supported_operations=[],
    )
