"""Load the fictitious-company policy PDFs using the real PeopleOps API."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import httpx


def _entry_by_key(root: Path) -> dict[str, dict]:
    metadata = {
        item["clave_documento"]: item
        for item in json.loads((root / "metadata_politicas_rrhh.json").read_text())
    }
    manifest = {
        item["document_key"]: item
        for item in json.loads((root / "manifest.json").read_text()).get("documents", [])
    }
    return metadata | manifest


def _fields(item: dict, *, is_spanish_metadata: bool) -> dict[str, str]:
    if is_spanish_metadata:
        effective_to = item["vigente_hasta"]
        fields = {
            "document_key": item["clave_documento"],
            "title": item["titulo"],
            "version": item["version"],
            "effective_from": datetime.strptime(item["vigente_desde"], "%d/%m/%Y").date().isoformat(),
            "effective_to": datetime.strptime(effective_to, "%d/%m/%Y").date().isoformat()
            if effective_to
            else "",
            "document_type": item["tipo"],
            "department": item["departamento"] or "",
            "confidentiality": item["confidencialidad"],
            "metadata": json.dumps(
                {**item["metadata"], "synthetic": True, "company": "Northstar People Services"}
            ),
        }
        if not fields["effective_to"]:
            fields.pop("effective_to")
        return fields
    return {
        "document_key": item["document_key"],
        "title": item["title"],
        "version": item["version"],
        "effective_from": item["effective_from"],
        "document_type": "policy",
        "department": item["department"],
        "confidentiality": item["confidentiality"],
        "metadata": json.dumps({"synthetic": True, "company": "Northstar People Services"}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--corpus-dir", type=Path, default=Path("policies/fictitious-company"))
    args = parser.parse_args()
    entries = _entry_by_key(args.corpus_dir)
    pdfs = sorted(args.corpus_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"no PDFs found in {args.corpus_dir}")

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=180.0) as client:
        client.get("/api/v1/health").raise_for_status()
        for pdf in pdfs:
            key = pdf.stem.removesuffix("-v1")
            item = entries.get(key)
            if item is None:
                raise SystemExit(f"metadata not found for {pdf.name}")
            data = _fields(item, is_spanish_metadata="clave_documento" in item)
            with pdf.open("rb") as stream:
                response = client.post(
                    "/api/v1/policies/upload",
                    data=data,
                    files={"file": (pdf.name, stream, "application/pdf")},
                )
            if response.is_error:
                raise RuntimeError(f"{pdf.name}: HTTP {response.status_code}: {response.text[:500]}")
            result = response.json()
            ingestion = result["ingestion"]
            print(
                f"{result['document']['document_key']} "
                f"{ingestion['status']} chunks={ingestion['chunk_count']} "
                f"idempotent={result['idempotent']}"
            )


if __name__ == "__main__":
    main()
