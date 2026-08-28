"""Promote one reviewed MCP run without silently overwriting evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REQUIRED = ("manifest.json", "dataset.jsonl", "predictions.jsonl", "evidence.jsonl", "metrics.json", "report.md")


def publish(run_dir: Path, destination: Path) -> None:
    if destination.exists():
        raise SystemExit(f"refusing to overwrite curated baseline: {destination}")
    missing = [name for name in REQUIRED if not (run_dir / name).is_file()]
    if missing:
        raise SystemExit(f"incomplete MCP run; missing: {', '.join(missing)}")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("execution") != "real_mcp_boundary":
        raise SystemExit("run is not a real MCP boundary execution")
    destination.mkdir(parents=True)
    for name in REQUIRED:
        shutil.copy2(run_dir / name, destination / name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--baseline-name", required=True)
    parser.add_argument("--baselines-dir", type=Path, default=Path("evaluation/baselines/mcp"))
    args = parser.parse_args()
    publish(args.run_dir, args.baselines_dir / args.baseline_name)
    print(f"Published curated MCP baseline at {args.baselines_dir / args.baseline_name}")


if __name__ == "__main__":
    main()
