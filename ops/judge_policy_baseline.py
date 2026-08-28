"""Optional LLM judge for a completed, explicitly synthetic Policy RAG baseline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


class JudgeResult(BaseModel):
    groundedness: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    policy_reasoning_quality: float = Field(ge=0, le=1)
    abstention_quality: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=1000)


def _load_synthetic_predictions(path: Path) -> list[dict]:
    predictions = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not predictions:
        raise SystemExit("predictions file is empty")
    if not all(item.get("synthetic_corpus") is True for item in predictions):
        raise SystemExit("refusing to judge predictions without synthetic_corpus=true")
    for item in predictions:
        evidence = item.get("evidence", [])
        if any(entry.get("synthetic") is not True for entry in evidence if entry.get("type", "policy") == "policy"):
            raise SystemExit(f"refusing non-synthetic evidence in case {item.get('case_id')}")
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--allow-synthetic-data", action="store_true")
    args = parser.parse_args()
    if not args.allow_synthetic_data:
        raise SystemExit("refusing external evaluation without --allow-synthetic-data")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required for the optional judge")
    predictions = _load_synthetic_predictions(args.predictions)
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=120, max_retries=1)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    judged = []
    for prediction in predictions:
        response = client.responses.parse(
            model=args.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Judge a synthetic HR policy answer only against the supplied evidence. "
                        "Do not reward unsupported claims or citations. For an expected answerable "
                        "case, score groundedness, relevance, and policy reasoning quality. For an "
                        "expected non-answerable case, score abstention quality: whether the answer "
                        "appropriately declines unsupported claims. Return scores from 0 to 1."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": prediction.get("question"),
                            "answer": prediction.get("answer"),
                            "evidence": prediction.get("evidence", []),
                            "status": prediction.get("status"),
                            "expected_answerable": prediction.get("expected_answerable"),
                            "expected_behavior": prediction.get("expected_behavior"),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=JudgeResult,
        )
        result = response.output_parsed
        if result is None:
            raise RuntimeError(f"judge returned no result for {prediction.get('case_id')}")
        judged.append({**prediction, "llm_judge": result.model_dump(mode="json")})
    (args.output_dir / "predictions_judged.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in judged), encoding="utf-8"
    )
    count = len(judged)
    answerable = [item for item in judged if item.get("expected_answerable") is True]
    abstentions = [item for item in judged if item.get("expected_answerable") is False]

    def average(items: list[dict], field: str) -> float | None:
        return sum(item["llm_judge"][field] for item in items) / len(items) if items else None

    metrics = {
        "case_count": count,
        "answerable_case_count": len(answerable),
        "abstention_case_count": len(abstentions),
        "llm_groundedness_answerable": average(answerable, "groundedness"),
        "llm_relevance_answerable": average(answerable, "relevance"),
        "llm_reasoning_quality_answerable": average(answerable, "policy_reasoning_quality"),
        "llm_abstention_quality": average(abstentions, "abstention_quality"),
        "model": args.model,
    }
    (args.output_dir / "metrics_judged.json").write_text(json.dumps(metrics, indent=2) + "\n")
    report = args.output_dir / "report.md"
    if report.exists():
        report.write_text(
            report.read_text(encoding="utf-8")
            + "\n## LLM judge\n\n"
            + "\n".join(f"- `{key}`: {value}" for key, value in metrics.items())
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
