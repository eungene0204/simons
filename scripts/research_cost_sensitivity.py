"""연구노트 — 거래 비용 민감도 실험.

같은 매매 규칙·같은 기간·같은 유니버스(KOSPI200 시점별 구성)에서 슬리피지만 바꿔 가며 결과가 어떻게 달라지는지
계산한다. 규칙은 회전율이 다른 두 가지(느린 20/60·빠른 5/20 이동평균 교차)이고, 수수료와 매도 거래세는 고정이다.
결과 JSON은 연구노트(`lib/notes/notes.ts`)의 숫자 원천이다 — 글에는 이 JSON의 값을 그대로 옮긴다.

실행:  cd backend && uv run --frozen python ../scripts/research_cost_sensitivity.py --json <경로>
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

START, END = "2020-01-02", "2025-12-30"
FEE_RATE = 0.00015  # 수수료 0.015% (매수·매도 각각)
SLIPPAGE_LEVELS = [0.0, 0.0005, 0.001, 0.002, 0.004]  # 0%, 0.05%, 0.1%, 0.2%, 0.4%
RULES = {"slow_20_60": (20, 60), "fast_5_20": (5, 20)}


def build_request(kospi200, short_ma, long_ma, slippage):
    entry = {"logic": "AND", "conditions": [{"id": "ma_crossover", "type": "entry",
                                              "params": {"shortMA": short_ma, "longMA": long_ma}}]}
    exit_ = {"logic": "AND", "conditions": [{"id": "ma_crossover", "type": "exit",
                                              "params": {"shortMA": short_ma, "longMA": long_ma, "signalType": "sell"}}]}
    return {
        "symbols": kospi200, "universe_id": "kospi200", "period": "full", "startDate": START, "endDate": END,
        "options": {"fee_rate": FEE_RATE, "slippage_rate": slippage, "execution_type": "next_open"},
        "entry": entry, "exit": exit_,
        "risk": {"init_cash": 10_000_000, "position_size_pct": 10, "max_positions": 10,
                 "stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None,
                 "max_holding_days": None, "rebalancing_period": "none", "allocation_type": "equal"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--only", default="", help="규칙 이름 부분 일치")
    ap.add_argument("--levels", type=int, default=len(SLIPPAGE_LEVELS))
    args = ap.parse_args()

    from backtest_engine import BacktestEngine
    from engine.version import ENGINE_VERSION

    kospi200 = json.load(open(ROOT / "data" / "kospi200-cache.json"))["symbols"]
    engine = BacktestEngine()
    rows = []
    for name, (s, l) in RULES.items():
        if args.only and args.only not in name:
            continue
        for slip in SLIPPAGE_LEVELS[: args.levels]:
            t0 = time.time()
            with contextlib.redirect_stdout(io.StringIO()):
                res = engine.run_backtest(copy.deepcopy(build_request(kospi200, s, l, slip)))
            rows.append({"rule": name, "slippage_rate": slip, "result": res})
            print(f"[{name}] slip={slip:.4%} trades={res.get('trades')} "
                  f"cagr={res.get('cagr')} mdd={res.get('maxDrawdown')} {time.time()-t0:.0f}s", flush=True)
    out = {"engine_version": ENGINE_VERSION, "start": START, "end": END, "fee_rate": FEE_RATE, "rows": rows}
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
