"""Run the clarification-to-SQLAlchemy experimental pipeline."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from peopleops_api.analysis_workflow import (
    OpenAIStructuredModel,
    _openai_strict_schema,
    _response_output_text,
)

import direct_sqlalchemy_phase41 as phase41
import direct_sqlalchemy_phase412 as phase412


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _validate(response: phase41.SQLAlchemyGenerationResponse) -> tuple[Any, list[str], str | None]:
    if response.status == "NEEDS_INFO":
        return None, [], None
    errors = phase41.validate_python_expression(response.sqlalchemy or "")
    if errors:
        return None, errors, None
    statement, build_errors = phase41.build_statement(response.sqlalchemy or "")
    if statement is None or build_errors:
        return statement, build_errors, None
    sql, compile_errors = phase41.compile_postgresql(statement)
    return statement, compile_errors, sql


def assert_runner_contract() -> None:
    phase412.assert_phase412_contract()
    cases = _load_cases(Path(__file__).with_name("direct_sqlalchemy_phase412_cases.jsonl"))
    assert len(cases) == 24
    assert len({case["id"] for case in cases}) == 24


def _parse_generator(
    *, client: Any, model: str, instructions: str, input_payload: dict[str, object]
) -> phase41.SQLAlchemyGenerationResponse:
    from openai import OpenAI

    if not isinstance(client, OpenAI):
        raise TypeError("client must be an OpenAI client")
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=[
            {
                "role": "user",
                "content": json.dumps(input_payload, ensure_ascii=False),
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": phase41.SQLAlchemyGenerationResponse.__name__,
                "strict": True,
                "schema": _openai_strict_schema(
                    phase41.SQLAlchemyGenerationResponse.model_json_schema()
                ),
            }
        },
        max_output_tokens=4096,
    )
    return phase41.SQLAlchemyGenerationResponse.model_validate_json(
        _response_output_text(response)
    )


def run(cases_path: Path, output_dir: Path, model: str, repetitions: int) -> None:
    assert_runner_contract()
    cases = _load_cases(cases_path)
    assert len(cases) == 24
    output_dir.mkdir(parents=True, exist_ok=True)
    llm = OpenAIStructuredModel(
        api_key=os.environ["OPENAI_API_KEY"], model=model, max_retries=0
    )
    from openai import OpenAI

    generator_client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"], timeout=30.0, max_retries=0
    )
    rows: list[dict[str, Any]] = []
    errors = Counter()
    for repetition in range(1, repetitions + 1):
        for case in cases:
            started = time.perf_counter()
            clarifier_prompt = (
                f"{phase412.CLARIFIER_PROMPT}\n\nUser request:\n{case['question']}"
            )
            clarification = llm.parse(
                purpose="phase412-english-semantic-clarification",
                instructions=clarifier_prompt,
                output_model=phase412.ClarificationResponse,
            )
            generator_prompt = phase412.generator_prompt(
                question=case["question"], clarification=clarification
            )
            generator_input = phase412.generator_input(clarification)
            generated = _parse_generator(
                client=generator_client,
                model=model,
                instructions=generator_prompt,
                input_payload=generator_input,
            )
            statement, validation_errors, compiled_sql = _validate(generated)
            errors.update(validation_errors)
            acceptable = generated.status in case["accepted_outcomes"]
            if (
                generated.status == "QUERY"
                and case.get("query_requires_declared_assumption")
                and not generated.assumptions
            ):
                acceptable = False
            response_json = generated.model_dump(mode="json")
            response_json["input_request"] = generator_input
            rows.append(
                {
                    "id": case["id"],
                    "language": "es",
                    "category": case.get("category"),
                    "repetition": repetition,
                    "question": case["question"],
                    "clarifier_prompt": clarifier_prompt,
                    "clarification": clarification.model_dump(mode="json"),
                    "generator_prompt": generator_prompt,
                    "generator_input": generator_input,
                    "response": response_json,
                    "outcome_acceptable": acceptable,
                    "validation_errors": validation_errors,
                    "statement_built": statement is not None,
                    "compiled_sql": compiled_sql,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
    query_rows = [row for row in rows if row["response"]["status"] == "QUERY"]
    compiled_rows = [row for row in query_rows if row["compiled_sql"]]
    metrics = {
        "runner_version": "direct-sqlalchemy-phase412-v1",
        "cases": len(cases),
        "repetitions": repetitions,
        "executions": len(rows),
        "clarifier_calls": len(rows),
        "generator_calls": len(rows),
        "structured_output_success": len(rows),
        "query_outputs": len(query_rows),
        "needs_info_outputs": len(rows) - len(query_rows),
        "outcome_acceptable": sum(row["outcome_acceptable"] for row in rows),
        "statement_built": sum(row["statement_built"] for row in rows),
        "postgresql_compiled": len(compiled_rows),
        "validation_error_counts": dict(errors),
    }
    manifest = {
        "runner_version": "direct-sqlalchemy-phase412-v1",
        "model": model,
        "cases": len(cases),
        "repetitions": repetitions,
        "source_date": "2026-08-30",
        "timezone": "UTC",
        "retries": 0,
        "pipeline": "question -> English clarifier -> SQLAlchemy generator",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output_dir / "raw_responses.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()
    run(args.cases, args.output_dir, args.model, args.repetitions)


if __name__ == "__main__":
    main()
