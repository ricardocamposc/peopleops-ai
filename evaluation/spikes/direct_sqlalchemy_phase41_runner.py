"""Run Phase 4.1 Direct SQLAlchemy 2.x query-generation PoC."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from peopleops_api.analysis_workflow import OpenAIStructuredModel
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

import direct_sqlalchemy_phase41 as phase41

RUNNER_VERSION = "direct-sqlalchemy-phase41-v1"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _percent(num: int, den: int) -> float | None:
    return None if den == 0 else round(num * 100.0 / den, 2)


def _outcome_acceptable(case: dict[str, Any], response: phase41.SQLAlchemyGenerationResponse) -> bool:
    if response.status not in case["accepted_outcomes"]:
        return False
    if (
        response.status == "QUERY"
        and case.get("query_requires_declared_assumption")
        and not response.assumptions
    ):
        return False
    return True


def _db_env_present() -> tuple[bool, list[str]]:
    required = (
        "SYNTHETIC_HRIS_DATABASE_HOST",
        "SYNTHETIC_HRIS_DATABASE_PORT",
        "SYNTHETIC_HRIS_DATABASE_NAME",
        "SYNTHETIC_HRIS_DATABASE_USER",
        "SYNTHETIC_HRIS_DATABASE_PASSWORD",
    )
    missing = [name for name in required if not os.getenv(name)]
    return not missing, missing


def _execute_read_only(statement: Any, *, max_rows: int = 100) -> dict[str, Any]:
    available, missing = _db_env_present()
    if not available:
        return {"executed": False, "error": f"MISSING_DB_ENV:{','.join(missing)}"}

    url = URL.create(
        "postgresql+psycopg",
        username=os.environ["SYNTHETIC_HRIS_DATABASE_USER"],
        password=os.environ["SYNTHETIC_HRIS_DATABASE_PASSWORD"],
        host=os.environ["SYNTHETIC_HRIS_DATABASE_HOST"],
        port=int(os.environ["SYNTHETIC_HRIS_DATABASE_PORT"]),
        database=os.environ["SYNTHETIC_HRIS_DATABASE_NAME"],
    )
    started = time.perf_counter()
    try:
        engine = create_engine(url, future=True, pool_pre_ping=True)
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
                result = connection.execute(statement)
                rows = result.fetchmany(max_rows + 1)
                columns = list(result.keys())
                truncated = len(rows) > max_rows
                rows = rows[:max_rows]
            finally:
                transaction.rollback()
        engine.dispose()
        return {
            "executed": True,
            "columns": columns,
            "row_count_sample": len(rows),
            "truncated": truncated,
            "sample": [list(row) for row in rows[:10]],
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001 - persist provider failure in experiment
        return {
            "executed": False,
            "error": f"{type(exc).__name__}:{exc}",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }


def assert_runner_contract() -> None:
    phase41.assert_phase41_contract()
    cases = _load_cases(Path(__file__).with_name("direct_sqlalchemy_phase41_cases.jsonl"))
    assert len(cases) == 24
    assert len({case["id"] for case in cases}) == 24
    ambiguous = next(case for case in cases if case["id"] == "P41-17")
    assert ambiguous["accepted_outcomes"] == ["QUERY", "NEEDS_INFO"]

    query_with_assumption = phase41.SQLAlchemyGenerationResponse(
        status="QUERY",
        sqlalchemy="select(Overtime)",
        interpretation="Assume previous period means previous month.",
        assumptions=["previous period = previous calendar month"],
    )
    assert _outcome_acceptable(ambiguous, query_with_assumption)

    query_without_assumption = query_with_assumption.model_copy(update={"assumptions": []})
    assert not _outcome_acceptable(ambiguous, query_without_assumption)


def run(
    cases_path: Path,
    output_dir: Path,
    model: str,
    repetitions: int,
    *,
    execute: bool,
) -> None:
    assert_runner_contract()
    cases = _load_cases(cases_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    llm = OpenAIStructuredModel(
        api_key=os.environ["OPENAI_API_KEY"],
        model=model,
        max_retries=0,
    )

    rows: list[dict[str, Any]] = []
    error_counts = Counter()
    by_case: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "executions": 0,
            "outcome_acceptable": 0,
            "python_valid": 0,
            "statement_built": 0,
            "postgresql_compiled": 0,
            "executed": 0,
        }
    )

    for repetition in range(1, repetitions + 1):
        for case in cases:
            started = time.perf_counter()
            response = llm.parse(
                purpose="phase41-direct-sqlalchemy-query-generation",
                instructions=f"{phase41.GENERATION_PROMPT}\n\nUser request:\n{case['question']}",
                output_model=phase41.SQLAlchemyGenerationResponse,
            )
            acceptable = _outcome_acceptable(case, response)
            source = response.sqlalchemy or ""
            syntax_errors = (
                [] if response.status == "NEEDS_INFO" else phase41.validate_python_expression(source)
            )
            statement = None
            build_errors: list[str] = []
            compile_errors: list[str] = []
            compiled_sql = None
            execution = None
            if response.status == "QUERY" and not syntax_errors:
                statement, build_errors = phase41.build_statement(source)
                if statement is not None and not build_errors:
                    compiled_sql, compile_errors = phase41.compile_postgresql(statement)
                    if execute and compiled_sql is not None and not compile_errors:
                        execution = _execute_read_only(statement)

            all_errors = syntax_errors + build_errors + compile_errors
            error_counts.update(all_errors)
            summary = by_case[str(case["id"])]
            summary["executions"] += 1
            summary["outcome_acceptable"] += int(acceptable)
            summary["python_valid"] += int(response.status == "NEEDS_INFO" or not syntax_errors)
            summary["statement_built"] += int(response.status == "NEEDS_INFO" or statement is not None)
            summary["postgresql_compiled"] += int(
                response.status == "NEEDS_INFO" or compiled_sql is not None
            )
            summary["executed"] += int(bool(execution and execution.get("executed")))

            rows.append(
                {
                    "id": case["id"],
                    "language": case.get("language"),
                    "category": case.get("category"),
                    "repetition": repetition,
                    "question": case["question"],
                    "accepted_outcomes": case["accepted_outcomes"],
                    "response": response.model_dump(mode="json"),
                    "outcome_acceptable": acceptable,
                    "validation_errors": all_errors,
                    "statement_built": statement is not None,
                    "compiled_sql": compiled_sql,
                    "execution": execution,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )

    total = len(rows)
    query_rows = [row for row in rows if row["response"]["status"] == "QUERY"]
    needs_info_rows = [row for row in rows if row["response"]["status"] == "NEEDS_INFO"]
    built_rows = [row for row in query_rows if row["statement_built"]]
    compiled_rows = [row for row in query_rows if row["compiled_sql"] is not None]
    acceptable_count = sum(row["outcome_acceptable"] for row in rows)
    metrics = {
        "runner_version": RUNNER_VERSION,
        "cases": len(cases),
        "repetitions": repetitions,
        "executions": total,
        "structured_output_success": total,
        "query_outputs": len(query_rows),
        "needs_info_outputs": len(needs_info_rows),
        "outcome_acceptable": acceptable_count,
        "outcome_acceptable_pct": _percent(acceptable_count, total),
        "statement_built": len(built_rows),
        "statement_built_pct_of_queries": _percent(len(built_rows), len(query_rows)),
        "postgresql_compiled": len(compiled_rows),
        "postgresql_compiled_pct_of_queries": _percent(len(compiled_rows), len(query_rows)),
        "validation_error_counts": dict(error_counts),
        "db_execution_requested": execute,
        "db_env_present": _db_env_present()[0],
        "executed": sum(bool(row["execution"] and row["execution"].get("executed")) for row in rows),
        "by_case": dict(sorted(by_case.items())),
    }
    manifest = {
        "runner_version": RUNNER_VERSION,
        "model": model,
        "cases": len(cases),
        "repetitions": repetitions,
        "expected_executions": len(cases) * repetitions,
        "source_date": "2026-08-30",
        "timezone": "UTC",
        "retries": 0,
        "execute": execute,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    run(args.cases, args.output_dir, args.model, args.repetitions, execute=args.execute)


if __name__ == "__main__":
    main()
