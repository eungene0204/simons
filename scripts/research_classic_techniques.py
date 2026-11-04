"""연구노트 — 유명 매매기법 9개, KOSPI 최근 3년 백테스트.

AEO 설계서 3단계(2026-11-04). 기법마다 규칙을 실행 전에 고정하고(아래 RULES), 앱과 같은 경로
(ParsedStrategy → strategy_converter.to_backtest_request → BacktestEngine.run_backtest)로 계산한다.
공통: KOSPI(시점별 구성·상장폐지 포함), 기간 2023-11-03~2026-11-03(최근 3년, 날짜 고정), 시작 자금 1,000만 원,
다음 거래일 시가 체결, 수수료 0.015%·슬리피지 0.05%(사용자 결정), 거래세는 시행일 기준 법정 세율.
래리 윌리엄스 변동성 돌파는 장중 돌파 가격 체결이 필요해 일봉 엔진으로 표현할 수 없어 제외했다.
결과 JSON은 연구노트 숫자의 원천이다 — 글에는 이 JSON의 값을 그대로 옮긴다.

실행:  cd backend && uv run --frozen python ../scripts/research_classic_techniques.py --json <경로> [--only <이름>]
       시작일 민감도: 같은 명령에 --starts 2023-11-06,2023-11-07,... (같은 JSON의 sensitivity에 덧붙인다)
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# 날짜를 고정한다 — 실행일(11-04)에는 종목 일부만 당일 봉이 있어 마지막 날 '데이터 종료' 강제 정산이 섞였다.
START, END = "2023-11-03", "2026-11-03"
COMMON = {"universe": ["KOSPI"], "backtest_period": "3y", "backtest_start_date": START, "backtest_end_date": END,
          "initial_capital": 10_000_000,
          "fee_rate": 0.015, "slippage_rate": 0.05, "execution_timing": "next_open"}


def rules():
    from engine.nl_parser import FundamentalFilter as F, RankingComponent as R, TechnicalSignal as T

    def ma(signal_type, short, long_, mode=None):
        return T(indicator="ma_crossover", signal_type=signal_type, short_period=short, long_period=long_, mode=mode)

    return {
        "golden_cross_5_20": dict(
            max_positions=10,
            entry_signals=[ma("buy", 5, 20)], exit_signals=[ma("sell", 5, 20)]),
        "ma_alignment_5_20_60": dict(
            max_positions=10, entry_logic="AND",
            entry_signals=[ma("buy", 5, 20, "above"), ma("buy", 20, 60, "above")],
            exit_signals=[ma("sell", 5, 20)]),
        "rsi_30_70": dict(
            max_positions=10,
            entry_signals=[T(indicator="rsi", signal_type="buy", period=14, operator="<=", value=30)],
            exit_signals=[T(indicator="rsi", signal_type="sell", period=14, operator=">=", value=70)]),
        "macd_signal_cross": dict(
            max_positions=10,
            entry_signals=[T(indicator="macd", signal_type="buy", mode="crossover")],
            exit_signals=[T(indicator="macd", signal_type="sell", mode="crossover")]),
        "bollinger_lower": dict(
            max_positions=10,
            entry_signals=[T(indicator="bollinger_bands", signal_type="buy")],
            exit_signals=[T(indicator="bollinger_bands", signal_type="sell")]),
        "high_52w_hold_3m": dict(
            max_positions=10, hold_period_days=63,
            entry_signals=[T(indicator="breakout", signal_type="buy", lookback_period=252)], exit_signals=[]),
        "dual_momentum_12m": dict(
            max_positions=10, rebalancing_period="monthly",
            ranking_metric="return", ranking_lookback_days=252, ranking_direction="top",
            absolute_momentum_threshold_pct=0, entry_signals=[], exit_signals=[]),
        "low_per_pbr_20": dict(
            max_positions=20, rebalancing_period="quarterly",
            fundamental_filters=[F(metric="per", operator=">", value=0), F(metric="pbr", operator=">", value=0)],
            ranking_metric="composite",
            ranking_components=[R(metric="per", direction="bottom"), R(metric="pbr", direction="bottom")],
            entry_signals=[], exit_signals=[]),
        "magic_formula_20": dict(
            max_positions=20, rebalancing_period="quarterly",
            fundamental_filters=[F(metric="ev_ebit", operator=">", value=0)],
            ranking_metric="composite",
            ranking_components=[R(metric="roic", direction="top"), R(metric="ev_ebit", direction="bottom")],
            entry_signals=[], exit_signals=[]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--only", default="", help="규칙 이름 부분 일치")
    ap.add_argument("--starts", default="",
                    help="시작일 민감도: 쉼표로 구분한 시작일마다 요약 지표만 sensitivity에 저장(종료일 고정)")
    args = ap.parse_args()

    from backtest_engine import BacktestEngine
    from engine.nl_parser import ParsedStrategy
    from engine.strategy_converter import to_backtest_request
    from engine.version import ENGINE_VERSION

    out_path = Path(args.json)
    out = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {"rows": {}}
    out["engine_version"] = ENGINE_VERSION
    if args.starts:
        # 10종목만 들고 넓은 유니버스에서 고르는 규칙은 첫날 산 종목에 따라 경로가 갈린다 — 시작일만 바꿔 범위를 잰다.
        sens = out.setdefault("sensitivity", {})
        for start in args.starts.split(","):
            for name, spec in rules().items():
                if args.only and args.only not in name:
                    continue
                req = to_backtest_request(ParsedStrategy(**{**COMMON, "backtest_start_date": start}, **spec))
                with contextlib.redirect_stdout(io.StringIO()):
                    res = BacktestEngine().run_backtest(copy.deepcopy(req))
                sens.setdefault(start, {})[name] = {k: res.get(k) for k in ("totalReturn", "cagr", "maxDrawdown", "trades")}
                out_path.write_text(json.dumps(out, ensure_ascii=False, default=str), encoding="utf-8")
                print(f"[{start} {name}] ret={res.get('totalReturn'):.1f} cagr={res.get('cagr'):.1f}", flush=True)
        return 0
    for name, spec in rules().items():
        if args.only and args.only not in name:
            continue
        strategy = ParsedStrategy(**COMMON, **spec)
        req = to_backtest_request(strategy)
        t0 = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            res = BacktestEngine().run_backtest(copy.deepcopy(req))
        out["rows"][name] = {
            "request": {k: v for k, v in req.items() if k != "symbols"},
            "result": res,
            "seconds": round(time.time() - t0),
        }
        # 규칙마다 저장한다 — 중간에 멈춰도 앞선 결과가 남는다.
        out_path.write_text(json.dumps(out, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"[{name}] trades={res.get('trades')} cagr={res.get('cagr')} mdd={res.get('maxDrawdown')} "
              f"{time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
