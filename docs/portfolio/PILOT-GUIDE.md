# PeopleOps AI — Controlled pilot guide

## Purpose and boundary

The pilot validates the intelligence and governance workflow over a customer
approved MCP provider. It is not a production deployment, HRIS replacement,
legal advice service, or automated employment-decision system.

Start with synthetic data. A customer pilot may proceed only after written
approval of the data classification, access scopes, retention, audit owner,
incident contact, and human reviewer group.

## Provider substitution

Keep the PeopleOps build, typed conceptual-query contracts, workflow and UI
unchanged. Replace only `REFERENCE_MCP_SERVER_URL` with a Customer MCP Server
that implements the discovery, validation, read-only execution, evidence and
error contracts. The customer server owns physical tables, APIs, mappings,
credentials and source-specific authorization. Do not copy proprietary schema
names or data into this repository.

The replacement must demonstrate:

- capability/entity/relationship discovery with semantic metadata;
- provider-neutral results and evidence;
- read-only execution, row/time limits and request correlation;
- payroll scope enforcement and safe normalized errors;
- contract and schema-independence cases before any user pilot.

## Pilot phases

1. **Readiness:** architecture/security review, synthetic smoke, evaluation
   baseline, reviewer training and rollback plan.
2. **Shadow:** approved read-only sample, no operational decisions, compare
   answers with HR analysts and log unsupported/insufficient evidence.
3. **Limited users:** named HR/payroll reviewers, restricted payroll scope,
   daily review of evidence and Human Review decisions.
4. **Exit review:** deterministic metrics, incidents, latency, abstention,
   evidence quality and user feedback determine whether to extend.

## Explicit non-goals

No writes to payroll/HRIS, dismissal/promotion/hiring/sanction automation,
customer adapter in the public repo, unrestricted employee search, or claim of
production readiness.
