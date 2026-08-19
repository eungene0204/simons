"""백테스트 결과 동일성 게이트 — 성능 경로(세션 캐시·Phase1 프로세스 풀·창 병렬)가 답을 바꾸지 않는지
실제 데이터로 전수 대조한다 (FR-BT-049c 안전장치).

같은 전략을 네 경로로 돌려 결과(거래·자산곡선·지표·경고·리밸런싱 비교표)를 바이트 단위로 비교한다.
  A  baseline : 세션 없음 · 스레드 경로(BACKTEST_PHASE1_WORKERS=1)
  B  session  : 최적화 세션 안에서 2회 연속(1회차=미적중, 2회차=캐시 적중) — 둘 다 A와 같아야 함
  C  pool     : Phase1 프로세스 풀(BACKTEST_PHASE1_WORKERS=N) · 세션 없음
  D  pool+ses : 풀 + 세션 2회
워크포워드(--wfa)는 순차 창(WALK_FORWARD_WORKERS=1) vs 병렬 창(N)을 대조한다.

비교 규칙
- timing 제거. warnings·resolution_logs는 원래부터 스레드 완료 순서에 따라 순서만 바뀌므로 정렬 후 비교.
- rebalanceComparison은 세션 안에서는 의도적으로 만들지 않으므로(결과 화면 전용) A↔C에서만 비교하고
  B/D에서는 제외한다.
- 거래 0건 전략은 '거래 없음'으로 따로 표시한다(같아도 검증력이 약하다).

실행:  python scripts/qa_backtest_equivalence.py [--workers 4] [--wfa] [--only rsi,ma] [--symbols 120]
종료 코드: 불일치가 하나라도 있으면 1.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("POLARS_MAX_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


# ── 전략 픽스처 ─────────────────────────────────────────────────────

def _cond(cid: str, ctype: str = "entry", **params) -> Dict[str, Any]:
    return {"id": cid, "type": ctype, "params": params}


def _grp(*conds, logic: str = "AND") -> Dict[str, Any]:
    return {"logic": logic, "conditions": list(conds)}


def _risk(**kw) -> Dict[str, Any]:
    base = {"init_cash": 10_000_000, "position_size_pct": 20, "max_positions": 5,
            "stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None,
            "max_holding_days": None, "rebalancing_period": "none", "allocation_type": "equal"}
    base.update(kw)
    return base


def build_strategies(symbols: List[str], kospi200_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """이름 → 요청. 지표·재무·랭킹·리밸런싱·리스크·체결·기간·유니버스를 고루 덮는다."""
    common = {"period": "5Y", "options": {"fee_rate": 0.00015, "slippage_rate": 0.001, "execution_type": "next_open"}}
    S: Dict[str, Dict[str, Any]] = {}

    def add(name, entry, exit_, risk=None, **extra):
        req = {"symbols": symbols, **copy.deepcopy(common), "entry": entry, "exit": exit_, "risk": risk or _risk()}
        req.update(extra)
        S[name] = req

    add("rsi", _grp(_cond("rsi", period=14, operator="<", value=30)),
        _grp(_cond("rsi", "exit", period=14, operator=">", value=70)), _risk(stop_loss_pct=7))
    add("rsi_rebound_trailing", _grp(_cond("rsi", period=10, value=30, mode="rebound")),
        _grp(_cond("rsi", "exit", period=10, value=70, mode="rebound", signalType="sell")),
        _risk(trailing_stop_pct=8, max_positions=8))
    add("ma_cross", _grp(_cond("ma_crossover", shortMA=5, longMA=20)),
        _grp(_cond("ma_crossover", "exit", shortMA=5, longMA=20, signalType="sell")), _risk(max_positions=10))
    add("ma_cross_same_close_hold", _grp(_cond("ma_crossover", shortMA=20, longMA=60)),
        _grp(_cond("ma_crossover", "exit", shortMA=20, longMA=60, signalType="sell")),
        _risk(max_holding_days=40, take_profit_pct=15),
        options={"fee_rate": 0.0003, "slippage_rate": 0.0, "execution_type": "same_close"})
    add("macd_default", _grp(_cond("macd", signalType="buy")), _grp(_cond("macd", "exit", signalType="sell")))
    add("macd_param_zero", _grp(_cond("macd", fastPeriod=10, slowPeriod=20, signalPeriod=5, mode="zero")),
        _grp(_cond("macd", "exit", fastPeriod=10, slowPeriod=20, signalPeriod=5, mode="zero", signalType="sell")))
    add("bollinger", _grp(_cond("bollinger_bands", period=20, stdDev=2.0)),
        _grp(_cond("bollinger_bands", "exit", period=20, stdDev=2.0, signalType="sell")), _risk(stop_loss_pct=5))
    add("bollinger_custom_std", _grp(_cond("bollinger_bands", period=30, stdDev=1.5)),
        _grp(_cond("bollinger_bands", "exit", period=30, stdDev=1.5, signalType="sell")))
    add("breakout_52w", _grp(_cond("breakout", lookbackPeriod=252)),
        _grp(_cond("breakout", "exit", lookbackPeriod=60, signalType="sell")), _risk(stop_loss_pct=10, max_positions=10))
    add("volume_spike_stoch", _grp(_cond("volume_spike", period=20), _cond("stochastic", period=14)),
        _grp(_cond("stochastic", "exit", period=14, signalType="sell")))
    add("cci_adx_wr", _grp(_cond("cci", period=20, operator="<", value=-100), _cond("adx", operator=">", value=20)),
        _grp(_cond("williams_r", "exit", period=14, operator=">", value=-20)))
    add("mfi_roc_vol", _grp(_cond("mfi", period=14, operator="<", value=25), _cond("volatility", period=60, operator="<", value=60)),
        _grp(_cond("roc", "exit", period=12, operator=">", value=8)))
    add("ema_rsi_or", _grp(_cond("ema", shortPeriod=10, longPeriod=30), _cond("rsi", period=14, operator="<", value=40), logic="OR"),
        _grp(_cond("ema", "exit", shortPeriod=10, longPeriod=30, signalType="sell")))
    add("value_per_pbr", _grp(_cond("per", operator="<", value=10), _cond("pbr", operator="<", value=1.0), _cond("rsi", period=14, operator="<", value=45)),
        _grp(_cond("rsi", "exit", period=14, operator=">", value=65)), _risk(max_positions=10, stop_loss_pct=12))
    add("quality_roe_debt", _grp(_cond("roe", operator=">", value=10), _cond("debt_ratio", operator="<", value=100), _cond("ma_crossover", shortMA=5, longMA=20)),
        _grp(_cond("ma_crossover", "exit", shortMA=5, longMA=20, signalType="sell")))
    add("trading_value_marketcap", _grp(_cond("trading_value", operator=">=", value=50), _cond("market_cap", operator=">", value=5000), _cond("rsi", period=14, operator="<", value=35)),
        _grp(_cond("rsi", "exit", period=14, operator=">", value=65)))
    add("momentum_monthly", _grp(), _grp(),
        _risk(ranking_metric="return", ranking_lookback_days=120, ranking_direction="top", max_positions=10, rebalancing_period="monthly", position_size_pct=10))
    add("momentum_pct_quarterly", _grp(), _grp(),
        _risk(ranking_metric="return", ranking_lookback_days=60, ranking_direction="top", max_positions=None, max_positions_pct=10, rebalancing_period="quarterly", position_size_pct=10))
    add("lowvol_weekly_stop", _grp(_cond("rsi", period=14, operator="<", value=60)), _grp(),
        _risk(ranking_metric="volatility", ranking_lookback_days=60, ranking_direction="bottom", max_positions=8, rebalancing_period="weekly", stop_loss_pct=8))
    add("composite_ranking", _grp(), _grp(),
        _risk(ranking_metric="composite", ranking_components=[{"metric": "return", "direction": "top", "lookback_days": 120}, {"metric": "pbr", "direction": "bottom"}],
              max_positions=10, rebalancing_period="monthly", position_size_pct=10))
    add("quantile_groups_per", _grp(), _grp(),
        _risk(ranking_metric="per", ranking_direction="bottom", ranking_quantile_groups=5, max_positions=None, rebalancing_period="quarterly", position_size_pct=5))
    add("no_cap_signal_only", _grp(_cond("rsi", period=14, operator="<", value=30)),
        _grp(_cond("rsi", "exit", period=14, operator=">", value=70)),
        _risk(max_positions=None, position_size_pct=10, skip_risk_management=True))
    add("dividends_total_return", _grp(_cond("ma_crossover", shortMA=10, longMA=50)),
        _grp(_cond("ma_crossover", "exit", shortMA=10, longMA=50, signalType="sell")),
        options={"fee_rate": 0.00015, "slippage_rate": 0.001, "execution_type": "next_open", "total_return": True})
    add("explicit_dates_2y", _grp(_cond("rsi", period=14, operator="<", value=35)),
        _grp(_cond("rsi", "exit", period=14, operator=">", value=65)),
        period="full", startDate="2022-03-02", endDate="2024-02-29")
    add("kospi200_pit_universe", _grp(_cond("rsi", period=14, operator="<", value=30)),
        _grp(_cond("rsi", "exit", period=14, operator=">", value=70)), symbols=kospi200_ids, universe_id="kospi200")
    add("etf_universe", _grp(_cond("ma_crossover", shortMA=20, longMA=60)),
        _grp(_cond("ma_crossover", "exit", shortMA=20, longMA=60, signalType="sell")),
        symbols=[], universe_id="etf")
    add("sector_semiconductor", _grp(_cond("rsi", period=14, operator="<", value=35)),
        _grp(_cond("rsi", "exit", period=14, operator=">", value=65)),
        symbols=kospi200_ids, universe_id="kospi200", sector="반도체")
    add("single_asset", _grp(_cond("ma_crossover", shortMA=5, longMA=20)),
        _grp(_cond("ma_crossover", "exit", shortMA=5, longMA=20, signalType="sell")),
        _risk(max_positions=1, position_size_pct=100), symbols=[symbols[0]], universe_id=None, backtest_mode="single")
    return S


# ── 비교 ────────────────────────────────────────────────────────────

def comparable(res: Dict[str, Any], *, drop_rebalance: bool) -> str:
    r = dict(res)
    r.pop("timing", None)
    if drop_rebalance:
        r.pop("rebalanceComparison", None)
    r["warnings"] = sorted(r.get("warnings") or [])
    r["resolution_logs"] = sorted(json.dumps(x, sort_keys=True, ensure_ascii=False) for x in (r.get("resolution_logs") or []))
    return json.dumps(r, sort_keys=True, default=str, ensure_ascii=False)


def first_diff(a: str, b: str) -> str:
    """두 직렬화 문자열의 첫 차이 지점 주변을 돌려준다(원인 파악용)."""
    n = min(len(a), len(b))
    i = next((k for k in range(n) if a[k] != b[k]), n)
    lo = max(0, i - 120)
    return f"@{i}: A=…{a[lo:i+80]!r} | B=…{b[lo:i+80]!r}"


def run_quiet(engine, req):
    with contextlib.redirect_stdout(io.StringIO()):
        return engine.run_backtest(copy.deepcopy(req))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=max(2, min((os.cpu_count() or 2) - 1, 8)))
    ap.add_argument("--symbols", type=int, default=120, help="커스텀 유니버스 종목 수(KOSPI200 앞에서부터)")
    ap.add_argument("--only", type=str, default="", help="쉼표로 구분한 전략 이름 부분 일치")
    ap.add_argument("--wfa", action="store_true", help="워크포워드 순차/병렬 창 대조도 실행")
    ap.add_argument("--json", type=str, default="", help="결과 JSON 저장 경로")
    args = ap.parse_args()

    from backtest_engine import BacktestEngine
    from engine import phase1_pool

    kospi200 = json.load(open(ROOT / "data" / "kospi200-cache.json"))["symbols"]
    symbols = kospi200[: args.symbols]
    strategies = build_strategies(symbols, kospi200)
    if args.only:
        keys = [k.strip() for k in args.only.split(",") if k.strip()]
        strategies = {n: r for n, r in strategies.items() if any(k in n for k in keys)}

    engine = BacktestEngine()
    report: List[Dict[str, Any]] = []
    failures = 0
    t_all = time.time()
    print(f"[EQ] {len(strategies)}개 전략 · 종목 {len(symbols)} · 풀 워커 {args.workers}", flush=True)

    for name, req in strategies.items():
        row: Dict[str, Any] = {"strategy": name}
        t0 = time.time()
        try:
            # A baseline
            os.environ["BACKTEST_PHASE1_WORKERS"] = "1"
            base_raw = run_quiet(engine, req)
            base = comparable(base_raw, drop_rebalance=False)
            base_no_rc = comparable(base_raw, drop_rebalance=True)
            row["trades"] = int(base_raw.get("trades") or 0)

            # B session ×2 (thread path)
            with engine.optimization_session():
                s1 = comparable(run_quiet(engine, req), drop_rebalance=True)
                s2 = comparable(run_quiet(engine, req), drop_rebalance=True)
            row["session_1st"] = s1 == base_no_rc
            row["session_2nd_hit"] = s2 == base_no_rc

            # C pool
            os.environ["BACKTEST_PHASE1_WORKERS"] = str(args.workers)
            os.environ["BACKTEST_PHASE1_POOL_MIN_SYMBOLS"] = "1"
            pool_raw = run_quiet(engine, req)
            row["pool"] = comparable(pool_raw, drop_rebalance=False) == base
            if not row["pool"]:
                row["pool_diff"] = first_diff(base, comparable(pool_raw, drop_rebalance=False))

            # D pool + session ×2
            with engine.optimization_session():
                p1 = comparable(run_quiet(engine, req), drop_rebalance=True)
                p2 = comparable(run_quiet(engine, req), drop_rebalance=True)
            row["pool_session_1st"] = p1 == base_no_rc
            row["pool_session_2nd_hit"] = p2 == base_no_rc
            for k, v in (("session_1st", s1), ("session_2nd_hit", s2), ("pool_session_1st", p1), ("pool_session_2nd_hit", p2)):
                if not row[k]:
                    row[k + "_diff"] = first_diff(base_no_rc, v)
            row["ok"] = all(row[k] for k in ("session_1st", "session_2nd_hit", "pool", "pool_session_1st", "pool_session_2nd_hit"))
        except Exception as exc:  # 한 전략의 예외는 그 행만 실패로
            row["ok"] = False
            row["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            os.environ["BACKTEST_PHASE1_WORKERS"] = "1"
        row["sec"] = round(time.time() - t0, 1)
        if not row["ok"]:
            failures += 1
        mark = "OK " if row["ok"] else "FAIL"
        note = " (거래 없음)" if row.get("trades", 0) == 0 else ""
        print(f"[EQ] {mark} {name:28s} trades={row.get('trades', '-'):>5} {row['sec']:5.1f}s{note}"
              + (f"  {row.get('error') or ''}" if not row["ok"] else ""), flush=True)
        for k in ("pool_diff", "session_1st_diff", "session_2nd_hit_diff", "pool_session_1st_diff", "pool_session_2nd_hit_diff"):
            if k in row:
                print(f"       {k}: {row[k]}", flush=True)
        report.append(row)

    if args.wfa:
        from engine.walk_forward import WalkForwardAnalyzer
        os.environ["BACKTEST_PHASE1_WORKERS"] = "1"
        for name in ("rsi", "ma_cross", "momentum_monthly"):
            if name not in strategies:
                continue
            req = strategies[name]
            ranges = ({"risk.stop_loss_pct": [5, 10]} if name != "momentum_monthly"
                      else {"risk.ranking_lookback_days": [60, 120]})
            row = {"strategy": f"wfa:{name}"}
            t0 = time.time()
            try:
                os.environ["WALK_FORWARD_WORKERS"] = "1"
                with contextlib.redirect_stdout(io.StringIO()):
                    seq = WalkForwardAnalyzer(engine).analyze(base_request=copy.deepcopy(req), ranges=ranges, method="grid", n_splits=3, train_pct=0.6)
                os.environ["WALK_FORWARD_WORKERS"] = str(min(3, args.workers))
                with contextlib.redirect_stdout(io.StringIO()):
                    par = WalkForwardAnalyzer(engine).analyze(base_request=copy.deepcopy(req), ranges=ranges, method="grid", n_splits=3, train_pct=0.6)
                a, b = json.dumps(seq, sort_keys=True, default=str), json.dumps(par, sort_keys=True, default=str)
                row["ok"] = a == b and seq.get("status") == "ok"
                row["status"] = seq.get("status")
                if a != b:
                    row["diff"] = first_diff(a, b)
            except Exception as exc:
                row["ok"] = False
                row["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                os.environ["WALK_FORWARD_WORKERS"] = "1"
            row["sec"] = round(time.time() - t0, 1)
            if not row["ok"]:
                failures += 1
            print(f"[EQ] {'OK ' if row['ok'] else 'FAIL'} {row['strategy']:28s} status={row.get('status')} {row['sec']:5.1f}s"
                  + (f"  {row.get('error') or row.get('diff') or ''}" if not row["ok"] else ""), flush=True)
            report.append(row)

    phase1_pool.shutdown_all()
    total = len(report)
    print(f"[EQ] 완료: {total - failures}/{total} 동일 · 불일치 {failures} · {time.time() - t_all:.0f}s", flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
