"""
AI '선택적 청산' 전략의 워크포워드/약세장 검증.

이전 실험(experiment_ai_auxiliary.py)은 단일 3Y 강세장 구간이라 편향이 있었다.
여기서는 승자 전략(C1 골든+AI청산, C3 RSI+AI청산)과 기준선을 2018~2025 연도별
구간(약세장 2018·2022 포함)에 걸쳐 돌려, 특히 약세장에서 AI-청산이 자본을
방어하는지(B&H보다 손실/낙폭이 작은지) 확인한다.

실행: POLARS_MAX_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 python3 experiment_ai_walkforward.py
(POLARS_MAX_THREADS=1 없으면 rayon 데드락으로 정지 — project_ai_backtest_deadlock 참고)
"""
import sys, time, json
import pandas as pd

sys.path.insert(0, ".")
from backtest_engine import BacktestEngine

POS_SIZE = 10
INIT_CASH = 10_000_000
OPTIONS = {"execution_type": "next_open", "fee_rate": 0.015, "slippage_rate": 0.05}

# 풀드 분포 기반 고정 threshold (experiment_ai_auxiliary 결과: 상승 p90≈0.284, 하락 p98≈0.403)
UP = 0.284
DOWN = 0.403

UNIVERSE = [
    "005930","000660","005380","035420","051910","005490","035720","005935",
    "012330","105560","055550","096770","066570","003550","015760","034730",
    "032830","000270","068270","207940","006400","051900","028260","009150",
    "086790","033780","017670","030200","011200","010130",
]

# 연도별 구간 (KOSPI 국면 라벨)
WINDOWS = [
    ("2018 약세(관세전쟁)", "2018-01-01", "2018-12-31"),
    ("2019 횡보",           "2019-01-01", "2019-12-31"),
    ("2020 코로나충격+회복", "2020-01-01", "2020-12-31"),
    ("2021 고점→횡보",       "2021-01-01", "2021-12-31"),
    ("2022 약세(금리인상)",  "2022-01-01", "2022-12-31"),
    ("2023 회복",           "2023-01-01", "2023-12-31"),
    ("2024 횡보",           "2024-01-01", "2024-12-31"),
    ("2025 상승",           "2025-01-01", "2025-12-31"),
]


def golden():  return {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
def dead():    return {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "sell"}}
def rsi_buy(): return {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<=", "signalType": "buy"}}
def rsi_sell():return {"id": "rsi", "params": {"period": 14, "value": 70, "operator": ">=", "signalType": "sell"}}
def ai_buy():  return {"id": "ai_model", "params": {"signalType": "buy", "threshold": UP}}
def ai_sell(): return {"id": "ai_drop_model", "params": {"signalType": "sell", "threshold": DOWN}}
OR = lambda *cs: {"logic": "OR", "conditions": list(cs)}

STRATEGIES = {
    "T1 골든단독":        (OR(golden()), OR(dead()), None),
    "A1 AI단독":          (OR(ai_buy()), OR(ai_sell()), None),
    "C1 골든+AI청산":     (OR(golden()), OR(ai_sell()), None),
    "C3 RSI+AI청산+손절7%":(OR(rsi_buy()), OR(ai_sell()), {"stop_loss_pct": 7}),
}


def run(engine, entry, exit_, risk_extra, start, end):
    risk = {"position_size_pct": POS_SIZE, "init_cash": INIT_CASH}
    if risk_extra:
        risk.update(risk_extra)
    req = {"symbols": UNIVERSE, "entry": entry, "exit": exit_, "risk": risk,
           "options": OPTIONS, "startDate": start, "endDate": end}
    r = engine.run_backtest(req)
    return r


def main():
    eng = BacktestEngine()
    eng.ai_engine
    all_rows = []
    print(f"[threshold] 진입 AI상승>={UP}  청산 AI하락>={DOWN}")
    for label, start, end in WINDOWS:
        print(f"\n{'='*100}\n[{label}]  {start} ~ {end}")
        print(f"{'전략':<24}{'수익%':>8}{'Sharpe':>8}{'MDD%':>8}{'승률%':>7}{'거래':>6}{'PF':>7}{'vs B&H':>9}")
        print("-"*100)
        bh = None
        win_rows = []
        for name, (entry, exit_, rx) in STRATEGIES.items():
            t = time.time()
            r = run(eng, entry, exit_, rx, start, end)
            if bh is None:
                bh = r["buyAndHoldReturn"]
            edge = r["totalReturn"] - bh
            row = {"window": label, "strategy": name,
                   "ret": round(r["totalReturn"], 1), "sharpe": round(r["sharpe"], 2),
                   "mdd": round(r["maxDrawdown"], 1), "win": round(r["winRate"], 1),
                   "trades": r["trades"], "pf": round(r["profitFactor"], 2),
                   "bh": round(bh, 1), "edge": round(edge, 1)}
            win_rows.append(row); all_rows.append(row)
            print(f"{name:<24}{row['ret']:>8}{row['sharpe']:>8}{row['mdd']:>8}"
                  f"{row['win']:>7}{row['trades']:>6}{row['pf']:>7}{row['edge']:>+9}")
        print(f"{'(바이앤홀드)':<24}{round(bh,1):>8}")

    # 요약: 전략별 전 구간 평균
    print(f"\n{'='*100}\n[전 구간 요약 — 전략별 평균]")
    print(f"{'전략':<24}{'평균수익%':>10}{'평균Sharpe':>11}{'평균MDD%':>10}{'B&H대비승':>10}")
    print("-"*100)
    for name in STRATEGIES:
        rows = [r for r in all_rows if r["strategy"] == name]
        avg_ret = sum(r["ret"] for r in rows) / len(rows)
        avg_sh = sum(r["sharpe"] for r in rows) / len(rows)
        avg_mdd = sum(r["mdd"] for r in rows) / len(rows)
        beat = sum(1 for r in rows if r["edge"] > 0)
        print(f"{name:<24}{avg_ret:>10.1f}{avg_sh:>11.2f}{avg_mdd:>10.1f}{beat:>7}/{len(rows)}")
    bh_rows = {r["window"]: r["bh"] for r in all_rows}
    print(f"{'(바이앤홀드 평균)':<24}{sum(bh_rows.values())/len(bh_rows):>10.1f}")

    with open("../ai_walkforward_results.json", "w") as f:
        json.dump({"up": UP, "down": DOWN, "universe": UNIVERSE,
                   "windows": [w[0] for w in WINDOWS], "rows": all_rows}, f, ensure_ascii=False, indent=2)
    print("\n결과 저장: ai_walkforward_results.json")


if __name__ == "__main__":
    main()
