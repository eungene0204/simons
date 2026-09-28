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

## MA exit quote preservation — 2026-09-25

Boundary K; allowed files: `interpreter/quote_check.py`, `backend/nl_cache.py`,
`backend/tests/test_quote_check.py`, `backend/tests/test_strategy_conversation.py`, and this document.
The quote checker now explicitly distinguishes an N-day moving-average exit from a fixed percentage
stop loss or holding period. A `no/other` verdict that would delete an MA condition receives one
independent confirmation call, restricted to the rejected conditions. Disagreement, malformed output
or transport failure leaves that condition undecided, so the existing removal guard preserves it.
Confirmed fabricated conditions are still removed. Positive verdicts need no additional call;
cancellation still propagates. This applies to individual and batched checks, including added conditions
on modification turns. Parser cache version 11 expires responses containing the old false removal.

Validation: the new regression tests reproduced the false removal before the fix (13 failed, 2 passed).
`KRX_ID= KRX_PW= UV_CACHE_DIR=/tmp/simons-uv-cache uv run pytest backend/tests/test_quote_check.py backend/tests/test_check_batch.py backend/tests/test_strategy_conversation.py backend/tests/test_nl_cache.py -q`
passed **329 tests**. The existing fabricated-condition fixtures now answer the targeted confirmation.
Full-suite command: `KRX_ID= KRX_PW= HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 UV_CACHE_DIR=/tmp/simons-uv-cache uv run pytest backend/tests -q`.
Result: **5367 passed, 5 skipped, 1 failed**. The existing `test_columns_match_korean_schema` failure
compares US columns against a Korean parquet with five extra columns (first: `fcf_margin`), unrelated
to quote checking. The initial sandbox run hit local DB access errors and was interrupted during
embedding initialization; the final run allowed local DB/cache access and disabled model downloads.
Test-generated LFS fixture changes were restored, preserving fixture changes present before this task.
Live-model verification requires approval to send the strategy text to OpenRouter; automatic approval
review blocked that call. No live model result is claimed. `git diff --check` passed.
Model interpretation remains probabilistic; two agreeing incorrect verdicts can still remove a condition.
The project plan, architecture and SRS were reviewed; their edits belong to Boundary G and are outside
this implementation's scope. This boundary-local document records the behavior and validation.

## Korean example strategy audit — 2026-09-26

Boundary K. The 81 prompts in `components/strategy/StrategyExampleTabs.tsx` were each sent through
the real `parse_nl_strategy` pipeline using the installed local Ollama model. The audit compared
fundamental thresholds, holding periods, rebalance cadence, entry and exit roles, signal periods,
unsupported notices, and duplicate conditions. It did not transmit repository examples to the
configured OpenRouter service; automatic approval review blocked that external transfer.

The audit found these interpretation errors:

- Example 4: three months of holding became 21 rather than 63 trading days.
- Example 6: a 20-day price-low exit became a 20-day moving-average exit.
- Examples 18, 21, 23, 27, 31, 32, 36, 41, 57, 59, 65, and 70: monthly rebalance wording
  produced an invented monthly contribution plan and a false unsupported-DCA notice.
- Example 29: EMA dead-cross exit reused the wrong 1/20 pair instead of the stated 5/20 pair.
- Example 33: operating-cash-flow growth was given an unregistered `*_qoq` factor and omitted.
- Example 34: the ADX 20 exit threshold was put in `lookback_period` and omitted.
- Example 49: a valid MA buy phrase was mirrored into an unrequested sell condition; one run
  also said that phrase was not a moving-average condition. Another run invented an MA exit
  source quote not present in the user's sentence.
- Example 72: an unqualified 20-day moving average was changed to EMA.
- Example 12: five consecutive rising days were silently approximated as a five-day MA state.
  There is no equivalent consecutive-rise indicator in the current registry, so this phrase must
  remain explicitly unsupported instead of being simulated as another signal.

The interpreter prompt now distinguishes price lows from MA lines, inherited EMA pairs, ADX
thresholds from indicator periods, supported OCF growth, and SMA from explicit EMA. The quote
checker checks an invented, non-verbatim MA exit against the original sentence twice, without
presenting the invented quote as evidence. The primary parser requires a quoted contribution
amount before recovering a previously absent contribution plan, preserves an explicit unsupported
report over a conflicting MA approximation, and suppresses a false notice when an extra sell
condition merely repeats a valid buy quote. A 20-day low's quoted period is retained when the
quote checker reclassifies it as breakout.

Targeted local model reruns verified examples 4, 6, 18, 29, 33, 34, 49, and 72. Example 12 was
rerun and now reports its unsupported consecutive-rise phrase without substituting an MA signal.
In the final example-49 run, the independent source-only check removed the invented MA sell;
the remaining sell signal was MACD alone. Rejected model-authored quotes are not repeated in user
notices. The repository's frontend examples and engine indicator registry were not changed under
Boundary K.

Final validation: `KRX_ID= KRX_PW= HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
UV_CACHE_DIR=/tmp/simons-uv-cache uv run pytest backend/tests -q` returned **5372 passed,
5 skipped, 1 failed**. The remaining pre-existing failure is
`test_backfill_us_stocks.py::test_columns_match_korean_schema`: the Korean parquet sample has
five additional columns beginning with `fcf_margin`. The target interpreter, quote-check, and
parse-evidence tests passed before the full run. `git diff --check` passed. The local 81-case audit
is a model observation, not a deterministic guarantee that every future generation will be identical.

## Initial allocation mistaken for recurring contributions — 2026-09-28

Boundary K. The reported prompt assigns KRW 1,000,000 across market-cap ranks 1–10,
KRW 100,000 per company, and replaces departing constituents annually. The contribution
checker previously assumed every checked request was recurring accumulation, and its apply
step could only recover missing plans, never reject a first-pass invented plan. Consequently,
a correct independent negative answer still left the invented amount/period in place, and the
capability validator reported unsupported trading conditions combined with contributions.

Read-only production inspection found revision `fa17ec9e` running this exact biased prompt.
Both production and local dotenv configuration select `primary`, OpenRouter, and
`nvidia/nemotron-3-super-120b-a12b:free`; a model-name mismatch is not supported by this evidence.
The original production model response was not captured, so its precise first-pass output and
sampling/cache history remain unverified.

The checker now distinguishes initial allocation from recurring contributions. Only an explicit
initial-allocation verdict with a source-matching quote and three explicitly null plan fields
can remove an existing contribution amount/period on the creation path. Missing, invalid,
conflicting or failed verdicts preserve the first-pass plan; modification-only checks preserve
existing contributions. No regex interprets the request. The interpreter prompt also distinguishes
holding every member of a stated rank range from selecting a subset of a candidate universe.
Cache version 12 expires earlier parse responses. The auxiliary output budget includes the added
allocation evidence. Public response contracts, model selection and engine behavior are unchanged.

The regression initially failed (1 failed, 6 passed); after repair the focused contribution,
batch and cache tests passed (78 passed). These tests inject model verdicts; they do not guarantee
live-model interpretation or demonstrate a deployed fix. Changes have not been deployed.
The project plan, architecture and SRS were reviewed; this boundary-local record documents the
change without modifying Boundary G documents or pre-existing user edits.

Validation commands and results:
- `UV_CACHE_DIR=/tmp/simons-uv-cache uv run pytest backend/tests/test_contribution_allocation.py backend/tests/test_contributions.py backend/tests/test_check_batch.py backend/tests/test_nl_cache.py -q`: 78 passed.
- `KRX_ID= KRX_PW= HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 UV_CACHE_DIR=/tmp/simons-uv-cache uv run pytest backend/tests -q`: 5350 passed, 6 skipped, 55 sandbox-blocked localhost DB errors, 1 failed.
- The same environment with `uv run pytest backend/tests --lf -q`, allowing local DB access: 55 passed, 1 failed. The sole remaining failure is the previously recorded `test_backfill_us_stocks.py::test_columns_match_korean_schema` data-column mismatch, unrelated to strategy parsing.
- Scoped `git diff --check` passed. Test-generated fixture changes cleaned themselves up; pre-existing work was preserved.
