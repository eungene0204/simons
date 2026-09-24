# Strategy call reduction — 2026-09-24

Boundary: K — AI Runtime Orchestration. Implement in separate small steps: request sharing,
auxiliary extraction, condition-check batching, and conditional planner scheduling.
Public API, model selection, compiler semantics, independent recall and existing apply guards are preserved.

## Step 1: request sharing

- Primary parses with identical full request context share in-flight work within a process.
- Each subscriber receives its own result copy and can cancel independently. The last cancellation stops shared work.
- Legacy deferred validation remains per request. Completed cache keys include all request state and runtime switches.
- Targeted validation: `uv run pytest backend/tests/test_strategy_singleflight.py backend/tests/test_nl_cache.py backend/tests/test_observability_parse_root.py backend/tests/test_deferred_parse_validation.py -q`.

## Step 2: independent extraction

`interpreter/parse_evidence.py` combines condition phrases, backtest period, and explicit universe
expressions in a source-only call. `primary.py` passes phrases to the existing condition recall
and supplies the period response through an adapter to the unchanged period validator. Invalid
or missing sections use the original extractors; valid null periods do not trigger another call.
The original source checks, missing-value behavior, and no-overwrite rules remain in effect.

## Step 3: planner scheduling

`runtime/planner_gate.py` only settles plain markets when independent evidence, canonical tool
observations, and the interpreter agree. Themes, exclusions, ETF, named symbols, missing evidence,
and disagreement keep the original planner. For OpenRouter, complex planning begins as soon as
independent evidence arrives and overlaps the main interpretation. It does not wait for the full
interpretation. Existing tool observations are returned in the same DAG result contract.

## Step 4: condition checks

`interpreter/check_batch.py` batches quote, trading-value, and contribution checks when at least
two are applicable. Their original request builders, validators, and ordered application remain
in their respective modules. Returned item IDs protect against reordering. A missing ID is accepted
only when the section contains exactly one requested item; ambiguous/duplicate/conflicting IDs
fall back to the original checker. Invalid sections alone fall back. Newly recovered conditions
continue through their original follow-up check. Modification checks remain limited to added conditions.

## Validation results

- Targeted regression command below: **492 passed**, including cancellation, shared request isolation,
  context-sensitive keys, KR/US gates, condition recovery, contribution logic and legacy rollback.
- Deterministic comparison: initial plain-market parse **4 → 2** calls with identical compiled strategy,
  clarification and notices. Independent condition/period extraction **2 → 1**. Applicable special checks
  **3 → 1**, with identical applied conditions, amount and period values.
- Current configured OpenRouter model (`nvidia/nemotron-3-super-120b-a12b:free`): two synthetic inputs
  retained the same extracted condition phrases and 3y/null period results. The final live batch returned
  quote, trading-value and contribution verdicts in **one call**, including the requested item IDs.
- Earlier live attempts hit upstream HTTP 503 and missing IDs. Individual fallback preserved the strategy;
  output examples were updated to carry IDs. The final successful response had no individual fallback.
  These are small smoke samples, not a statistical quality or latency equivalence claim.
- Full suite was attempted with `uv run pytest backend/tests -q`. The default uv cache was inaccessible;
  subsequent commands set `UV_CACHE_DIR=/tmp/simons-uv-cache`. KRX import-time login required disabling
  `KRX_ID`/`KRX_PW` only for the test process. That full run reported **5276 passed, 6 skipped, 8 failed,
  55 errors**. Retrying with local socket access resolved all 55 environment errors. The affected contribution
  fixture was updated for the new protocol, and the targeted final run is green.
- The six remaining full-suite failures reproduce when loading all changed production modules from **HEAD**:
  `test_backfill_us_stocks.py::test_columns_match_korean_schema`, and `test_backtest_engine.py` cases for
  no period overlap, partial-period inclusion, delisted forced close, market-cap cutoff and split stop loss.
  They concern unchanged engine/data behavior and were not modified in this task.
- `git diff --check` passed. Frontend code was not changed; frontend tests were not required.

```sh
KRX_ID= KRX_PW= UV_CACHE_DIR=/tmp/simons-uv-cache uv run pytest \
  backend/tests/test_parse_evidence.py backend/tests/test_planner_gate.py \
  backend/tests/test_planner_first.py backend/tests/test_parallel_parse.py \
  backend/tests/test_check_batch.py backend/tests/test_strategy_singleflight.py \
  backend/tests/test_nl_cache.py backend/tests/test_strategy_conversation.py \
  backend/tests/test_contributions.py backend/tests/test_deferred_parse_validation.py \
  backend/tests/test_observability_parse_root.py backend/tests/test_request_cancellation.py \
  backend/tests/test_us_region_isolation.py -q
```

## Operation and limits

Batching and conditional planner scheduling default to on. `STRATEGY_CALL_REDUCTION=off` restores
individual extraction/checks and planner-first scheduling. Request sharing remains enabled for
primary parses; legacy deferred validation stays per request. Cache identity now includes full
request state, active provider/model, runtime flags and relevant universe/knowledge file stamps.
No process-shared cache was introduced: independent server workers may still compute the same request.
No model change, production deployment, or backend process restart was performed. Malformed batches,
ambiguous universes and newly recovered conditions can legitimately require additional calls.
