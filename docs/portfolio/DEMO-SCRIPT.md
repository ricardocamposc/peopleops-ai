# PeopleOps AI — Demo script

This is the short, repeatable portfolio/pilot walkthrough. It uses only the
synthetic fixture and the three existing deployables.

## Setup

```bash
cp .env.example .env
cp apps/peopleops-web/.env.example apps/peopleops-web/.env.local
make build
make up
make demo-setup
make health
make smoke
```

`make demo-setup` applies PeopleOps migrations and loads both Schema A and
Schema B fixtures into the isolated synthetic database. It is safe to rerun
only on a disposable demo database; use `make clean` when resetting local
state.

## Flagship scenarios

1. Open `http://localhost:3000` and ask: “¿Puede este empleado solicitar 15
   días de vacaciones en noviembre?” Show the data/policy evidence and the
   `pending_human_review` state. In Human Review, inspect the evidence snapshot,
   choose Approve/Reject/Needs information, and show that the same request
   resumes with an audited decision.
2. Ask: “¿Por qué este empleado recibió menos neto este mes?” Show the
   period comparison, concept-level facts, overtime reconciliation and source
   evidence. Payroll requires the `hr:payroll` scope at the authenticated edge.
3. Ask: “¿Qué empleados tienen horas extra registradas que no aparecen
   correctamente en nómina?” Show the discrepancy set and explain that the
   copilot is read-only.

For a deterministic, key-free presentation, use the committed evaluation
artifacts under `evaluation/runs/` and the ground truth under
`synthetic-hris/seeds/ground_truth.json`. Live model analysis requires an
`OPENAI_API_KEY` supplied through the environment; no key is committed.

## Evidence to narrate

- Facts come through `PeopleOps API → HRDataGateway → MCP Client → Reference
  MCP Server`; the browser never connects to either database.
- Policy evidence is owned by PeopleOps and remains separate from structured
  HR facts.
- Inference is labelled as inference and sensitive outcomes pause for durable
  Human Review.
- Schema independence is proven by the same conceptual query mapped by the
  MCP boundary to physically different schemas.

## Capture list

Capture the browser at: home/analysis, evidence detail, policy upload/status,
Human Review inbox/detail, and the final decision. Keep request IDs visible,
redact local secrets, and use only synthetic IDs. `docs/portfolio/assets/`
contains the capture manifest; generated screenshots/video are intentionally
not committed.
