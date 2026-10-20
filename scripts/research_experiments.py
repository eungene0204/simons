"""연구노트 실험 모음 — 설계는 실행 전에 고정하고 결과는 있는 그대로 기록한다.

공통 조건: KOSPI200 시점별 구성(일별 시가총액 상위 200), 수수료 0.015%·슬리피지 0.1%, 종목당 10%·최대 10종목,
기본 체결=다음 거래일 시가. 실험마다 바꾸는 값은 하나(또는 한 묶음)뿐이다.
  A  체결 시점        — 신호 당일 종가(same_close) vs 다음 거래일 시가(next_open)
  B  손절·트레일링    — 손절 5/10/15/20% · 트레일링 10/20% vs 없음
  C  이동평균 기간    — 단기×장기 16조합을 학습(2020~2022)·검증(2023~2025) 구간으로 나눠 순위 비교
  D  리밸런싱 주기    — 120일 수익률 상위 10종목 랭킹 규칙, 주간·월간·분기·연간 × 슬리피지 0%/0.1%
  E  구간 민감도      — 같은 규칙을 달력 연도(2020~2025)별로 1년씩
  K  비교 기준        — 같은 구간의 KOSPI 지수(가격지수, 배당 제외) 수익률. 노트가 인용하는 지수 수치의 원천

실행:  cd backend && uv run --frozen python ../scripts/research_experiments.py --exp A --json <경로>
(거래 비용 민감도 노트는 research_cost_sensitivity.py)
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
FEE, SLIP = 0.00015, 0.001
RULES = {"slow_20_60": (20, 60), "fast_5_20": (5, 20)}
KEEP = ("cagr", "totalReturn", "maxDrawdown", "trades", "winRate", "avgHoldingDays", "sharpe")


def _grp(*conds):
    return {"logic": "AND", "conditions": list(conds)}


def _cond(ctype, **params):
    return {"id": "ma_crossover", "type": ctype, "params": params}


def risk(**kw):
    base = {"init_cash": 10_000_000, "position_size_pct": 10, "max_positions": 10, "stop_loss_pct": None,
            "take_profit_pct": None, "trailing_stop_pct": None, "max_holding_days": None,
            "rebalancing_period": "none", "allocation_type": "equal"}
    base.update(kw)
    return base


def ma_request(universe, s, l, *, start=START, end=END, execution="next_open", slip=SLIP, **risk_kw):
    return {
        "symbols": universe, "universe_id": "kospi200", "period": "full", "startDate": start, "endDate": end,
        "options": {"fee_rate": FEE, "slippage_rate": slip, "execution_type": execution},
        "entry": _grp(_cond("entry", shortMA=s, longMA=l)),
        "exit": _grp(_cond("exit", shortMA=s, longMA=l, signalType="sell")),
        "risk": risk(**risk_kw),
    }


def momentum_request(universe, period, slip):
    return {
        "symbols": universe, "universe_id": "kospi200", "period": "full", "startDate": START, "endDate": END,
        "options": {"fee_rate": FEE, "slippage_rate": slip, "execution_type": "next_open"},
        "entry": {"logic": "AND", "conditions": []}, "exit": {"logic": "AND", "conditions": []},
        "risk": risk(ranking_metric="return", ranking_lookback_days=120, ranking_direction="top",
                     rebalancing_period=period),
    }


def plan(exp, universe):
    """(라벨 dict, 요청) 목록."""
    runs = []
    if exp == "A":
        for rule, (s, l) in RULES.items():
            for ex in ("same_close", "next_open"):
                runs.append(({"rule": rule, "execution": ex}, ma_request(universe, s, l, execution=ex)))
    elif exp == "B":
        variants = [("none", {}), ("stop5", {"stop_loss_pct": 5}), ("stop10", {"stop_loss_pct": 10}),
                    ("stop15", {"stop_loss_pct": 15}), ("stop20", {"stop_loss_pct": 20}),
                    ("trail10", {"trailing_stop_pct": 10}), ("trail20", {"trailing_stop_pct": 20})]
        for rule, (s, l) in RULES.items():
            for name, kw in variants:
                runs.append(({"rule": rule, "exit_rule": name}, ma_request(universe, s, l, **kw)))
    elif exp == "C":
        windows = {"train": ("2020-01-02", "2022-12-30"), "test": ("2023-01-02", "2025-12-30")}
        for s in (5, 10, 20, 30):
            for l in (40, 60, 90, 120):
                for wname, (a, b) in windows.items():
                    runs.append(({"short": s, "long": l, "window": wname}, ma_request(universe, s, l, start=a, end=b)))
    elif exp == "D":
        for period in ("weekly", "monthly", "quarterly", "yearly"):
            for slip in (0.0, SLIP):
                runs.append(({"period": period, "slippage_rate": slip}, momentum_request(universe, period, slip)))
    elif exp == "E":
        for year in range(2020, 2026):
            a = f"{year}-01-02"
            b = "2025-12-30" if year == 2025 else f"{year}-12-30"
            for rule, (s, l) in RULES.items():
                runs.append(({"rule": rule, "year": year}, ma_request(universe, s, l, start=a, end=b)))
    else:
        raise SystemExit(f"unknown experiment {exp}")
    return runs


def kospi_reference():
    """노트가 인용하는 KOSPI 지수(가격지수) 수치 — data/index/KOSPI.parquet 종가, 구간 첫·마지막 거래일 종가 기준."""
    import pyarrow.parquet as pq

    close = pq.read_table(ROOT / "data" / "index" / "KOSPI.parquet").to_pandas().set_index("date").sort_index()["close"]

    def window(a, b):
        s = close[(close.index >= a) & (close.index <= b)]
        years = (s.index[-1] - s.index[0]).days / 365.25
        total = s.iloc[-1] / s.iloc[0] - 1
        return {"from": str(s.index[0].date()), "to": str(s.index[-1].date()),
                "totalReturn": total * 100, "cagr": ((1 + total) ** (1 / years) - 1) * 100}

    out = {"full": window(START, END), "train": window("2020-01-02", "2022-12-30"),
           "test": window("2023-01-02", "2025-12-30")}
    for y in range(2020, 2026):
        out[str(y)] = window(f"{y}-01-02", END if y == 2025 else f"{y}-12-30")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    if args.exp == "K":
        ref = kospi_reference()
        for k, v in ref.items():
            print(f"[K] {k} {v['from']}~{v['to']} total={v['totalReturn']:.1f}% cagr={v['cagr']:.1f}%")
        if args.json:
            Path(args.json).write_text(json.dumps(ref, ensure_ascii=False), encoding="utf-8")
        return 0

    from backtest_engine import BacktestEngine
    from engine.version import ENGINE_VERSION

    universe = json.load(open(ROOT / "data" / "kospi200-cache.json"))["symbols"]
    engine = BacktestEngine()
    rows = []
    for label, req in plan(args.exp, universe):
        t0 = time.time()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                res = engine.run_backtest(copy.deepcopy(req))
            slim = {k: res.get(k) for k in KEEP}
            slim["warnings"] = [w for w in (res.get("warnings") or []) if "거래 없음" in w or "0거래" in w]
        except Exception as exc:  # 실패는 숨기지 않고 행에 남긴다
            slim = {"error": repr(exc)}
        rows.append({"label": label, "result": slim})
        print(f"[{args.exp}] {label} {slim.get('cagr')} trades={slim.get('trades')} {time.time()-t0:.0f}s", flush=True)
    out = {"exp": args.exp, "engine_version": ENGINE_VERSION, "start": START, "end": END, "fee_rate": FEE,
           "slippage_rate": SLIP, "rows": rows}
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
