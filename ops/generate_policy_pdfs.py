"""Generate the synthetic policy PDFs used by the local Policy RAG demo.

The generator intentionally uses only the Python standard library so it can be
run before the application dependencies are installed. The output is a small,
deterministic four-page corpus with visible business metadata and PDF-level
metadata suitable for upload through the PeopleOps API.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


POLICIES = (
    {
        "document_key": "synthetic-vacation",
        "title": "Vacation and Leave Policy",
        "version": "1",
        "effective_from": "2025-01-01",
        "department": "People",
        "confidentiality": "internal",
        "source": "policies/synthetic/vacation-policy-v1.md",
        "pages": [
            (
                "01 Purpose and scope",
                [
                    "This fictional policy defines how employees request vacation and leave.",
                    "It applies to all regular employees unless a written local addendum says otherwise.",
                    "The policy is a synthetic fixture for the PeopleOps AI demonstration.",
                    "It is not legal advice and must not be used for an employment decision.",
                    "",
                    "Policy owner: People Operations",
                    "Review cadence: annual and after a material regulatory change",
                    "Primary record: the approved request in the HRIS",
                    "",
                    "Employees remain responsible for checking their available balance before",
                    "submitting a request. A request is not approved merely because it was submitted.",
                ],
            ),
            (
                "02 Request and approval process",
                [
                    "An employee may request vacation up to the available balance.",
                    "The request should include the start date, end date and a contact plan.",
                    "The direct manager reviews staffing impact and records an approval or rejection.",
                    "People Operations reviews requests that exceed the available balance.",
                    "",
                    "People Operations review is also required when the request:",
                    "- overlaps a leave period;",
                    "- approaches a contract end date; or",
                    "- requires an exception to a local scheduling rule.",
                    "",
                    "Approval is not an automatic employment action. An authorized reviewer",
                    "records the final decision and the decision date in the HRIS.",
                ],
            ),
            (
                "03 Exceptions and evidence",
                [
                    "A manager may request an exception when business continuity requires it.",
                    "The exception request must state the reason, affected dates and mitigation plan.",
                    "People Operations confirms whether the exception is permitted.",
                    "No exception is valid until the approval is recorded in the HRIS.",
                    "",
                    "Required evidence for an approved request:",
                    "- request identifier and employee identifier;",
                    "- requested dates and balance at the time of review;",
                    "- manager decision and timestamp;",
                    "- People Operations decision when an exception applies.",
                    "",
                    "A question about promotion, compensation or career progression is outside",
                    "the scope of this policy and must not be inferred from a leave approval.",
                ],
            ),
            (
                "04 Responsibilities and related controls",
                [
                    "Employees submit accurate requests and keep contact information current.",
                    "Managers review requests consistently and avoid decisions based on protected data.",
                    "People Operations maintains the policy, handles exceptions and audits records.",
                    "The HRIS is the system of record for balances and approval decisions.",
                    "",
                    "Related controls include payroll cut-off dates, leave records and access review.",
                    "Those controls do not change the approval requirement in this document.",
                    "If two approved sources conflict, the issue must be escalated to People Operations.",
                    "",
                    "Document status: active",
                    "Synthetic marker: synthetic=true",
                    "End of policy",
                ],
            ),
        ],
    },
    {
        "document_key": "synthetic-payroll",
        "title": "Payroll Change Procedure",
        "version": "1",
        "effective_from": "2025-01-01",
        "department": "People",
        "confidentiality": "internal",
        "source": "policies/synthetic/payroll-procedure-v1.md",
        "pages": [
            (
                "01 Purpose and scope",
                [
                    "This fictional procedure defines controls for employee payroll changes.",
                    "It covers recurring compensation, one-time adjustments and bank changes.",
                    "The procedure is a synthetic fixture for the PeopleOps AI demonstration.",
                    "It is not legal advice and must not be used for an employment decision.",
                    "",
                    "Process owner: Payroll Operations",
                    "Control owner: People Operations",
                    "System of record: the payroll system and its approval log",
                    "",
                    "Every change must have a source request, an authorized approval and an",
                    "effective payroll period before it is included in a payroll run.",
                ],
            ),
            (
                "02 Change intake and approval",
                [
                    "A change request must identify the employee, change type and effective date.",
                    "Payroll Operations validates the request against the employee record.",
                    "The manager confirms the business reason for recurring compensation changes.",
                    "People Operations confirms changes that affect employment conditions.",
                    "",
                    "Bank account changes require an additional identity verification step.",
                    "One-time payments require the approving cost center and payment reason.",
                    "Requests received after the payroll cut-off move to the next eligible cycle.",
                    "",
                    "No payroll change is applied based only on an informal message or chat.",
                ],
            ),
            (
                "03 Validation and exception handling",
                [
                    "Payroll Operations checks required fields before submitting a change.",
                    "The reviewer compares the effective date with the payroll calendar.",
                    "Conflicting requests remain pending until the source of truth is confirmed.",
                    "A rejected request includes a reason and may be resubmitted with corrections.",
                    "",
                    "Required evidence for a completed change:",
                    "- source request and request identifier;",
                    "- approval identity and timestamp;",
                    "- validated effective date and payroll period;",
                    "- result of the payroll processing check.",
                    "",
                    "This procedure does not define career progression or promotion criteria.",
                ],
            ),
            (
                "04 Audit and related controls",
                [
                    "Payroll Operations retains the approval trail for the configured retention period.",
                    "People Operations reviews exceptions and recurring failure patterns monthly.",
                    "Access to payroll changes is restricted to authorized roles.",
                    "A material discrepancy is escalated and corrected through a controlled rerun.",
                    "",
                    "Related controls include vacation approvals, expense processing and HRIS access.",
                    "Those controls are separate procedures and cannot be inferred here.",
                    "If two approved sources conflict, Payroll Operations escalates the issue.",
                    "",
                    "Document status: active",
                    "Synthetic marker: synthetic=true",
                    "End of procedure",
                ],
            ),
        ],
    },
)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_pdf(path: Path, policy: dict) -> None:
    objects: list[bytes] = []

    def add_object(value: bytes) -> int:
        objects.append(value)
        return len(objects)

    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    for page_number, (heading, body) in enumerate(policy["pages"], start=1):
        lines = [policy["title"], f"Document key: {policy['document_key']}", f"Version: {policy['version']}", f"Effective from: {policy['effective_from']}", f"Department: {policy['department']}", f"Confidentiality: {policy['confidentiality']}", "Synthetic: true", "", heading, ""] + body
        commands = ["BT", "/F1 18 Tf", "48 770 Td", f"({_pdf_escape(lines[0])}) Tj", "/F1 9 Tf"]
        for line in lines[1:]:
            commands.extend(["0 -18 Td", f"({_pdf_escape(line)}) Tj"])
        commands.extend(["0 -22 Td", f"(Page {page_number} of 4) Tj", "ET"])
        stream = "\n".join(commands).encode("latin-1")
        content_id = add_object(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        page_id = add_object(
            f"<< /Type /Page /Parent PAGES /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        page_ids.append(page_id)
    pages_id = add_object(
        (f"<< /Type /Pages /Kids [{ ' '.join(f'{item} 0 R' for item in page_ids) }] /Count {len(page_ids)} >>").encode()
    )
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    info_id = add_object(
        f"<< /Title ({_pdf_escape(policy['title'])}) /Author (PeopleOps AI Synthetic Corpus) /Subject (Synthetic policy for Policy RAG evaluation) /Keywords (synthetic, policy, {policy['document_key']}) >>".encode()
    )

    # Resolve the symbolic parent placeholder after all object ids are known.
    objects = [item.replace(b"PAGES", f"{pages_id} 0 R".encode()) for item in objects]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, value in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode())
        output.extend(value)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R /Info {info_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    path.write_bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("policies/fictitious-company")
    )
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "synthetic": True,
        "documents": [],
    }
    for policy in POLICIES:
        if len(policy["pages"]) < 4:
            raise RuntimeError(f"{policy['document_key']} must contain at least four pages")
        filename = f"{policy['document_key']}-v{policy['version']}.pdf"
        destination = args.output_dir / filename
        _write_pdf(destination, policy)
        manifest["documents"].append(
            {
                key: policy[key]
                for key in (
                    "document_key",
                    "title",
                    "version",
                    "effective_from",
                    "department",
                    "confidentiality",
                    "source",
                )
            }
            | {"filename": str(destination), "pages": len(policy["pages"]), "synthetic": True}
        )
    manifest_path = args.manifest or args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(manifest['documents'])} policy PDFs in {args.output_dir}")


if __name__ == "__main__":
    main()
