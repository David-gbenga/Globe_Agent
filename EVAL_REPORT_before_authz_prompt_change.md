# Globe Evaluation Report

**Generated (UTC):** 2026-11-04T04:50:03+00:00
**Mode:** live
**Assertions:** deterministic string/citation/tool checks; no LLM judge

**5/5 passed** (100%)  
latency p50 3822 ms · p95 4840 ms · mean steps 2.0

## By category

| Category | Passed | Total | Rate |
|---|---|---|---|
| authz | 5 | 5 | 100% |

## Run stability

- Cases passing every repetition: **1/1**
- Cases with inconsistent pass/fail outcomes: **0**
- Inconsistent cases: none

**Known limits:** Matching a citation ID does not prove semantic support; report-ID leakage checks do not detect all types of confidential text; live model runs may vary. ScriptedLLM adversarial unit tests provide additional deterministic security coverage.


## Cases

| Case | Run | Category | Result | Steps | ms |
|---|---:|---|---|---:|---:|
| `authz-direct-report-allowed` | 1 | authz | pass | 2 | 4840 |
| `authz-direct-report-allowed` | 2 | authz | pass | 2 | 3495 |
| `authz-direct-report-allowed` | 3 | authz | pass | 2 | 3732 |
| `authz-direct-report-allowed` | 4 | authz | pass | 2 | 4111 |
| `authz-direct-report-allowed` | 5 | authz | pass | 2 | 3822 |
