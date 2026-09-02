"""Run Phase 4.0 Direct Conceptual Eloquent Translation PoC.

Gate A:
    natural language -> direct conceptual Eloquent text / NEEDS_INFO
Gate B (optional):
    conceptual Eloquent -> PostgreSQL using provider-owned physical model mapping
Gate C (optional):
    validate and execute read-only SQL against the synthetic reference HRIS

The first LLM call never sees physical table/column names. The second call is a
stand-in for the future MCP/provider translation boundary and receives the full
physical model mapping.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from peopleops_api.analysis_workflow import OpenAIStructuredModel

import direct_conceptual_eloquent_phase40 as phase40

RUNNER_VERSION = "direct-conceptual-eloquent-phase40-v1"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _percent(num: int, den: int) -> float | None:
    return None if den == 0 else round(num * 100.0 / den, 2)


def _known_models() -> set[str]:
    return {model.name for model in phase40.MODELS}


def _physical_tables() -> set[str]:
    return {model.physical_table for model in phase40.MODELS}


def _resolve_reference(root_model: str, reference: str) -> bool:
    """Validate a logical attribute or relationship path against model metadata."""
    models = {model.name: model for model in phase40.MODELS}
    current = models[root_model]
    parts = reference.split(".")
    for index, part in enumerate(parts):
        attribute_names = {item.name for item in current.attributes}
        if part in attribute_names:
            return index == len(parts) - 1
        relation = next((item for item in current.relationships if item.name == part), None)
        if relation is None:
            return False
        current = models[relation.related_model]
    return False


def validate_conceptual_eloquent(response: phase40.ConceptualEloquentResponse) -> list[str]:
    """Validate the allowed conceptual Eloquent surface without interpreting semantics."""
    if response.status == "NEEDS_INFO":
        return []
    query = response.eloquent_query or ""
    errors: list[str] = []
    lower = query.lower()

    for forbidden in phase40.FORBIDDEN_METHODS:
        if forbidden.lower() in lower:
            errors.append(f"FORBIDDEN_CONSTRUCT:{forbidden}")

    for physical in _physical_tables():
        if re.search(rf"\b{re.escape(physical)}\b", query, flags=re.IGNORECASE):
            errors.append(f"PHYSICAL_NAME_LEAK:{physical}")

    model_matches = re.findall(r"\b([A-Z][A-Za-z0-9_]*)::query\(\)", query)
    if not model_matches:
        errors.append("NO_MODEL_QUERY")
        return errors
    unknown_models = sorted(set(model_matches) - _known_models())
    errors.extend(f"UNKNOWN_MODEL:{name}" for name in unknown_models)

    methods = re.findall(r"->([A-Za-z_][A-Za-z0-9_]*)\s*\(", query)
    allowed_methods = set(phase40.ALLOWED_METHODS) - {"query"}
    for method in methods:
        if method not in allowed_methods:
            errors.append(f"UNKNOWN_METHOD:{method}")

    # Validate quoted references supplied to common field-taking methods. This
    # is deliberately a surface validator, not a second semantic compiler.
    field_method_pattern = re.compile(
        r"->(select|where|whereBetween|whereIn|whereYear|whereMonth|whereDay|"
        r"whereWeekday|whereLastDayOfMonth|whereFirstDayOfMonth|groupBy|"
        r"groupByMonth|orderBy|sum|avg|min|max)\s*\(\s*['\"]([^'\"]+)['\"]"
    )
    root_model = model_matches[0]
    for method, reference in field_method_pattern.findall(query):
        if not _resolve_reference(root_model, reference):
            errors.append(f"UNKNOWN_REFERENCE:{method}:{reference}")

    return sorted(set(errors))


def validate_read_only_sql(sql: str) -> list[str]:
    """PoC safety gate before optional execution; not a production SQL parser."""
    stripped = sql.strip()
    compact = re.sub(r"\s+", " ", stripped.lower())
    normalized = f" {compact} "
    errors: list[str] = []
    if not (compact.startswith("select ") or compact.startswith("with ")):
        errors.append("SQL_NOT_SELECT")
    if ";" in stripped or "--" in stripped or "/*" in stripped or "*/" in stripped:
        errors.append("SQL_MULTISTATEMENT_OR_COMMENT")
    forbidden = (
        " insert ",
        " update ",
        " delete ",
        " drop ",
        " alter ",
        " truncate ",
        " copy ",
        " create ",
        " grant ",
        " revoke ",
        " for update ",
        " pg_sleep",
    )
    for token in forbidden:
        if token in normalized:
            errors.append(f"SQL_FORBIDDEN:{token.strip()}")

    allowed_tables = _physical_tables()
    referenced_tables = re.findall(
        r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", stripped, flags=re.IGNORECASE
    )
    for table in referenced_tables:
        if table not in allowed_tables:
            errors.append(f"SQL_UNKNOWN_TABLE:{table}")
    if not referenced_tables:
        errors.append("SQL_NO_MAPPED_TABLE")
    return sorted(set(errors))


def _execute_sql(sql: str, *, max_rows: int = 100) -> dict[str, Any]:
    """Execute validated SQL in a read-only transaction against synthetic HRIS."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - environment dependent
        return {"executed": False, "error": f"PSYCOPG_UNAVAILABLE:{exc}"}

    required = (
        "SYNTHETIC_HRIS_DATABASE_HOST",
        "SYNTHETIC_HRIS_DATABASE_PORT",
        "SYNTHETIC_HRIS_DATABASE_NAME",
        "SYNTHETIC_HRIS_DATABASE_USER",
        "SYNTHETIC_HRIS_DATABASE_PASSWORD",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        return {"executed": False, "error": f"MISSING_DB_ENV:{','.join(missing)}"}

    started = time.perf_counter()
    try:
        with psycopg.connect(
            host=os.environ["SYNTHETIC_HRIS_DATABASE_HOST"],
            port=int(os.environ["SYNTHETIC_HRIS_DATABASE_PORT"]),
            dbname=os.environ["SYNTHETIC_HRIS_DATABASE_NAME"],
            user=os.environ["SYNTHETIC_HRIS_DATABASE_USER"],
            password=os.environ["SYNTHETIC_HRIS_DATABASE_PASSWORD"],
            autocommit=False,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '5000ms'")
                cursor.execute(sql)
                columns = [item.name for item in cursor.description] if cursor.description else []
                values = cursor.fetchmany(max_rows + 1)
                truncated = len(values) > max_rows
                values = values[:max_rows]
                connection.rollback()
        return {
            "executed": True,
            "columns": columns,
            "row_count_sample": len(values),
            "truncated": truncated,
            "sample": [list(row) for row in values[:10]],
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001 - experiment must persist provider error
        return {
            "executed": False,
            "error": f"{type(exc).__name__}:{exc}",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }


def assert_runner_contract() -> None:
    valid = phase40.ConceptualEloquentResponse(
        status="QUERY",
        eloquent_query=(
            "Overtime::query()->where('work_date', '>=', '2026-01-01')"
            "->where('work_date', '<', '2026-02-01')->sum('approved_minutes')"
        ),
    )
    assert validate_conceptual_eloquent(valid) == []

    leak = phase40.ConceptualEloquentResponse(
        status="QUERY",
        eloquent_query="Overtime::query()->where('overtime_record.work_date', '>=', '2026-01-01')->get()",
    )
    assert any(item.startswith("PHYSICAL_NAME_LEAK") for item in validate_conceptual_eloquent(leak))

    unsafe_sql = "DELETE FROM overtime_record"
    assert "SQL_NOT_SELECT" in validate_read_only_sql(unsafe_sql)
    assert any(item.startswith("SQL_FORBIDDEN") for item in validate_read_only_sql(unsafe_sql))

    safe_sql = "SELECT approved_minutes FROM overtime_record WHERE work_date >= DATE '2026-01-01'"
    assert validate_read_only_sql(safe_sql) == []


def run(
    cases_path: Path,
    output_dir: Path,
    model: str,
    repetitions: int,
    *,
    translate_sql: bool,
    execute_sql: bool,
) -> None:
    phase40.assert_phase40_contract()
    assert_runner_contract()
    cases = _load_cases(cases_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    llm = OpenAIStructuredModel(
        api_key=os.environ["OPENAI_API_KEY"],
        model=model,
        max_retries=0,
    )

    rows: list[dict[str, Any]] = []
    by_case: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "executions": 0,
            "status_correct": 0,
            "eloquent_surface_valid": 0,
            "sql_translated": 0,
            "sql_safe": 0,
            "sql_executed": 0,
        }
    )
    validation_errors = Counter()
    sql_validation_errors = Counter()

    for repetition in range(1, repetitions + 1):
        for case in cases:
            started = time.perf_counter()
            instructions = (
                f"{phase40.ELOQUENT_GENERATION_PROMPT}\n\n"
                f"User request:\n{case['question']}"
            )
            response = llm.parse(
                purpose="phase40-direct-conceptual-eloquent",
                instructions=instructions,
                output_model=phase40.ConceptualEloquentResponse,
            )
            eloquent_errors = validate_conceptual_eloquent(response)
            status_correct = response.status == case["expected_status"]

            translation: phase40.SQLTranslationResponse | None = None
            sql_errors: list[str] = []
            execution: dict[str, Any] | None = None
            if translate_sql and response.status == "QUERY" and not eloquent_errors:
                translator_instructions = (
                    f"{phase40.SQL_TRANSLATION_PROMPT}\n\n"
                    f"Conceptual Eloquent query:\n{response.eloquent_query}"
                )
                translation = llm.parse(
                    purpose="phase40-provider-postgresql-translation",
                    instructions=translator_instructions,
                    output_model=phase40.SQLTranslationResponse,
                )
                if translation.status == "SQL" and translation.sql:
                    sql_errors = validate_read_only_sql(translation.sql)
                    if execute_sql and not sql_errors:
                        execution = _execute_sql(translation.sql)

            summary = by_case[str(case["id"])]
            summary["executions"] += 1
            summary["status_correct"] += int(status_correct)
            summary["eloquent_surface_valid"] += int(
                response.status == "NEEDS_INFO" or not eloquent_errors
            )
            summary["sql_translated"] += int(
                translation is not None and translation.status == "SQL"
            )
            summary["sql_safe"] += int(
                translation is not None
                and translation.status == "SQL"
                and not sql_errors
            )
            summary["sql_executed"] += int(bool(execution and execution.get("executed")))
            validation_errors.update(eloquent_errors)
            sql_validation_errors.update(sql_errors)

            rows.append(
                {
                    "id": case["id"],
                    "language": case.get("language"),
                    "category": case.get("category"),
                    "repetition": repetition,
                    "question": case["question"],
                    "expected_status": case["expected_status"],
                    "response": response.model_dump(mode="json"),
                    "status_correct": status_correct,
                    "eloquent_validation_errors": eloquent_errors,
                    "eloquent_surface_valid": response.status == "NEEDS_INFO"
                    or not eloquent_errors,
                    "translation": (
                        None if translation is None else translation.model_dump(mode="json")
                    ),
                    "sql_validation_errors": sql_errors,
                    "execution": execution,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )

    total = len(rows)
    query_rows = [row for row in rows if row["response"]["status"] == "QUERY"]
    translated_rows = [row for row in rows if row["translation"] is not None]
    execution_rows = [row for row in rows if row["execution"] is not None]
    status_correct_count = sum(row["status_correct"] for row in rows)
    eloquent_valid_count = sum(row["eloquent_surface_valid"] for row in rows)
    metrics = {
        "runner_version": RUNNER_VERSION,
        "cases": len(cases),
        "repetitions": repetitions,
        "executions": total,
        "structured_output_success": total,
        "status_correct": status_correct_count,
        "status_correct_pct": _percent(status_correct_count, total),
        "query_outputs": len(query_rows),
        "eloquent_surface_valid": eloquent_valid_count,
        "eloquent_surface_valid_pct": _percent(eloquent_valid_count, total),
        "eloquent_validation_error_counts": dict(validation_errors),
        "sql_translation_attempts": len(translated_rows),
        "sql_translated": sum(
            row["translation"] is not None and row["translation"]["status"] == "SQL"
            for row in rows
        ),
        "sql_safe": sum(
            row["translation"] is not None
            and row["translation"]["status"] == "SQL"
            and not row["sql_validation_errors"]
            for row in rows
        ),
        "sql_validation_error_counts": dict(sql_validation_errors),
        "sql_execution_attempts": len(execution_rows),
        "sql_executed": sum(
            bool(row["execution"] and row["execution"].get("executed")) for row in rows
        ),
        "by_case": dict(sorted(by_case.items())),
    }
    manifest = {
        "phase": "4.0-direct-conceptual-eloquent",
        "runner_version": RUNNER_VERSION,
        "cases": len(cases),
        "repetitions": repetitions,
        "expected_executions": len(cases) * repetitions,
        "actual_executions": total,
        "model": model,
        "source_date": "2026-08-30",
        "timezone": "UTC",
        "max_retries": 0,
        "physical_mapping_exposed_to_first_llm": False,
        "translate_sql": translate_sql,
        "execute_sql": execute_sql,
        "query_representation": "direct conceptual Eloquent text",
    }

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--translate-sql", action="store_true")
    parser.add_argument("--execute-sql", action="store_true")
    args = parser.parse_args()
    if args.execute_sql and not args.translate_sql:
        parser.error("--execute-sql requires --translate-sql")
    run(
        args.cases,
        args.output_dir,
        args.model,
        args.repetitions,
        translate_sql=args.translate_sql,
        execute_sql=args.execute_sql,
    )


if __name__ == "__main__":
    main()
