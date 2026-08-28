"""Promote one completed synthetic Policy RAG run to curated public evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


REQUIRED = ("manifest.json", "dataset.jsonl", "metrics.json", "report.md")
OPTIONAL = ("predictions.jsonl", "evidence.jsonl", "metrics_judged.json", "predictions_judged.jsonl")


def publish(run_dir: Path, baselines_dir: Path, name: str) -> Path:
    destination = baselines_dir / name
    if destination.exists():
        raise SystemExit(f"refusing to overwrite existing curated baseline: {destination}")
    missing = [item for item in REQUIRED if not (run_dir / item).is_file()]
    if missing:
        raise SystemExit(f"run is incomplete; missing artifacts: {', '.join(missing)}")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("execution") != "real_peopleops_api":
        raise SystemExit("refusing to publish a run not executed against the real PeopleOps API")
    predictions = [
        json.loads(line)
        for line in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not predictions or not all(item.get("synthetic_corpus") is True for item in predictions):
        raise SystemExit("refusing to publish a run without synthetic_corpus=true on every prediction")
    if len(predictions) != manifest.get("dataset_case_count"):
        raise SystemExit("refusing to publish an incomplete prediction set")
    destination.mkdir(parents=True)
    for filename in (*REQUIRED, *OPTIONAL):
        source = run_dir / filename
        if source.is_file():
            shutil.copy2(source, destination / filename)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--baseline-name", required=True)
    parser.add_argument("--baselines-dir", type=Path, default=Path("evaluation/baselines/policy-rag"))
    args = parser.parse_args()
    destination = publish(args.run_dir, args.baselines_dir, args.baseline_name)
    print(f"Published curated baseline at {destination}")


if __name__ == "__main__":
    main()
