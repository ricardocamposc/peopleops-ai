# Semantic Understanding & Comparison Baseline v1

## 1. Purpose

Freeze a repeatable baseline for the current Phase 3.4.2 / 3.4.3 semantic architecture before further semantic remediation.

The baseline must measure separately:

1. raw LLM semantic understanding;
2. canonical semantic understanding;
3. compiler fidelity given valid canonical input;
4. normalized temporal correctness;
5. end-to-end compiled semantic success;
6. stability across repeated executions.

The frozen measurement instrument is:

- `semantic_comparison_baseline_evaluator_v1.py`
- integrated through `semantic_understanding_phase343_runner.py`

The baseline must not change Semantic Understanding prompts, schemas, canonicalizer, compiler, normalizer, or the evaluator.

## 2. Architecture under test

```text
Natural language
→ capability scope
→ scoped catalog
→ Semantic Understanding V343
→ canonicalization
→ ComparisonPlan / simple Query Intent compiler
→ temporal normalization
→ frozen baseline evaluator v1
```

No MCP, SQL, provider execution, or executable Eloquent is part of this baseline.

## 3. Dataset size and repetitions

- 48 unique cases.
- 5 repetitions per case.
- 240 total model executions.
- Model: `gpt-4o-mini`.
- Source date: `2026-08-30`.
- Timezone: `UTC`.
- Retries: `0`.

A critical subset must also be tagged for an optional later 10-repeat battery, but the v1 baseline itself remains 5 repetitions.

## 4. Case distribution

| Group | Cases |
|---|---:|
| A. Result semantics / projection / measure | 6 |
| B. Explicit and relative temporal semantics | 10 |
| C. Calendar + containing time scope | 6 |
| D. Filter vs grouping / ordering | 6 |
| E. Ambiguity / unsupported / antecedents | 8 |
| F. Comparisons | 12 |
| Total | 48 |

Cases may exercise more than one dimension; the group indicates the primary purpose.

## 5. Expected dataset schema

Each JSONL row must contain at least:

```json
{
  "id": "...",
  "language": "es|en|pt",
  "group": "A|B|C|D|E|F",
  "category": "...",
  "critical": true,
  "question": "...",
  "expected": {
    "answerability": "UNDERSTOOD_AND_EXECUTABLE|NEEDS_CLARIFICATION|UNSUPPORTED_QUERY",
    "requested_fields": [],
    "measure": null,
    "temporal": null,
    "comparison": null,
    "breakdowns": [],
    "calendar_conditions": [],
    "order_by": [],
    "limit": null,
    "alignment": null,
    "operation": null
  }
}
```

The dataset is the independent semantic oracle for raw/canonical understanding. Do not derive expected values from model outputs.

For compiler fidelity, the frozen evaluator may compare analytical structures against a valid canonical understanding, but normalized temporal expectations must remain independently derived by the evaluator.

## 6. Semantic conventions

### 6.1 Result semantics

- Listing without explicit fields uses default fields: `requested_fields=[]`, no measure.
- Explicit field requests populate only `requested_fields`.
- Aggregate requests use `measure` and do not copy the measure field into `requested_fields`.
- `total`, `sum`, equivalent explicit aggregate wording → `SUM`.
- Showing a numeric field does not imply aggregation.

### 6.2 Temporal semantics

- Relative meanings remain symbolic in Semantic Understanding.
- Explicit dates/months/years retain explicit values.
- `previous period` without a determined unit is ambiguous.
- `previous month` and `previous calendar year` are resolved.
- Comparisons can anchor the right operand to `SOURCE_DATE` or `LEFT_OPERAND` as explicitly required.

### 6.3 Calendar predicates

Supported concepts in this baseline:

- `WEEKDAY = MONDAY`;
- `DAY_OF_MONTH = 15`;
- `FIRST_DAY_OF_MONTH`;
- `LAST_DAY_OF_MONTH`.

`FIRST_DAY_OF_WEEK` remains unsupported.

Calendar filtering does not imply grouping.

### 6.4 Grouping

- Group only when the user explicitly requests grouped/broken-down output.
- `by month` across a range that can span years uses `YEAR_MONTH`.
- Calendar filter and grouping are independent operations.
- Explicit `do not group` must result in no grouping.

### 6.5 Ambiguity and unsupported

- Multiple reasonable meanings → `NEEDS_CLARIFICATION`.
- A single understood meaning that the contract cannot represent → `UNSUPPORTED_QUERY`.
- Non-executable states must contain no executable query content after canonicalization/compilation.

## 7. Exact 48-case inventory

### Group A — Result semantics / projection / measure (6)

A01 `es` — `Lista los 5 últimos trabajadores que ingresaron a la empresa.`

Expected: executable; default fields; no measure; order `employee.hire_date DESC`; limit 5.

A02 `es` — `Muéstrame el código y nombre de los trabajadores.`

Expected: executable; requested fields `employee.employee_code`, `employee.full_name`; no measure.

A03 `es` — `Muéstrame la fecha y las horas extras registradas en enero de 2026.`

Expected: executable; requested fields `overtime.work_date`, `overtime.approved_minutes`; no measure; January 2026.

A04 `es` — `Dame el total de horas extras de enero de 2026.`

Expected: executable; `SUM(overtime.approved_minutes)`; no requested fields; January 2026.

A05 `en` — `Show me the overtime date and approved overtime minutes for January 2026.`

Expected: same semantics as A03.

A06 `pt` — `Mostre o total de horas extras de janeiro de 2026.`

Expected: same semantics as A04.

### Group B — Explicit and relative temporal semantics (10)

B01 `es` — `Dame las horas extras de enero de 2026.`
Expected: explicit January 2026, aggregate SUM.

B02 `es` — `Dame las horas extras del mes actual.`
Expected: current month symbolic, aggregate SUM.

B03 `es` — `Dame las horas extras del mes anterior.`
Expected: previous month symbolic, aggregate SUM.

B04 `es` — `Dame las horas extras de los últimos 3 meses.`
Expected: last 3 calendar months using symbolic relative semantics, aggregate SUM.

B05 `es` — `Dame las horas extras de los últimos 2 años hasta hoy.`
Expected: current-date anchored last 2 years through current date, aggregate SUM.

B06 `es` — `Dame las horas extras acumuladas en lo que va del año.`
Expected: YTD/current year from start through current date, aggregate SUM.

B07 `es` — `Dame las horas extras del año calendario anterior.`
Expected: previous calendar year symbolic, aggregate SUM.

B08 `en` — `Show me overtime for the previous month.`
Expected: same as B03.

B09 `pt` — `Mostre as horas extras do mês anterior.`
Expected: same as B03.

B10 `en` — `Show me overtime for the last two years through today.`
Expected: same as B05.

### Group C — Calendar + containing time scope (6)

C01 `es` — `Dame el total de horas extras de cada lunes de 2026.`
Expected: year 2026 + WEEKDAY MONDAY; SUM; no grouping.

C02 `es` — `Dame el total de horas extras del día 15 de cada mes de 2026.`
Expected: year 2026 + DAY_OF_MONTH 15; SUM; no grouping.

C03 `es` — `Dame el total de horas extras del primer día de cada mes de 2026.`
Expected: year 2026 + FIRST_DAY_OF_MONTH; SUM; no grouping.

C04 `es` — `Dame el total de horas extras del último día de cada mes de 2026.`
Expected: year 2026 + LAST_DAY_OF_MONTH; SUM; no grouping.

C05 `en` — `Show total overtime for every Monday in 2026.`
Expected: same as C01.

C06 `pt` — `Mostre o total de horas extras do último dia de cada mês de 2026.`
Expected: same as C04.

### Group D — Filter vs grouping / ordering (6)

D01 `es` — `Dame las horas extras de cada lunes de 2026, no agrupes los resultados.`
Expected: WEEKDAY MONDAY filter; no grouping.

D02 `es` — `Dame las horas extras de cada lunes de 2026 agrupadas por mes.`
Expected: WEEKDAY MONDAY filter + YEAR_MONTH grouping.

D03 `es` — `Dame las horas extras de los últimos 3 meses agrupadas por mes.`
Expected: last 3 months + YEAR_MONTH grouping.

D04 `es` — `Dame las horas extras de enero de 2026 agrupadas por departamento.`
Expected: January 2026 + group `department.name` + SUM.

D05 `es` — `Ordena las horas extras de enero de 2026 por fecha ascendente, sin agrupar.`
Expected: January 2026 + order `overtime.work_date ASC`; no grouping.

D06 `en` — `Show overtime for 2026 grouped by month and ordered by month ascending.`
Expected: year 2026 + YEAR_MONTH grouping + corresponding ascending order.

### Group E — Ambiguity / unsupported / antecedents (8)

E01 `es` — `Dame las horas extras del período anterior.`
Expected: NEEDS_CLARIFICATION; no executable semantic content.

E02 `en` — `Show me overtime for the previous period.`
Expected: NEEDS_CLARIFICATION.

E03 `pt` — `Mostre as horas extras do período anterior.`
Expected: NEEDS_CLARIFICATION.

E04 `es` — `Compara el mes actual con el anterior.`
Expected: executable comparison; current month vs previous month; right relative to LEFT_OPERAND or another semantically equivalent explicit antecedent representation accepted by the contract.

E05 `es` — `Estamos comparando meses. Compara el mes actual con el período anterior.`
Expected: executable only if structured context is represented as the resolution source establishing MONTH; otherwise the oracle must not silently relax this case. The baseline dataset must choose one contractual expectation before execution and document it.

E06 `es` — `Dame las horas extras del primer día de la semana de 2026.`
Expected: UNSUPPORTED_QUERY (`FIRST_DAY_OF_WEEK` unsupported).

E07 `es` — `Dame las horas extras del período de nómina anterior.`
Expected: UNSUPPORTED_QUERY under the current public semantic contract because payroll-period calendar semantics are provider-defined and not available here.

E08 `es` — `Compara enero de 2026 con el período anterior.`
Expected: NEEDS_CLARIFICATION; must not inherit MONTH merely because the left operand is January.

### Group F — Comparisons (12)

F01 `es` — `Compara las horas extras del mes actual con las del mes anterior.`
Expected: current month vs previous month; SAME_PERIOD; SIDE_BY_SIDE.

F02 `es` — `Compara enero de 2026 con el mes anterior.`
Expected: left January 2026; right previous MONTH relative to LEFT_OPERAND; SAME_PERIOD; SIDE_BY_SIDE; normalized right December 2025.

F03 `es` — `Compara las horas extras de enero y febrero de este año con enero y febrero del año pasado.`
Expected: current year months [1,2] vs previous year months [1,2]; SAME_MONTH; SIDE_BY_SIDE.

F04 `en` — `Compare overtime for the current calendar year with the previous calendar year.`
Expected: current year vs previous year; SAME_PERIOD; SIDE_BY_SIDE.

F05 `pt` — `Compare as horas extras do mês atual com as do mês anterior.`
Expected: same semantics as F01.

F06 `es` — `Compara enero de 2026 con diciembre de 2025.`
Expected: two explicit month operands; SAME_PERIOD; SIDE_BY_SIDE.

F07 `es` — `Compara enero de 2026 con enero de 2025.`
Expected: explicit months across years; SAME_MONTH; SIDE_BY_SIDE.

F08 `es` — `Dime la diferencia de horas extras entre el mes actual y el mes anterior.`
Expected: current vs previous month; operation DELTA.

F09 `en` — `Show the percent change in overtime between the current month and the previous month.`
Expected: current vs previous month; operation PERCENT_CHANGE.

F10 `es` — `Compara las horas extras de enero de 2026 con el mes anterior y muéstralas por departamento.`
Expected: January 2026 vs previous month anchored LEFT_OPERAND; department breakdown applied consistently; SAME_PERIOD.

F11 `es` — `Compara las horas extras de enero y febrero de 2026 con enero y febrero de 2025 y ordénalas por mes.`
Expected: explicit multi-month comparison across years; SAME_MONTH; month alignment/order semantics preserved.

F12 `en` — `Compare January 2026 with the previous period.`
Expected: NEEDS_CLARIFICATION; no executable ComparisonPlan.

## 8. Critical subset

Tag at least these cases `critical=true`:

- A03, A04;
- B03, B04, B06, B07;
- C01, C02, C04;
- D01, D02, D04;
- E01, E04, E06, E08;
- F01, F02, F03, F08, F09, F10, F12.

## 9. Metrics

### 9.1 Primary metrics

- `STRUCTURED_OUTPUT_SUCCESS`
- `RAW_UNDERSTANDING_ACCURACY`
- `CANONICAL_UNDERSTANDING_ACCURACY`
- `COMPILED_SEMANTIC_SUCCESS`
- `COMPILER_SUCCESS_GIVEN_VALID_INPUT`
- `NORMALIZATION_ERROR_RATE`

### 9.2 Semantic component metrics

- answerability accuracy;
- requested-fields accuracy;
- measure accuracy;
- temporal semantic accuracy;
- calendar-condition accuracy;
- grouping accuracy;
- ordering accuracy;
- limit accuracy;
- ambiguity recognition;
- canonical abstention safety;
- compiled abstention safety;
- unsupported recognition;
- antecedent-resolution accuracy;
- materialization leakage raw/canonical.

### 9.3 Comparison metrics

- comparison detection accuracy;
- left-operand semantic accuracy;
- right-operand semantic accuracy;
- `relative_to` accuracy;
- anchor/materialized-range accuracy;
- alignment accuracy;
- operation accuracy;
- `COMPARISON_PLAN_SEMANTIC_SUCCESS`;
- `COMPARISON_COMPILER_SUCCESS_GIVEN_VALID_INPUT`.

### 9.4 Architecture/safety metrics

- selected scope accuracy where an independent expected capability oracle exists;
- effective scope accuracy;
- payroll contamination;
- entity derivation accuracy;
- forbidden SQL/physical-schema constructs.

### 9.5 Reliability metrics

Per case:

- successes / 5;
- canonical fingerprint modal count / 5;
- compiled fingerprint modal count / 5;
- modal semantic fingerprint;
- first failing layer distribution.

Global:

- average canonical fingerprint consistency;
- average compiled fingerprint consistency;
- passing-set reliability.

`passing-set` means cases that achieve at least 4/5 compiled successes. Passing-set reliability is total compiled successes across that set divided by total executions in that set.

## 10. Frozen gates

Do not change these after seeing results.

```text
Structured Output                         >= 99%
Canonical Understanding                  >= 80%
Compiled Semantic Success                >= 80%
Compiler Success Given Valid Input       >= 98%
Effective Scope                          >= 98%
Canonical Abstention Safety              = 100%
Compiled Abstention Safety               = 100%
Payroll Contamination                    = 0%
Entity Derivation                        = 100%
Passing-set Reliability                  >= 90%
```

Comparison sub-gates:

```text
Comparison Understanding                 >= 75%
ComparisonPlan Semantic Success          >= 75%
Comparison Compiler Given Valid Input    >= 98%
```

Failure to meet a gate is evidence, not a reason to modify the evaluator or dataset after execution.

## 11. Baseline artifacts

The runner must produce one immutable run directory containing at least:

- `manifest.json`;
- `raw_responses.jsonl`;
- `metrics.json`;
- `case_summary.jsonl`;
- `failure_clusters.json`;
- `baseline_report.md`.

The manifest must record:

- baseline name/version;
- architecture commit under test;
- evaluator name/version;
- dataset SHA/hash;
- model;
- source date/timezone;
- repetitions;
- exact gates;
- total calls;
- no MCP/SQL/Eloquent execution.

## 12. Failure attribution

Each execution must attribute the first failing layer to exactly one of:

- `SCOPE_FAILURE`;
- `RAW_UNDERSTANDING_FAILURE`;
- `CANONICALIZATION_FAILURE`;
- `COMPILER_FAILURE_WITH_VALID_INPUT`;
- `NORMALIZATION_FAILURE`;
- `FULL_SUCCESS`;
- `MODEL_OR_TRANSPORT_FAILURE`;
- `EVALUATOR_FAILURE`.

Keep all differences as well; do not retain only `first_difference`.

## 13. Baseline freeze rule

Before any 240-call execution:

1. audit all 48 oracle rows;
2. run dataset/evaluator self-tests;
3. verify no duplicate case IDs;
4. verify every expected field is contract-valid;
5. verify language/category distribution;
6. verify comparison anchors independently;
7. verify non-executable cases contain no expected executable semantics;
8. verify the runner uses the frozen evaluator v1;
9. run a dry-run / synthetic test without OpenAI;
10. only then execute the baseline.

After the baseline starts, do not modify dataset, evaluator, prompt, schema, compiler, canonicalizer, or normalizer until the complete run and report are produced.
