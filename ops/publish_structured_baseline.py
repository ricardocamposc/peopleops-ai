"""Promote a complete synthetic structured-HR run without overwriting evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REQUIRED = ("manifest.json", "dataset.jsonl", "predictions.jsonl", "evidence.jsonl", "metrics.json", "report.md")


def publish(run_dir: Path, destination: Path) -> None:
    if destination.exists():
        raise SystemExit(f"refusing to overwrite existing baseline: {destination}")
    missing = [name for name in REQUIRED if not (run_dir / name).is_file()]
    if missing:
        raise SystemExit(f"run is incomplete: missing {', '.join(missing)}")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("execution") != "real_peopleops_mcp_hris":
        raise SystemExit("run was not executed against the real PeopleOps MCP/HRIS path")
    predictions = [
        json.loads(line)
        for line in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(predictions) != manifest.get("dataset_case_count"):
        raise SystemExit("prediction count does not match dataset case count")
    destination.mkdir(parents=True)
    for name in REQUIRED:
        shutil.copy2(run_dir / name, destination / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--baseline-name", required=True)
    parser.add_argument("--baselines-dir", type=Path, default=Path("evaluation/baselines/structured-hr"))
    args = parser.parse_args()
    destination = args.baselines_dir / args.baseline_name
    publish(args.run_dir, destination)
    print(f"Published curated baseline at {destination}")


if __name__ == "__main__":
    main()
