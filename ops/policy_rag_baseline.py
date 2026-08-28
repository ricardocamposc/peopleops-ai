"""Run the versioned Policy RAG dataset against the real PeopleOps API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_SRC = Path(__file__).resolve().parents[1] / "apps" / "peopleops-api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

def _json_request(base_url: str, path: str, *, payload: dict | None, timeout: float) -> dict | list:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json", "X-Evaluation-Run": "policy-rag"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {path}: {detail[:500]}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"request failed for {path}: {type(exc).__name__}") from exc


def _evaluation_question(case) -> str:
    context = [f"Evaluate the policy as of {case.as_of.isoformat()}." ]
    if case.filters:
        filters = []
        for key in ("document_key", "document_type", "department", "confidentiality"):
            value = getattr(case.filters, key, None)
            if value:
                filters.append(f"{key}={value}")
        if case.filters.metadata:
            filters.append(f"metadata={case.filters.metadata}")
        if filters:
            context.append("Apply these policy filters: " + ", ".join(filters) + ".")
    return f"{' '.join(context)} {case.query}"


def _validate_corpus(base_url: str, cases, timeout: float) -> None:
    documents = _json_request(base_url, "/api/v1/policies", payload=None, timeout=timeout)
    expected_keys = {
        key
        for case in cases
        for key in case.expected_document_keys
    }
    active_versions = [
        (document.get("document_key"), version)
        for document in documents
        for version in document.get("versions", [])
        if version.get("status") == "active"
    ]
    active_expected_versions = [
        (document_key, version)
        for document_key, version in active_versions
        if document_key in expected_keys
    ]
    non_synthetic_expected = [
        document_key
        for document_key, version in active_expected_versions
        if version.get("metadata", {}).get("synthetic") is not True
    ]
    if non_synthetic_expected:
        raise RuntimeError(
            "baseline requires every expected active policy version to be explicitly marked "
            "synthetic=true: " + ", ".join(sorted(set(non_synthetic_expected)))
        )
    available = {
        (document_key, version.get("version"))
        for document_key, version in active_expected_versions
    }
    missing = []
    for case in cases:
        for key in case.expected_document_keys:
            versions = set(case.expected_versions) or {None}
            if not any(doc_key == key and (version in versions or None in versions) for doc_key, version in available):
                missing.append({"case_id": case.case_id, "document_key": key, "versions": sorted(v for _, v in available if _ == key)})
    if missing:
        raise RuntimeError(
            "required policy corpus is not ingested; baseline will not ingest it automatically: "
            + json.dumps(missing)
        )


def run(dataset: Path, output_dir: Path, base_url: str, timeout: float) -> dict:
    from peopleops_api.policy_evaluation import evaluate_predictions, load_cases, write_artifact

    cases = load_cases(dataset)
    if not cases:
        raise RuntimeError("dataset contains no evaluation cases")
    _validate_corpus(base_url, cases, timeout)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    manifest = {
        "run_id": run_id,
        "git_commit": _git_commit(),
        "timestamp": datetime.now(UTC).isoformat(),
        "dataset": str(dataset),
        "dataset_case_count": len(cases),
        "base_url": base_url,
        "request_timeout_seconds": timeout,
        "execution": "real_peopleops_api",
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        "embedding_dimension": int(os.getenv("EMBEDDING_DIMENSION", "1536")),
        "retrieval_top_k": 6,
        "retrieval_minimum_score": 0.30,
        "policy_non_synthetic_mode": os.getenv("POLICY_NON_SYNTHETIC_MODE", "insufficient"),
        "judge_model": None,
        "artifact_contract": {
            "manifest": "manifest.json",
            "dataset": "dataset.jsonl",
            "predictions": "predictions.jsonl",
            "evidence": "evidence.jsonl",
            "metrics": "metrics.json",
            "report": "report.md",
            "optional": ["metrics_judged.json", "predictions_judged.jsonl"],
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output_dir / "dataset.jsonl").write_text(
        Path(dataset).read_text(encoding="utf-8"), encoding="utf-8"
    )
    predictions: list[dict] = []
    evidence_records: list[dict] = []
    for index, case in enumerate(cases, start=1):
        started = time.monotonic()
        expected_answerable = (
            case.expected_answerable
            if case.expected_answerable is not None
            else case.expected_status.value == "COMPLETED"
        )
        request_payload = {
            "question": _evaluation_question(case),
            "metadata": {
                "evaluation_case_id": case.case_id,
                "evaluation_run_id": run_id,
                "language": case.language,
                "as_of_date": case.as_of.isoformat(),
                "evaluation_policy_only": True,
            },
        }
        prediction: dict = {
            "case_id": case.case_id,
            "run_id": run_id,
            "question": case.query,
            "language": case.language,
            "as_of_date": case.as_of.isoformat(),
            "synthetic_corpus": True,
            "pdd_section": case.pdd_section,
            "capability": case.capability or "policy_rag",
            "expected_sources": list(case.expected_sources),
            "expected_behavior": case.expected_behavior,
            "expected_answerable": expected_answerable,
            "expected_policy_facts": list(case.expected_policy_facts),
        }
        try:
            response = _json_request(
                base_url,
                "/api/v1/analysis",
                payload=request_payload,
                timeout=timeout,
            )
            prediction.update(
                {
                    "request_id": response.get("request_id"),
                    "status": str(response.get("status") or "").upper(),
                    "answer": (response.get("response") or {}).get("answer"),
                    "policy_documents": response.get("policy_sources") or [],
                    "retrieved_policy_documents": _policy_documents_from_evidence(
                        (response.get("validation") or {})
                        .get("evidence_verification", {})
                        .get("retrieved_evidence", response.get("evidence") or [])
                    ),
                    "policy_versions": response.get("policy_versions") or [],
                    "evidence": response.get("evidence") or [],
                    "retrieved_evidence": (response.get("validation") or {})
                    .get("evidence_verification", {})
                    .get("retrieved_evidence", response.get("evidence") or []),
                    "evidence_verification": (response.get("validation") or {}).get("evidence_verification"),
                    "citations_valid": all(item.get("verified") is True for item in response.get("evidence") or [] if item.get("type") == "policy"),
                    "warnings": response.get("warnings") or [],
                    "error_type": response.get("error_type"),
                    "error_detail": response.get("error_detail"),
                    "latency_ms": response.get("latency_ms"),
                    "model_name": response.get("model_name"),
                    "stage_history": response.get("stage_history") or [],
                    "validation": response.get("validation") or {},
                    "structured_result": response.get("structured_result"),
                    "request_payload": request_payload,
                    "api_response": response,
                }
            )
        except Exception as exc:  # preserve the failed case and stop loudly
            prediction.update({"error": str(exc), "failed_layer": "runner"})
            predictions.append(prediction)
            _checkpoint(output_dir, predictions)
            _write_evidence(output_dir, evidence_records)
            _write_partial_failure(output_dir, run_id, case.case_id, str(exc), predictions)
            raise RuntimeError(f"case {case.case_id} failed after {index - 1}/{len(cases)} cases: {exc}") from exc
        prediction.setdefault("latency_ms", round((time.monotonic() - started) * 1000))
        evidence_records.append(_evidence_record(prediction))
        predictions.append(prediction)
        _checkpoint(output_dir, predictions)
        _write_evidence(output_dir, evidence_records)
        print(f"[{index}/{len(cases)}] {case.case_id} {prediction.get('status')} {prediction.get('latency_ms')}ms")
    result = evaluate_predictions(cases, predictions)
    result["dataset"] = dataset.stem
    write_artifact(result, output_dir / "metrics.json")
    # Keep the portfolio-compatible baseline artifact name in addition to the
    # canonical metrics.json name. Both contain the same deterministic result.
    write_artifact(result, output_dir / "enterprise_rag_baseline.json")
    report = _report(result)
    report = report.replace(
        "# Policy RAG evaluation\n",
        "# Policy RAG evaluation\n\n"
        f"- Run: `{run_id}`\n"
        f"- Commit: `{manifest['git_commit']}`\n"
        f"- Dataset: `{dataset}`\n",
        1,
    )
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    return result


def _checkpoint(output_dir: Path, predictions: list[dict]) -> None:
    destination = output_dir / "predictions.jsonl"
    destination.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in predictions), encoding="utf-8")


def _evidence_record(prediction: dict) -> dict:
    """Write a compact, auditable evidence record without losing raw response data."""
    return {
        "run_id": prediction.get("run_id"),
        "case_id": prediction.get("case_id"),
        "request_id": prediction.get("request_id"),
        "question": prediction.get("question"),
        "pdd_section": prediction.get("pdd_section"),
        "capability": prediction.get("capability"),
        "expected_sources": prediction.get("expected_sources", []),
        "expected_behavior": prediction.get("expected_behavior"),
        "status": prediction.get("status"),
        "latency_ms": prediction.get("latency_ms"),
        "policy_documents": prediction.get("policy_documents", []),
        "retrieved_policy_documents": prediction.get("retrieved_policy_documents", []),
        "policy_versions": prediction.get("policy_versions", []),
        "evidence": prediction.get("evidence", []),
        "retrieved_evidence": prediction.get("retrieved_evidence", []),
        "evidence_verification": prediction.get("evidence_verification"),
        "citations_valid": prediction.get("citations_valid"),
        "answer": prediction.get("answer"),
        "stage_history": prediction.get("stage_history", []),
        "validation": prediction.get("validation", {}),
        "error_type": prediction.get("error_type"),
        "error_detail": prediction.get("error_detail"),
    }


def _policy_documents_from_evidence(evidence: list[dict]) -> list[dict]:
    seen: set[str] = set()
    documents: list[dict] = []
    for item in evidence:
        key = item.get("document_key") or item.get("document_id")
        if not key or key in seen:
            continue
        seen.add(key)
        documents.append(
            {
                "document_key": item.get("document_key"),
                "document_id": item.get("document_id"),
                "title": item.get("title"),
                "version": item.get("version"),
            }
        )
    return documents


def _write_evidence(output_dir: Path, records: list[dict]) -> None:
    (output_dir / "evidence.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
        encoding="utf-8",
    )


def _write_partial_failure(
    output_dir: Path, run_id: str, case_id: str, error: str, predictions: list[dict]
) -> None:
    (output_dir / "failure.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "failed_case_id": case_id,
                "error": error,
                "completed_case_count": len(predictions) - 1,
                "checkpoint": "predictions.jsonl",
                "evidence_checkpoint": "evidence.jsonl",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _report(result: dict) -> str:
    lines = ["# Policy RAG evaluation", "", f"Cases: {result['case_count']}", "", "## Deterministic metrics", ""]
    for key, value in result["metrics"].items():
        lines.append(f"- `{key}`: {value if value is not None else 'N/A'}")
    lines.extend(["", "## Failed cases", ""])
    failed = result.get("failed_cases") or []
    for item in failed:
        lines.extend(
            [
                f"### `{item['case_id']}`",
                f"- failed_layer: `{item.get('failed_layer') or item.get('error')}`",
                f"- expected_status: `{item.get('expected_workflow_status') or item.get('expected_status')}`",
                f"- observed_status: `{item.get('status')}`",
                f"- expected_docs: `{item.get('expected_document_keys', [])}`",
                f"- retrieved_docs: `{item.get('retrieved_document_keys', [])}`",
                f"- promoted_docs: `{item.get('promoted_document_keys', [])}`",
                f"- expected_versions: `{item.get('expected_versions', [])}`",
                f"- observed_versions: `{item.get('observed_versions', [])}`",
                f"- answerability: `{item.get('answerable')}` (expected `{item.get('expected_answerable')}`)",
                f"- policy_fact_coverage: `{item.get('policy_fact_coverage')}`",
                f"- verification: `{item.get('verification_result', {})}`",
            ]
        )
    if not failed:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _git_commit() -> str:
    try:
        import subprocess

        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/cases/policy_rag_v1.jsonl"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--request-timeout", type=float, default=180.0)
    args = parser.parse_args()
    try:
        result = run(args.dataset, args.output_dir, args.base_url, args.request_timeout)
    except Exception as exc:
        print(f"baseline failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result["metrics"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
