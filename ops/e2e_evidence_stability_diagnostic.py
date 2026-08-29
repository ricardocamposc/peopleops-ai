"""Capture repeated real E2E structured-HR responses without changing the system."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "Dime las horas extras del período 2026-01"


def main() -> None:
    out = ROOT / "evaluation" / "runs" / f"e2e-evidence-stability-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=False)
    attempts = []
    for index in range(1, 11):
        started = time.monotonic()
        request = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/analysis",
            data=json.dumps({"question": QUESTION, "metadata": {"evaluation_structured_hr": True}}).encode(),
            headers={"Content-Type": "application/json", "X-Security-Scopes": "hr:read"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.load(response)
            attempts.append({"run": index, "latency_ms": round((time.monotonic() - started) * 1000, 1), "response": body})
            trace = body.get("evaluation_trace") or {}
            print(json.dumps({"run": index, "request_id": body.get("request_id"), "status": body.get("status"), "stage": body.get("current_stage"), "validations": len(trace.get("provider_validations") or []), "executions": len(trace.get("provider_executions") or []), "evidence": len(body.get("evidence") or [])}, ensure_ascii=False), flush=True)
        except Exception as exc:
            attempts.append({"run": index, "latency_ms": round((time.monotonic() - started) * 1000, 1), "error": {"class": type(exc).__name__, "message": str(exc)[:300]}})
            print(json.dumps({"run": index, "error": type(exc).__name__}), flush=True)
    attempts_path = out / "attempts.jsonl"
    attempts_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in attempts) + "\n", encoding="utf-8")
    manifest = {"run_type": "e2e_evidence_stability", "timestamp": datetime.now(UTC).isoformat(), "question": QUESTION, "attempts": 10, "execution_mode": "real_peopleops_openai_mcp_hris", "model": os.environ.get("OPENAI_MODEL", "configured"), "mcp_audit": "request_ids retained in responses"}
    manifest["attempts_sha256"] = hashlib.sha256(attempts_path.read_bytes()).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "stage-comparison.json").write_text(json.dumps({"runs": [{"run": a["run"], "request_id": (a.get("response") or {}).get("request_id"), "status": (a.get("response") or {}).get("status"), "stage_history": (a.get("response") or {}).get("stage_history"), "trace": (a.get("response") or {}).get("evaluation_trace"), "evidence": (a.get("response") or {}).get("evidence"), "structured_result": (a.get("response") or {}).get("structured_result"), "answer": (a.get("response") or {}).get("answer")} for a in attempts]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps({"runs": len(attempts), "completed": sum((a.get("response") or {}).get("status") == "completed" for a in attempts), "failed": sum((a.get("response") or {}).get("status") == "failed" for a in attempts), "insufficient_data": sum((a.get("response") or {}).get("status") == "insufficient_data" for a in attempts)}, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text("# E2E evidence stability diagnostic\n\nRepeated real API/MCP executions; no MCP or HRIS shortcut.\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
