# Integrated evaluation (Slice 16)

`peopleops_api.evaluation_runner` is the single deterministic runner for the versioned
MVP evaluation dataset. It reports independent results for semantic
understanding, conceptual query, structured data/MCP, RAG, workflow, HITL and
final answer. Expected values are objective contract observations; they do not
encode a question router and are never loaded into PeopleOps persistence.

Run from the repository root:

```bash
make evaluate
```

This writes the reproducible JSON and Markdown artifacts under
`evaluation/runs/`. A different observed-output file can be supplied with
`--observations`; its keys must be case IDs. The runner does not ingest
documents, auto-fix data, call an LLM, or hide failures with retries.

The optional LangSmith integration remains technical tracing only. The
authoritative functional record is still `AnalysisInteraction`.
