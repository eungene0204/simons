# Backtest Core audit — 2026-09-24–25

## Scope

Boundary C: Backtest Core. Reviewed loading, indicators, signals, simulation,
and result handling. Production edits affect only `Simulator._run_once`.
Reviewed `docs/PROJECT_PLAN.md`, `docs/software_architecture.md`, and `docs/SRS.md`;
they belong to Boundary G, so work details are recorded here. API contracts are unchanged.

## Fixed: final-bar execution looks back to an elapsed open

Final-bar risk triggers (including partial take profits) in `next_open` mode
previously filled at that day's already elapsed open. Example: 100 shares bought
at 100, final-day open 100 / close 80, 10% stop. The engine reported 10,000 after
a retroactive sell instead of valuing the open position at 8,000.
Both paths now wait for a later tradable bar; unfilled positions retain final-close valuation.
Ten regression cases cover stops, take profits, trailing stops, holding limits,
and partial take profits in both execution modes. Three-bar orders and values
must match the first three bars of an extended window. Tests also verify later
fills, open status, execution prices, and absence of false executed-exit reasons.

## Validation

Commands use `UV_CACHE_DIR=/tmp/simons-uv-cache` because the default uv cache is
outside the writable sandbox, and `uv run --offline` uses installed dependencies.

- Before the fix: `uv run --offline pytest backend/tests/test_simulator_validation.py -k final_bar -q`
  produced 5 failures (`next_open`) and 5 passes (`same_close`).
- After the fix: `uv run --offline pytest backend/tests/test_simulator_validation.py -q`
  passed all 16 tests.
- Expanded engine validation command:

```sh
UV_CACHE_DIR=/tmp/simons-uv-cache uv run --offline pytest \
  backend/tests/test_engine_simulator.py backend/tests/test_simulator_ranking.py \
  backend/tests/test_simulator_validation.py backend/tests/test_result_handler.py \
  backend/tests/test_engine_signals.py backend/tests/test_indicators.py \
  backend/tests/test_engine_loader.py backend/tests/test_loader_preprocess.py \
  backend/tests/test_loader_etf_skip.py backend/tests/test_execution_delay.py \
  backend/tests/test_lookahead_no_prelisting_trades.py backend/tests/test_transaction_tax.py \
  backend/tests/test_dividends.py backend/tests/test_competitive_gap_v16_28.py \
  backend/tests/test_backtest_engine.py -q
```

Final result: **215 passed**. Initially five failures also reproduced with the original
`HEAD` simulator: Korean fixtures used US-style tickers and top-N patched an obsolete
constant. Fixtures now use six-digit common-stock codes ending in zero and patch
`_INDEX_UNIVERSES`. Existing assertions remain intact; integration tests pass 12/12.

The required `uv run --offline pytest backend/tests` collected 5,349 tests but stopped
with two collection errors: `test_sync_data_status.py` and
`test_sync_fundamental_enrichment_gate.py` import `pykrx`, whose KRX DNS lookup fails.

A diagnostic `--continue-on-collection-errors -q` run was interrupted after
2,041 passes, 6 failures, 5 skips, 26 errors. Five failures are fixed above;
`test_columns_match_korean_schema` finds five extra local Korean parquet columns.
Errors comprise two KRX imports and 24 database setups (sandbox denies PostgreSQL access).
The session exited; this is not a completed full-suite result.

## Remaining scope

Real-provider data, remote worker equivalence, parquet schema compatibility, and
database-dependent tests remain unverified. Stored backtests are not recalculated.
