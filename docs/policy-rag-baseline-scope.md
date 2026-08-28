# Policy RAG MVP baseline

## Scope

The first PeopleOps AI baseline closes the document-retrieval capability before
HRIS/MCP and combined workflows. It evaluates the real `/api/v1/analysis`
application path against the synthetic fictitious-company policy corpus.

The initial scope is derived from the Policy RAG portions of the PDD:

- section 7.6: policies and procedures;
- section 7.8: policy-aware questions;
- section 7.10: unsupported or restricted questions.

Questions about employees, attendance, payroll or organizational aggregates are
not silently treated as Policy RAG cases. They belong to the subsequent
HRIS/MCP baseline. Questions combining structured data and policies belong to
the final integrated baseline.

## Dataset

The executable dataset is:

`evaluation/cases/policy_rag_fictitious_company_v1.jsonl`

It contains positive single-policy, positive multi-policy, multilingual,
missing-policy and insufficient-evidence cases. Each case declares the expected
policy key/version when applicable and whether the application should answer or
abstain.

## Run artifacts

Every invocation creates a separate timestamped directory under
`evaluation/runs/`, unless an explicit output directory is provided. The
required compatibility artifacts are:

- `predictions.jsonl`: one real API observation per case;
- `enterprise_rag_baseline.json`: deterministic summary and per-case metrics.

The additional `manifest.json`, `dataset.jsonl`, `evidence.jsonl`, `metrics.json`
and `report.md` files make the run reproducible and auditable. The manifest
contains the run ID; the API request metadata stores the same run ID and case
ID so the persisted `analysis_interaction` records can be traced back to the
filesystem artifacts.

## Success criteria

The baseline is considered operational when all dataset cases complete without
runner errors and the artifact contains per-case values for document hit,
document recall, answerability, abstention, citation validity and the two
diagnostic lexical metrics. Quality thresholds are evaluated from the observed
results; the runner does not convert a failed case into a passing result.
