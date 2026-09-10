"""Phase 2.3: corrected isolated live Semantic Query DSL spike.

Starts from production baseline 60db56f and stops before Query IR/MCP/SQL.
The experiment tests capability scoping, typed query operations, generic DATE
capabilities, deterministic relative-date resolution, and semantic evaluation.
"""
from __future__ import annotations

import argparse, hashlib, json, os, time, uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field
from peopleops_api.analysis_workflow import OpenAIStructuredModel

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATE = date(2026, 8, 30)
SOURCE_TIMEZONE = "UTC"

CAPABILITIES: dict[str, dict[str, Any]] = {
    "overtime": {"description": "Recorded and approved employee overtime.", "fields": {
        "overtime.work_date": {"data_type": "DATE", "semantic_type": "calendar_date", "description": "Business date on which overtime was worked."},
        "overtime.approved_minutes": {"data_type": "INTEGER", "semantic_type": "duration_minutes", "query_role": "measure", "default_aggregation": "SUM", "description": "Approved overtime duration in minutes."},
    }},
    "workforce": {"description": "Employee and organization attributes for identification and breakdowns.", "fields": {
        "employee.employee_code": {"data_type": "STRING", "semantic_type": "identifier"},
        "department.name": {"data_type": "STRING", "semantic_type": "label"},
    }},
    "payroll": {"description": "Restricted payroll amounts and payroll-period identifiers.", "fields": {
        "payroll.net_amount": {"data_type": "DECIMAL", "semantic_type": "currency", "query_role": "measure", "default_aggregation": "SUM"},
        "payroll_period.code": {"data_type": "STRING", "semantic_type": "period_identifier", "description": "Payroll business period identifier; not a calendar DATE."},
    }},
    "sales": {"description": "Abstract sales capability for DSL expressiveness tests.", "fields": {
        "sales.sale_date": {"data_type": "DATE", "semantic_type": "calendar_date"},
        "sales.amount": {"data_type": "DECIMAL", "semantic_type": "currency", "query_role": "measure", "default_aggregation": "SUM"},
    }},
    "operations": {"description": "Abstract timestamped operations for DSL expressiveness tests.", "fields": {
        "operation.timestamp": {"data_type": "DATETIME", "semantic_type": "event_timestamp"},
        "operation.amount": {"data_type": "DECIMAL", "semantic_type": "currency", "query_role": "measure", "default_aggregation": "SUM"},
    }},
}
TYPE_CAPABILITIES = {
    "DATE": {"derivations": ["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY"], "calendar_predicates": ["IS_LAST_DAY_OF_MONTH"]},
    "DATETIME": {"derivations": ["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY", "TIME_OF_DAY"], "calendar_predicates": ["IS_LAST_DAY_OF_MONTH"]},
}

class Answerability(BaseModel):
    status: Literal["UNDERSTOOD_AND_EXECUTABLE", "NEEDS_CLARIFICATION", "UNSUPPORTED_QUERY"]
    reason: str | None = None
class ScopeSelection(BaseModel):
    capabilities: list[Literal["overtime", "workforce", "payroll", "sales", "operations"]] = Field(default_factory=list)
    answerability: Answerability
class Measure(BaseModel):
    field: str
    aggregation: Literal["SUM", "COUNT", "AVG", "MIN", "MAX"]
class ScalarFilter(BaseModel):
    field: str
    operator: Literal["EQ", "GT", "GTE", "LT", "LTE"]
    value: str | int | float
class SetFilter(BaseModel):
    field: str
    values: list[str | int | float] = Field(min_length=1)
class RangeFilter(BaseModel):
    field: str
    start_inclusive: str | None = None
    end_exclusive: str | None = None
class DerivedFilter(BaseModel):
    field: str
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY", "TIME_OF_DAY"]
    operator: Literal["EQ", "IN"]
    value: str | int | None = None
    values: list[str | int] = Field(default_factory=list)
class CalendarFilter(BaseModel):
    field: str
    predicate: Literal["IS_LAST_DAY_OF_MONTH"]
class RelativeBound(BaseModel):
    offset: int = 0
    unit: Literal["DAY", "MONTH", "YEAR"] = "DAY"
    snap: Literal["NONE", "START_OF_DAY", "START_OF_MONTH", "START_OF_YEAR"] = "NONE"
    add_days_after_snap: int = 0
class RelativeRangeFilter(BaseModel):
    field: str
    start: RelativeBound
    end_exclusive: RelativeBound
class Grouping(BaseModel):
    field: str
    derivation: Literal["YEAR", "YEAR_MONTH", "MONTH", "DAY_OF_MONTH", "QUARTER", "WEEK", "WEEKDAY", "TIME_OF_DAY"] | None = None
class Ordering(BaseModel):
    field: str
    direction: Literal["ASC", "DESC"] = "ASC"
class SemanticQueryDSLv23(BaseModel):
    goal: str
    projections: list[str] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    scalar_filters: list[ScalarFilter] = Field(default_factory=list)
    set_filters: list[SetFilter] = Field(default_factory=list)
    range_filters: list[RangeFilter] = Field(default_factory=list)
    derived_filters: list[DerivedFilter] = Field(default_factory=list)
    calendar_filters: list[CalendarFilter] = Field(default_factory=list)
    relative_range_filters: list[RelativeRangeFilter] = Field(default_factory=list)
    groupings: list[Grouping] = Field(default_factory=list)
    ordering: list[Ordering] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)
    answerability: Answerability

SCOPE_PROMPT = """Select only the conceptual capabilities required by the analytical request. Keep scope minimal. Payroll is a distinct restricted business capability and MUST NOT be selected merely because the user says 'period'. Do not infer fields, SQL, tables or joins. If ambiguity materially changes the result, use NEEDS_CLARIFICATION. If unavailable, use UNSUPPORTED_QUERY."""
DSL_PROMPT = """Translate the question into the provider-neutral Semantic Query DSL using ONLY the scoped conceptual fields. Never output entities, relationships, SQL, physical schema, provider syntax, or fields outside the scope.
projections are requested raw/detail fields; measures are analytical quantities and MUST follow query_role/default_aggregation metadata. Filter forms are structurally separate. range_filters are HALF-OPEN intervals: start_inclusive <= field < end_exclusive; they are NOT SQL BETWEEN. groupings are only for requested breakdowns ('by department', 'by month'). DATE/DATETIME derivations come from type capabilities. WEEKDAY values MUST be semantic names MONDAY..SUNDAY, never DBMS/locale numbers. Concrete calendar months/years should normally be half-open ranges. 'every Monday' is a derived WEEKDAY filter, not a grouping unless grouping is explicitly requested. Relative periods use RelativeRangeFilter bounds anchored to provider source_current_date; never materialize relative dates yourself. RelativeBound means: apply offset in unit to source date, then snap, then add_days_after_snap. For 'until today', an exclusive end is source date + 1 DAY. If multiple plausible meanings materially change results, NEEDS_CLARIFICATION; if capabilities cannot express it, UNSUPPORTED_QUERY. Keep output minimal."""

def scoped_catalog(capabilities: list[str]) -> dict[str, Any]:
    fields = {}
    for capability in capabilities:
        fields.update(CAPABILITIES.get(capability, {}).get("fields", {}))
    return {"provider_temporal_context": {"source_current_date": SOURCE_DATE.isoformat(), "source_timezone": SOURCE_TIMEZONE}, "type_capabilities": TYPE_CAPABILITIES, "fields": fields}

def refs(dsl: SemanticQueryDSLv23) -> list[str]:
    result = list(dsl.projections)
    for collection in (dsl.measures, dsl.scalar_filters, dsl.set_filters, dsl.range_filters, dsl.derived_filters, dsl.calendar_filters, dsl.relative_range_filters, dsl.groupings, dsl.ordering):
        result.extend(item.field for item in collection)
    return result

def derived_entities(dsl: SemanticQueryDSLv23) -> list[str]:
    return sorted({x.split('.', 1)[0] for x in refs(dsl) if '.' in x})

def days_in_month(year: int, month: int) -> int:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days

def add_months(value: date, amount: int) -> date:
    idx = value.year * 12 + value.month - 1 + amount
    year, month0 = divmod(idx, 12); month = month0 + 1
    return date(year, month, min(value.day, days_in_month(year, month)))

def add_years(value: date, amount: int) -> date:
    year = value.year + amount
    return date(year, value.month, min(value.day, days_in_month(year, value.month)))

def resolve_bound(bound: RelativeBound, source: date = SOURCE_DATE) -> date:
    value = source + timedelta(days=bound.offset) if bound.unit == "DAY" else add_months(source, bound.offset) if bound.unit == "MONTH" else add_years(source, bound.offset)
    if bound.snap == "START_OF_MONTH": value = date(value.year, value.month, 1)
    elif bound.snap == "START_OF_YEAR": value = date(value.year, 1, 1)
    return value + timedelta(days=bound.add_days_after_snap)

def normalize_relative(dsl: SemanticQueryDSLv23) -> list[dict[str, str]]:
    return [{"field": x.field, "start_inclusive": resolve_bound(x.start).isoformat(), "end_exclusive": resolve_bound(x.end_exclusive).isoformat()} for x in dsl.relative_range_filters]

def validate(scope: ScopeSelection, dsl: SemanticQueryDSLv23) -> dict[str, Any]:
    fields = scoped_catalog(scope.capabilities)["fields"]; references = refs(dsl)
    field_valid = all(x in fields for x in references); derivations_valid = True; weekday_valid = True; ranges_valid = True
    for x in [*dsl.derived_filters, *dsl.groupings]:
        if x.derivation:
            metadata = fields.get(x.field, {}); supported = TYPE_CAPABILITIES.get(metadata.get("data_type"), {}).get("derivations", [])
            derivations_valid &= x.derivation in supported
    for x in dsl.derived_filters:
        if x.derivation == "WEEKDAY":
            supplied = [x.value] if x.operator == "EQ" else x.values
            weekday_valid &= all(v in {"MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY","SUNDAY"} for v in supplied)
    for x in dsl.range_filters:
        ranges_valid &= bool(x.start_inclusive or x.end_exclusive)
        if x.start_inclusive and x.end_exclusive: ranges_valid &= x.start_inclusive < x.end_exclusive
    for x in normalize_relative(dsl): ranges_valid &= x["start_inclusive"] < x["end_exclusive"]
    return {"field_catalog_valid": field_valid, "derivations_valid": derivations_valid, "weekday_values_valid": weekday_valid, "ranges_valid": ranges_valid, "derived_entities": derived_entities(dsl), "payroll_contamination": "payroll" not in scope.capabilities and any(x.startswith("payroll") for x in references)}

def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def semantic_check(case: dict[str, Any], scope: ScopeSelection, dsl: SemanticQueryDSLv23, checks: dict[str, Any]) -> tuple[bool, str | None]:
    e = case["expected"]; expected_status = e.get("answerability", "UNDERSTOOD_AND_EXECUTABLE")
    if dsl.answerability.status != expected_status: return False, "ANSWERABILITY_MISMATCH"
    if expected_status != "UNDERSTOOD_AND_EXECUTABLE": return True, None
    if sorted(scope.capabilities) != sorted(e.get("capabilities", [])): return False, "CAPABILITY_SCOPE_MISMATCH"
    if not checks["field_catalog_valid"]: return False, "FIELD_OUTSIDE_SCOPED_CATALOG"
    if not checks["derivations_valid"]: return False, "UNSUPPORTED_DERIVATION"
    if not checks["weekday_values_valid"]: return False, "NON_SEMANTIC_WEEKDAY_VALUE"
    if not checks["ranges_valid"]: return False, "INVALID_HALF_OPEN_RANGE"
    if checks["payroll_contamination"]: return False, "PAYROLL_CONTAMINATION"
    actual_measures = sorted((x.field,x.aggregation) for x in dsl.measures); expected_measures = sorted((x["field"],x["aggregation"]) for x in e.get("measures",[]))
    if actual_measures != expected_measures: return False, "MEASURE_MISMATCH"
    if sorted(dsl.projections) != sorted(e.get("projections", [])): return False, "PROJECTION_MISMATCH"
    if sorted((x.field,x.derivation) for x in dsl.groupings) != sorted((x["field"],x.get("derivation")) for x in e.get("groupings",[])): return False, "GROUPING_MISMATCH"
    if sorted((x.field,x.start_inclusive,x.end_exclusive) for x in dsl.range_filters) != sorted((x["field"],x.get("start_inclusive"),x.get("end_exclusive")) for x in e.get("range_filters",[])): return False, "RANGE_FILTER_MISMATCH"
    if sorted((x.field,x.derivation,x.operator,str(x.value),tuple(map(str,x.values))) for x in dsl.derived_filters) != sorted((x["field"],x["derivation"],x["operator"],str(x.get("value")),tuple(map(str,x.get("values",[])))) for x in e.get("derived_filters",[])): return False, "DERIVED_FILTER_MISMATCH"
    if sorted((x.field,x.predicate) for x in dsl.calendar_filters) != sorted((x["field"],x["predicate"]) for x in e.get("calendar_filters",[])): return False, "CALENDAR_FILTER_MISMATCH"
    actual_relative = sorted((x["field"],x["start_inclusive"],x["end_exclusive"]) for x in normalize_relative(dsl)); expected_relative = sorted((x["field"],x["start_inclusive"],x["end_exclusive"]) for x in e.get("normalized_relative_ranges",[]))
    if actual_relative != expected_relative: return False, "RELATIVE_RANGE_MISMATCH"
    return True, None

def fingerprint(dsl: SemanticQueryDSLv23) -> str:
    payload = dsl.model_dump(mode="json"); payload["relative_range_filters"] = normalize_relative(dsl); payload.pop("goal", None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

def run(cases: list[dict[str, Any]], repetitions: int, output: Path, model_name: str) -> None:
    model = OpenAIStructuredModel(api_key=os.environ.get("OPENAI_API_KEY"), model=model_name, timeout_seconds=60, max_retries=0, max_output_tokens=4096)
    output.mkdir(parents=True, exist_ok=False); rows = []
    for case in cases:
        for repetition in range(1,repetitions+1):
            started=time.monotonic(); row={"attempt_id":str(uuid.uuid4()),"question_id":case["id"],"question":case["question"],"repetition":repetition,"model":model.model_name}
            try:
                scope=model.parse(purpose=SCOPE_PROMPT,instructions="Capabilities: "+json.dumps({k:v["description"] for k,v in CAPABILITIES.items()},ensure_ascii=False)+"\nQuestion: "+case["question"],output_model=ScopeSelection); assert isinstance(scope,ScopeSelection)
                if scope.answerability.status == "UNDERSTOOD_AND_EXECUTABLE":
                    catalog=scoped_catalog(scope.capabilities); parsed=model.parse(purpose=DSL_PROMPT,instructions="Provider temporal context: "+json.dumps(catalog["provider_temporal_context"])+"\nType capabilities: "+json.dumps(catalog["type_capabilities"])+"\nScoped conceptual fields: "+json.dumps(catalog["fields"],ensure_ascii=False)+"\nQuestion: "+case["question"],output_model=SemanticQueryDSLv23); assert isinstance(parsed,SemanticQueryDSLv23)
                else: parsed=SemanticQueryDSLv23(goal="",answerability=scope.answerability)
                checks=validate(scope,parsed); ok,failure=semantic_check(case,scope,parsed,checks); row.update({"structured_output_success":True,"scope":scope.model_dump(mode="json"),"scoped_fields":sorted(scoped_catalog(scope.capabilities)["fields"]),"raw_dsl":parsed.model_dump(mode="json"),"normalized_relative_ranges":normalize_relative(parsed),"validation":checks,"semantic_success":ok,"first_failure":failure,"semantic_fingerprint":fingerprint(parsed),"response_diagnostics":model.last_response_diagnostics})
            except Exception as exc: row.update({"structured_output_success":False,"semantic_success":False,"first_failure":model.last_failure_class or "MODEL_FAILURE","exception_class":type(exc).__name__,"error":str(exc)[:240],"response_diagnostics":model.last_response_diagnostics})
            row["latency_ms"]=round((time.monotonic()-started)*1000,1); rows.append(row); print(json.dumps({k:row.get(k) for k in ("question_id","repetition","structured_output_success","semantic_success","first_failure","latency_ms")},ensure_ascii=False),flush=True)
    (output/"raw_responses.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in rows)+"\n",encoding="utf-8")
    failures=Counter(x.get("first_failure") for x in rows if x.get("first_failure")); by_case={}
    for x in rows:
        if x.get("semantic_fingerprint"): by_case.setdefault(x["question_id"],Counter())[x["semantic_fingerprint"]]+=1
    consistency={k:max(v.values())/sum(v.values()) for k,v in by_case.items()}; metrics={"total":len(rows),"structured_output_success_rate":sum(bool(x.get("structured_output_success")) for x in rows)/len(rows),"semantic_success_rate":sum(bool(x.get("semantic_success")) for x in rows)/len(rows),"failure_distribution":dict(failures),"semantic_fingerprint_consistency":consistency,"average_fingerprint_consistency":sum(consistency.values())/len(consistency) if consistency else None}
    (output/"metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); (output/"manifest.json").write_text(json.dumps({"created_at":datetime.utcnow().isoformat()+"Z","phase":"2.3","model":model.model_name,"source_current_date":SOURCE_DATE.isoformat(),"source_timezone":SOURCE_TIMEZONE,"retries":0,"cases":len(cases),"repetitions":repetitions,"production_mcp_executed":False,"production_contract_changed":False},indent=2)+"\n",encoding="utf-8")

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--cases",type=Path,default=ROOT/"evaluation/spikes/semantic_query_dsl_phase23_cases.jsonl"); p.add_argument("--repetitions",type=int,default=1); p.add_argument("--output",type=Path,required=True); p.add_argument("--model",default=os.environ.get("OPENAI_MODEL","gpt-4o-mini")); a=p.parse_args(); run(load_cases(a.cases),a.repetitions,a.output,a.model)
if __name__ == "__main__": main()
