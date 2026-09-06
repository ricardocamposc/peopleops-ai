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

## Runner

Use:

`evaluation/spikes/direct_sqlalchemy_phase42_skills_runner.py`

It reuses the Phase 4.2 runner and changes only the Query Programmer runtime.

Example:

`python evaluation/spikes/direct_sqlalchemy_phase42_skills_runner.py --output-dir evaluation/runs/phase42-skill-prompts-smoke --limit 5 --mode team`

The generated manifest records hashes for all three Query Programmer skill prompts.

## Evaluation intent

This variant should be compared against the existing Phase 4.2 runner using the same cases and model configuration.

Primary comparison dimensions:

- first-pass technical validity;
- final technical validity;
- internal repair success;
- Senior first-pass approval;
- final semantic approval;
- number of LLM calls/repair attempts;
- latency;
- failure category.

The immediate purpose is not to maximize the score. It is to determine whether separating Query Programmer skills improves reliability without adding more agentic complexity.
