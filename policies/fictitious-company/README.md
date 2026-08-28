# Northstar People Services - fictional policy corpus

This folder contains the shareable synthetic policy corpus used to validate
the PeopleOps Policy RAG workflow. **Northstar People Services** is a fictional
company; all names, rules, dates and content are invented for demonstration
and testing only.

The corpus currently contains:

- `synthetic-vacation-v1.pdf` - Vacation and Leave Policy
- `synthetic-payroll-v1.pdf` - Payroll Change Procedure
- `manifest.json` - generation metadata and document inventory

Each PDF contains four pages, visible business metadata, PDF technical
metadata and the marker `synthetic=true`. The PDFs are intentionally ordinary
test inputs: they can be uploaded through the application UI or through the
API, and they are safe to use with the authorized synthetic-data evaluator.

To regenerate the corpus from the repository root:

```bash
python ops/generate_policy_pdfs.py
```

The application database is not populated by this generator. Upload the PDFs
explicitly through the application so ingestion, chunking and embeddings are
tested as part of the workflow.
