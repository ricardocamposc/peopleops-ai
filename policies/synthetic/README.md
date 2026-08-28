# Synthetic policy corpus

These policy sources are fictional, intentionally small, and safe for local
demo/evaluation use. They are reference content for the PeopleOps-owned
Policy RAG boundary; they are not legal advice and are not HRIS data.

The API accepts PDF uploads. To demonstrate ingestion, upload a PDF export of
one of the sources below through `/policies` with this business metadata:

```json
{
  "document_key": "synthetic-vacation",
  "document_type": "policy",
  "department": "People",
  "confidentiality": "internal",
  "synthetic": true
}
```

Use the corresponding `document_key` for the payroll source. The explicit
`synthetic=true` marker is required by the evaluation runner before any
content can be sent to an external semantic judge. The existing policy
ingestion and retrieval tests create deterministic PDF fixtures and verify
chunk provenance, effective dates, version selection, evidence verification
and abstention.

Never replace these files with customer policies or personal data.
