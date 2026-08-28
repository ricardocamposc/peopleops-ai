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

## Policy RAG baseline

Policy RAG uses a separate expected dataset and real API observations:

```bash
make baseline-policy
```

The default dataset is the synthetic-company corpus mapped to the Policy RAG
requirements in PDD sections 7.6, 7.8 and 7.10:
`evaluation/cases/policy_rag_fictitious_company_v1.jsonl`. Use
`POLICY_DATASET=evaluation/cases/policy_rag_v1.jsonl` only when intentionally
running the smaller generic regression set.

The three MVP suites are independently executable and regression-checked:

```bash
make baseline-policy-rag
make baseline-policy-rag-holdout
make baseline-hris-mcp
make baseline-combined
```

`make baseline-all` runs the three suites in that order. The HRIS/MCP and
combined datasets are currently contract baselines with explicit observations;
they become live application baselines when their corresponding end-to-end
execution slices are enabled. Their thresholds are stored in
`evaluation/baselines/` and a regression causes a non-zero command result.

`baseline-policy-rag-holdout` runs the independent robustness set in
`evaluation/cases/policy_rag_holdout_v1.jsonl`. It contains new paraphrases,
three languages, ambiguity, typographical errors, multi-policy questions,
historical dates, distractors and unsupported claims. Its output must use a
new directory; it is not merged into the regression baseline and is not tuned
to produce an artificial pass. After a deterministic run, judge it with:

This file is retained as a validation/robustness and regression set. It has
already been used during remediation cycles and must not be described as an
unseen final evaluation. New unseen evaluations belong in a separately frozen
dataset such as `policy_rag_holdout_v2.jsonl`.

```bash
POLICY_PREDICTIONS=evaluation/runs/<holdout-run>/predictions.jsonl \
POLICY_BASELINE_OUTPUT_DIR=evaluation/runs/<holdout-run> \
make baseline-policy-judge
```

If `POLICY_BASELINE_OUTPUT_DIR` is omitted, the Make target creates a new
timestamped directory under `evaluation/runs/baseline-YYYYMMDD-HHMMSS`; a
completed run is never written to a shared fixed directory by default.

The runner fails before execution if the required active policy corpus is not
already ingested or if active versions are not explicitly marked
`synthetic=true`. It never re-ingests documents to make a baseline pass.

Each run creates a self-contained evidence bundle under the requested output
directory:

- `manifest.json`: run ID, commit, dataset, endpoint, timeout and artifact contract.
- `dataset.jsonl`: exact dataset snapshot used by the run.
- `predictions.jsonl`: one checkpointed record per API request, including the
  request ID, complete API response, stage history, retrieved policies,
  evidence, citations, verification and latency.
- Evaluation cases may carry `pdd_section`, `capability`, `expected_sources`
  and `expected_behavior`. These are traceability labels from the PDD, not
  application routing rules; the runner copies them to the prediction and
  evidence artifacts.
- `evidence.jsonl`: compact case-by-case evidence view suitable for review or
  downstream metric tooling.
- `metrics.json` and `enterprise_rag_baseline.json`: the same deterministic
  result, including summary metrics and per-case indicators compatible with
  the Enterprise RAG baseline format. In addition to recall/hit rate, the
  report includes `document_precision`, `promoted_document_precision` and
  `retrieval_noise_rate`. Recall measures whether expected documents appear;
  precision penalizes unrelated retrieved documents; promoted precision
  measures the documents actually exposed as citations. Lexical groundedness
  and relevance are diagnostic token-overlap metrics only; they do not route
  questions or decide whether an answer is acceptable.
- `report.md`: human-readable metrics and failed-case report.

The request metadata includes `evaluation_run_id` and `evaluation_case_id`.
Because the API stores conversation metadata, these values can be joined back
to `analysis_interaction` through the conversation when auditing a run in the
database. The repository also includes an exporter for that persisted view:

```bash
make inspect-policy-run POLICY_RUN_ID=<run_id> \
  POLICY_RUN_OUTPUT=evaluation/runs/<run_id>/database-evidence.json
```

A failed run preserves `predictions.jsonl`, `evidence.jsonl` and
`failure.json` as checkpoints; it does not pretend to have a complete baseline.

Use `make baseline-policy-judge` only after a deterministic baseline exists
and only for an authorized synthetic run. Its outputs are
`predictions_judged.jsonl` and `metrics_judged.json`, separate from
`predictions.jsonl` and `metrics.json`.

## MCP boundary baseline

The structured-data boundary is evaluated independently from Policy RAG and
agent quality. It uses a dataset with expected values only, executes the real
official MCP client against the Streamable HTTP endpoint, and writes a new
timestamped run under `evaluation/runs/`:

```bash
make baseline-mcp
```

The run records the negotiated protocol, server information, capability and
query results, normalized source failures, provider evidence and deterministic
boundary metrics. It does not call REST discovery/query endpoints and does not
persist observed values into the source dataset. Curated evidence belongs under
`evaluation/baselines/mcp/regression-v1/` only after an explicit review.
