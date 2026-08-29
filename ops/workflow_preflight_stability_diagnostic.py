"""Capture repeated real workflow state for one structured HR query."""
from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "Dime las horas extras del período 2026-01"


def main() -> None:
    out = ROOT / "evaluation" / "runs" / f"workflow-preflight-stability-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=False)
    attempts = []
    for run in range(1, 21):
        request = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/analysis",
            data=json.dumps({"question": QUESTION, "metadata": {"evaluation_structured_hr": True}}).encode(),
            headers={"Content-Type": "application/json", "X-Security-Scopes": "hr:read"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.load(response)
            trace = body.get("evaluation_trace") or {}
            attempts.append({"run": run, "request_id": body.get("request_id"), "status": body.get("status"), "error_type": body.get("error_type"), "current_stage": body.get("current_stage"), "stage_history": body.get("stage_history"), "semantic_request": body.get("semantic_request"), "query_plan": body.get("query_plan"), "evaluation_trace": trace, "evidence": body.get("evidence"), "structured_result": body.get("structured_result"), "response": body.get("response"), "answer": body.get("answer"), "warnings": body.get("warnings")})
            print(json.dumps({"run": run, "request_id": body.get("request_id"), "status": body.get("status"), "stage": body.get("current_stage"), "queries": len((body.get("query_plan") or {}).get("queries") or []), "validations": len(trace.get("provider_validations") or []), "executions": len(trace.get("provider_executions") or [])}, ensure_ascii=False), flush=True)
        except Exception as exc:
            attempts.append({"run": run, "error": {"class": type(exc).__name__, "message": str(exc)[:300]}})
            print(json.dumps({"run": run, "error": type(exc).__name__}), flush=True)
    attempts_path = out / "attempts.jsonl"
    attempts_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in attempts) + "\n", encoding="utf-8")
    (out / "state-transitions.jsonl").write_text("\n".join(json.dumps({"run": x["run"], "request_id": x.get("request_id"), "stage_history": x.get("stage_history"), "trace": x.get("evaluation_trace")}, ensure_ascii=False) for x in attempts) + "\n", encoding="utf-8")
    manifest = {"run_type": "workflow_preflight_stability", "timestamp": datetime.now(UTC).isoformat(), "question": QUESTION, "attempts": 20, "execution_mode": "real_peopleops_openai_langgraph_mcp_hris", "mcp_audit": "request_ids retained", "dataset": "single diagnostic question"}
    manifest["attempts_sha256"] = hashlib.sha256(attempts_path.read_bytes()).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    statuses = {}
    for x in attempts:
        status = (x.get("status") or x.get("error", {}).get("class") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    (out / "failure-distribution.json").write_text(json.dumps(statuses, indent=2) + "\n", encoding="utf-8")
    (out / "good-vs-bad.json").write_text(json.dumps({"successful": [x for x in attempts if x.get("status") == "completed"], "unsuccessful": [x for x in attempts if x.get("status") != "completed"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "report.md").write_text("# Workflow/preflight stability diagnostic\n\n20 real runs; no code changes during BEFORE phase.\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
