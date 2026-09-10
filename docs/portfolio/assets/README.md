# Portfolio capture manifest

Committed portfolio assets should contain **synthetic data only** and should document implemented, reproducible behavior rather than mockups.

Current committed assets:

- `peopleops-analysis-workspace.webp` — main PeopleOps analysis workspace with synthetic data and recent analysis history.
- `peopleops-last-five-employees.webp` — evidence-driven response to the “last 5 employees” request; the system exposes that only four matching active records are available instead of fabricating a fifth result.
- `semantic-run-viewer-overview.jpg` — PeopleOps Semantic Run Viewer showing a production-graph evaluation run and node-level inspection.

Additional useful screenshots or a short screen recording:

1. Data Evidence and Policy Evidence shown together for a policy-aware analysis.
2. Pending Human Review with evidence snapshot.
3. Review decision and resumed analysis with the same request ID.
4. Payroll discrepancy/reconciliation with warnings and source evidence.
5. Policy upload metadata and ingestion status.
6. Semantic Run Viewer with an expanded LLM round showing rendered prompt/context.
7. Semantic Run Viewer with an expanded tool call showing tool input/output.
8. External OpenAI Codex session using the registered PeopleOps MCP server.

Do not commit customer data, credentials, private ERP/HRIS schemas or screenshots that expose secrets.
