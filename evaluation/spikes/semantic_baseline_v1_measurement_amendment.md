# Semantic Baseline v1 — Measurement Amendment

## Status

This amendment is normative for `Semantic Understanding & Comparison Baseline v1`.

The original baseline design named:

- `semantic_comparison_baseline_evaluator_v1.py`

as the frozen evaluator.

A pre-execution oracle audit identified an objective measurement defect: v1 did not implement an expected temporal scope for:

```text
CURRENT_DATE + LAST_N + YEAR
```

This affects baseline cases B05 and B10 (`last two years through today`). The compiler can legitimately produce:

```text
RELATIVE_RANGE
SOURCE_DATE - 2 YEAR
→ SOURCE_DATE + 1 DAY
```

while evaluator v1 returned no expected scope, creating false compiler and normalization mismatches.

## Approved correction

The frozen evaluator for the baseline is therefore version-bumped to:

- `semantic_comparison_baseline_evaluator_v1_1.py`

Evaluator v1.1:

1. preserves the previously audited v1 behavior;
2. adds only the missing independent oracle for `CURRENT_DATE + LAST_N + YEAR`;
3. preserves the independent normalization oracle;
4. does not change Semantic Understanding prompts;
5. does not change schemas;
6. does not change canonicalization;
7. does not change compiler behavior;
8. does not change normalization behavior;
9. adds a regression self-test for the exact defect that invalidated the first baseline attempt.

For source date `2026-08-30`, the required regression is:

```text
CURRENT_DATE + LAST_N + YEAR + count=2 + through_current_date=true

expected compiled scope:
SOURCE_DATE -2 YEAR
→ SOURCE_DATE +1 DAY

expected normalized range:
2024-08-30 <= date < 2026-08-31
```

## Freeze rule

After v1.1 passes its self-test and the baseline preflight audit, it becomes the frozen evaluator for Semantic Baseline v1.

No further evaluator change is allowed during the 240-execution baseline unless another objective measurement defect is found. If such a defect appears after OpenAI execution begins, the run must be marked invalid and stopped rather than repaired in place.

All other dataset sizes, gates, repetitions, semantic conventions, case inventory, and baseline rules remain unchanged from `semantic_baseline_v1_design.md`.
