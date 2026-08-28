"""Deterministic baseline for the real MCP source boundary."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp import Client

REPO_ROOT = Path(__file__).resolve().parents[1]


def _request_args(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": f"mcp-eval-{case['id']}",
        "security": case.get("security", {"scopes": ["hr:read", "hr:payroll"]}),
    }


async def run_case(base_url: str, case: dict[str, Any], alternate_url: str | None) -> dict[str, Any]:
    operation = case["operation"]
    if operation == "source_unavailable":
        target = "http://127.0.0.1:1/mcp"
    else:
        target = f"{base_url.rstrip('/')}/mcp"
    try:
        async with Client(target, read_timeout_seconds=10) as client:
            observed: dict[str, Any] = {
                "status": "success",
                "protocol_version": client.protocol_version,
                "server_info": client.server_info.model_dump(mode="json") if client.server_info else None,
            }
            if operation == "discover_catalog":
                result = await client.call_tool("discover_catalog", _request_args(case))
                observed["catalog"] = result.structured_content
            elif operation == "discover_capabilities":
                result = await client.call_tool("discover_capabilities", _request_args(case))
                observed["capabilities"] = result.structured_content
            elif operation in {"validate", "execute"}:
                tool = "validate_conceptual_query" if operation == "validate" else "execute_conceptual_query"
                result = await client.call_tool(tool, {**_request_args(case), "query": case["query"]})
                observed["result"] = result.structured_content
                observed["tool_error"] = result.is_error
            elif operation == "schema_independence":
                if not alternate_url:
                    observed["status"] = "not_applicable"
                else:
                    args = {**_request_args(case), "query": case["query"]}
                    first = await client.call_tool("execute_conceptual_query", args)
                    async with Client(f"{alternate_url.rstrip('/')}/mcp", read_timeout_seconds=10) as alternate:
                        second = await alternate.call_tool("execute_conceptual_query", args)
                    observed["canonical"] = first.structured_content
                    observed["alternate"] = second.structured_content
            else:
                observed["status"] = "unsupported_operation"
            return observed
    except Exception as exc:
        return {"status": "source_unavailable" if operation == "source_unavailable" else "error", "error_type": type(exc).__name__}


def evaluate(case: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    checks: dict[str, bool | None] = {}
    if case["operation"] == "discover_catalog":
        catalog = observed.get("catalog") or {}
        checks["catalog"] = observed.get("status") == "success" and expected["catalog"] is True
        checks["required_entities"] = set(expected["required_entities"]) <= {item["entity_id"] for item in catalog.get("entities", [])}
    elif case["operation"] == "discover_capabilities":
        raw = observed.get("capabilities") or {}
        capabilities = raw.get("result", raw) if isinstance(raw, dict) else raw
        checks["capabilities"] = set(expected["required_capabilities"]) <= {item["name"] for item in capabilities}
    elif case["operation"] in {"validate", "execute"}:
        result = observed.get("result") or {}
        validation = result.get("validation", result)
        checks["valid"] = validation.get("valid") is expected["valid"]
        if "row_count" in expected:
            checks["row_count"] = (result.get("evidence") or {}).get("row_count") == expected["row_count"]
        if "error_contains" in expected:
            checks["error_contains"] = expected["error_contains"] in " ".join(validation.get("errors", []))
    elif case["operation"] == "source_unavailable":
        checks["status"] = observed.get("status") == expected["status"]
    elif case["operation"] == "schema_independence":
        if observed.get("status") == "not_applicable":
            checks["schema_independence"] = None
        else:
            first = observed.get("canonical") or {}
            second = observed.get("alternate") or {}
            checks["schema_independence"] = first.get("rows") == second.get("rows")
    applicable = [value for value in checks.values() if value is not None]
    return {"checks": checks, "passed": bool(applicable) and all(applicable) if applicable else None}


async def run(args: argparse.Namespace) -> None:
    cases = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    predictions = []
    for case in cases:
        observed = await run_case(args.base_url, case, args.alternate_url)
        predictions.append({"id": case["id"], "expected": case["expected"], "observed": observed, **evaluate(case, observed)})
    handshake_cases = [item for item in predictions if item["id"] != "source-unavailable-001"]
    expected_failure_cases = [item for item in predictions if item["id"] == "source-unavailable-001"]
    read_only_probe = _run_read_only_probe()
    metrics = {
        "handshake_success_rate": sum(
            bool(item["observed"].get("protocol_version")) for item in handshake_cases
        ) / len(handshake_cases),
        "capability_discovery_success_rate": sum(item["passed"] is True for item in predictions if item["id"] in {"discovery-001", "capabilities-001"}) / 2,
        "query_validation_accuracy": _metric(predictions, {"valid-query-001", "invalid-entity-001", "invalid-field-001", "relationship-001", "aggregation-001", "time-filter-001", "authorization-001"}),
        "execution_success_rate": _metric(predictions, {"zero-rows-001"}),
        "error_normalization_accuracy": _metric(predictions, {"source-unavailable-001"}),
        "schema_independence_accuracy": _metric(predictions, {"schema-independence-001"}),
        "provider_evidence_validity": _metric(predictions, {"zero-rows-001"}),
        "read_only_enforcement": 1.0 if read_only_probe.get("passed") else 0.0,
        "expected_failure_handling_accuracy": _metric(predictions, {"source-unavailable-001"}),
    }
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / "dataset.jsonl").write_text(args.dataset.read_text(encoding="utf-8"), encoding="utf-8")
    (output / "predictions.jsonl").write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in predictions), encoding="utf-8")
    (output / "evidence.jsonl").write_text("".join(json.dumps({"id": item["id"], "observed": item["observed"], "checks": item["checks"]}, sort_keys=True) + "\n" for item in predictions), encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps({"cases": predictions, "summary": metrics}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest = {
        "run_id": output.name,
        "git_commit": sha,
        "timestamp": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset.resolve().relative_to(REPO_ROOT)),
        "case_count": len(cases),
        "execution": "real_peopleops_api" if args.execution == "real_peopleops_api" else args.execution,
        "mcp_sdk": "mcp 2.1.1",
        "transport": "streamable_http",
        "base_url": args.base_url,
        "alternate_url": args.alternate_url,
        "handshake_metric": {
            "eligible_case_count": len(handshake_cases),
            "successful_case_count": sum(
                bool(item["observed"].get("protocol_version")) for item in handshake_cases
            ),
            "excluded_cases": [item["id"] for item in expected_failure_cases],
            "exclusion_reason": "the case intentionally targets an unavailable provider",
        },
        "read_only_probe": read_only_probe,
        "artifact_contract": ["manifest.json", "dataset.jsonl", "predictions.jsonl", "evidence.jsonl", "metrics.json", "report.md"],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failed = [item for item in predictions if item["passed"] is False]
    report = [
        "# MCP boundary evaluation",
        "",
        f"Run: `{output.name}`",
        f"Cases: {len(cases)}",
        "",
        "## Metric definitions",
        "",
        f"- `handshake_success_rate`: {len(handshake_cases)} eligible cases; "
        f"{sum(bool(item['observed'].get('protocol_version')) for item in handshake_cases)} successful. "
        "The intentionally unavailable-provider case is excluded from this denominator.",
        "- `expected_failure_handling_accuracy`: the unavailable-provider case remains evaluated separately.",
        "- `read_only_enforcement`: provider-side SQL validation plus PostgreSQL read-only transaction probe.",
        "",
        "## Metrics",
        "",
    ]
    report.extend(f"- `{key}`: {value}" for key, value in metrics.items())
    report.extend(["", "## Failed cases", ""])
    report.extend(f"- `{item['id']}`: failed_layer=`{_failed_layer(item)}`" for item in failed)
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, sort_keys=True))


def _metric(predictions: list[dict[str, Any]], ids: set[str]) -> float | str:
    selected = [item for item in predictions if item["id"] in ids and item["passed"] is not None]
    return sum(item["passed"] is True for item in selected) / len(selected) if selected else "N/A"


def _run_read_only_probe() -> dict[str, Any]:
    command = [
        "poetry",
        "-C",
        "apps/reference-mcp-server",
        "run",
        "python",
        "../../ops/mcp_read_only_probe.py",
    ]
    try:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(REPO_ROOT / "apps" / "reference-mcp-server" / "src")
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=environment,
        )
        return json.loads(completed.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return {"passed": False, "probe_error": type(exc).__name__}


def _failed_layer(item: dict[str, Any]) -> str:
    observed = item["observed"]
    if observed.get("status") == "source_unavailable":
        return "transport"
    if item["id"].startswith("discovery") or item["id"].startswith("capabilities"):
        return "capability_discovery"
    return "conceptual_validation" if "result" in observed else "execution"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/cases/mcp_boundary_v1.jsonl"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=os.getenv("REFERENCE_MCP_SERVER_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--alternate-url", default=os.getenv("REFERENCE_MCP_SERVER_ALTERNATE_URL"))
    parser.add_argument("--execution", default="real_mcp_boundary")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
