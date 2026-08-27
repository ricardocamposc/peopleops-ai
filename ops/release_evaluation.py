"""Create the auditable Slice 18 evaluation index from versioned artifacts."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).parents[1]
RUNS = ROOT / "evaluation" / "runs"
DATASETS = sorted((ROOT / "evaluation" / "cases").glob("*_v*.jsonl"))


def case_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def main() -> int:
    command = [
        "poetry",
        "-C",
        "apps/peopleops-api",
        "run",
        "python",
        "-m",
        "peopleops_api.evaluation_runner",
        "--dataset",
        "../../evaluation/cases/integrated_v1.jsonl",
        "--output-dir",
        "../../evaluation/runs",
        "--baseline",
        "../../evaluation/baselines/slice16-integrated.json",
    ]
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "apps/peopleops-api/src")}
    subprocess.run(command, cwd=ROOT, check=True, env=environment)
    integrated = (
        json.loads((RUNS / "57eac1ca9b94aa1a.json").read_text(encoding="utf-8"))
        if (RUNS / "57eac1ca9b94aa1a.json").exists()
        else None
    )
    if integrated is None:
        candidates = sorted(
            RUNS.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True
        )
        integrated = json.loads(candidates[0].read_text(encoding="utf-8"))
    summary = {
        "schema_version": "slice18.portfolio_evaluation.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "deterministic": True,
        "integrated_run_id": integrated["run_id"],
        "integrated_metrics": integrated["metrics"],
        "datasets": {
            path.stem: {"path": str(path.relative_to(ROOT)), "case_count": case_count(path)}
            for path in DATASETS
        },
        "policy_corpus": sorted(
            str(path.relative_to(ROOT)) for path in (ROOT / "policies" / "synthetic").glob("*.md")
        ),
        "note": "Per-layer runners and MCP/PostgreSQL contract tests remain authoritative; this index does not replace them or mutate observations.",
    }
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / "slice18-portfolio.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Slice 18 portfolio evaluation",
        "",
        f"Integrated run: `{summary['integrated_run_id']}`",
        "",
        "| Dataset | Cases |",
        "|---|---:|",
    ]
    lines.extend(
        f"| `{name}` | {item['case_count']} |" for name, item in summary["datasets"].items()
    )
    lines.extend(["", "Integrated metrics:", "", "| Layer | Pass rate |", "|---|---:|"])
    lines.extend(
        f"| {layer} | {value:.2%} |" for layer, value in summary["integrated_metrics"].items()
    )
    (RUNS / "slice18-portfolio.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
