"""Regenerate the fictitious policy PDFs with the effective date shown in metadata."""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject


OLD_DATE = "01/09/2026"
NEW_DATE = "01/01/2026"


def _write_pdf(source: Path, destination: Path) -> None:
    reader = PdfReader(source)
    writer = PdfWriter(clone_from=reader)
    old_bytes = OLD_DATE.encode("ascii")
    new_bytes = NEW_DATE.encode("ascii")
    replacements = 0
    for page in writer.pages:
        contents = page.get_contents()
        if contents is None:
            continue
        content = contents.get_data()
        replacements += content.count(old_bytes)
        if old_bytes not in content:
            continue
        stream = DecodedStreamObject()
        stream.set_data(content.replace(old_bytes, new_bytes))
        page[NameObject("/Contents")] = stream
    if replacements == 0:
        raise RuntimeError(f"{source} does not contain the expected effective date")
    if len(old_bytes) != len(new_bytes):
        raise RuntimeError("date replacement must preserve byte length")
    with destination.open("wb") as stream:
        writer.write(stream)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("policies/fictitious-company"))
    args = parser.parse_args()
    pdfs = sorted(args.directory.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"no PDFs found in {args.directory}")
    for source in pdfs:
        temporary = source.with_suffix(".pdf.tmp")
        _write_pdf(source, temporary)
        temporary.replace(source)
        print(source)


if __name__ == "__main__":
    main()
