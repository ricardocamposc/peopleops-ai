# Phase 4.2 — Query Programmer Skill Prompts

## Purpose

This experiment remains inside **Phase 4.2**. It does not introduce a new phase.

The objective is to test a narrower hypothesis discovered while auditing the Phase 4.3 baseline: the Query Programmer currently uses one broad prompt for fresh generation, deterministic technical repair, and Senior-requested semantic repair. Those are different professional skills and may benefit from different instructions.

## What changes

Only the Query Programmer prompt strategy changes.

The existing Phase 4.2 graph, Functional Analyst, deterministic validator, Senior Reviewer, repair budgets, state model, dataset, and evaluation metrics remain unchanged.

The Query Programmer now has three prompt-level skills:

1. `GENERATE`
   - create a fresh SQLAlchemy 2.x query from a Functional Requirement;
   - emphasize correct Python/SQLAlchemy generation;
   - no repair history is required.

2. `TECHNICAL_REPAIR`
   - diagnose a previous candidate using deterministic validation diagnostics;
   - preserve the Functional Requirement;
   - correct syntax/build/compile defects;
   - used for both internal self-repair and outer technical repair.

3. `SEMANTIC_REPAIR`
   - revise a technically valid query after Senior Review;
   - preserve the Functional Requirement as the primary authority;
   - correct measures, dimensions, filters, grouping, relationships, grain, temporal or comparison defects;
   - do not blindly follow Senior implementation preferences that conflict with the functional contract.

## What does not change

- no new agent is created;
- no new phase is created;
- no new semantic hardcoding is introduced;
- deterministic validation remains the objective technical gate;
- Senior Review remains an independent semantic/functional check;
- no database execution is added;
- no MCP execution is added;
- no production code path is changed by this spike.

## Context behavior

Each LLM invocation is still a fresh request at the application level.

Each skill prompt receives exactly one `data_model` block and exactly one copy of each execution-context variable in its system prompt.

The human payload continues to contain typed artifacts only:

- Functional Requirement;
- repair type/attempt;
- previous query when applicable;
- deterministic validation result when applicable;
- Senior Review when applicable;
- internal tool results when applicable.

This experiment intentionally does not redesign context sharing yet. Prompt specialization is isolated first so its effect can be measured independently.

## Routing contract

The Query Programmer remains one logical agent. The workflow selects one skill per LLM invocation:

- initial generation -> `GENERATE`;
- internal deterministic self-repair -> `TECHNICAL_REPAIR`;
- outer deterministic repair -> `TECHNICAL_REPAIR`;
- Senior-requested revision -> `SEMANTIC_REPAIR`.

Unknown repair types fail fast instead of silently falling back to generation.

## Invocation audit

Every Query Programmer LLM invocation is recorded independently so a run can be reconstructed without inferring which prompt produced a candidate.

The audit metadata records:

- invocation sequence;
- `agent_id`;
- selected skill;
- prompt id and version;
- model;
- output schema;
- repair type and attempt;
- latency;
- relevant typed input artifacts;
- output status.

Internal generation/repair iterations are also annotated with the skill, prompt id/version, model, and LLM latency that produced the corresponding candidate.

This is required for the experiment because a single outer Query Programmer call may contain an initial `GENERATE` invocation followed by one or more `TECHNICAL_REPAIR` invocations.

## Runner

Use:

`evaluation/spikes/direct_sqlalchemy_phase42_skills_runner.py`

It reuses the Phase 4.2 runner and changes only the Query Programmer runtime.

Example:

`python evaluation/spikes/direct_sqlalchemy_phase42_skills_runner.py --output-dir evaluation/runs/phase42-skill-prompts-smoke --limit 5 --mode team`

The generated manifest records hashes for all three Query Programmer skill prompts.

## Pre-baseline verification

Before running the controlled baseline:

1. run the Phase 4.2 skill-routing tests;
2. run the existing Phase 4.2/Phase 4.3 deterministic/tooling tests;
3. run the repository unit-test suite;
4. run a small team-mode smoke experiment;
5. inspect at least one case that exercises internal technical repair and confirm the invocation audit shows `GENERATE -> TECHNICAL_REPAIR`;
6. inspect at least one Senior revision, when present, and confirm the invocation audit records `SEMANTIC_REPAIR`.

Do not change the dataset, model configuration, validation logic, Senior Review logic, or repair budgets while measuring the prompt-skill hypothesis.

## Evaluation intent

This variant should be compared against the existing Phase 4.2 runner using the same cases and model configuration.

Primary comparison dimensions:

- first-pass technical validity;
- final technical validity;
- internal repair success;
- Senior first-pass approval;
- final semantic approval;
- number of LLM calls/repair attempts;
- per-skill invocation counts and latency;
- failure category.

The immediate purpose is not to maximize the score. It is to determine whether separating Query Programmer skills improves reliability without adding more agentic complexity.
