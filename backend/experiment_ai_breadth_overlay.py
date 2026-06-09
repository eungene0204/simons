"""
AI '브레드스 위험 오버레이' 검증.

가설: AI를 per-stock 매매가 아니라 시장 레짐 필터로 쓴다. 유니버스를 동일가중
보유(B&H 코어)하다가, 다수 종목에서 AI-하락 신호가 동시에 켜지면(breadth 급등)
시장 전체 스트레스로 보고 전량 현금화, 진정되면 재진입. 약세장 하방을 깎아
'위험조정수익'을 B&H보다 개선할 수 있는지 본다.

룩어헤드 방지: 당일 종가로 breadth 계산 → 익일(+1)부터 익스포저 적용.
스위치마다 왕복 거래비용 차감. 워밍업(스코어 유효) 이후 구간만 사용.

실행: KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 python3 experiment_ai_breadth_overlay.py
"""
import sys, json
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from ai.ai_engine import AIEngine

DOWN = 0.403          # per-stock AI 하락 발화 임계 (p98)
SWITCH_COST = 0.003   # 익스포저 플립당 왕복 비용(수수료+슬리피지, 전 종목 회전 가정)
START = "2017-01-01"  # 워밍업 이후
END   = "2025-12-31"

UNIVERSE = [
    "005930","000660","005380","035420","051910","005490","035720","005935",
    "012330","105560","055550","096770","066570","003550","015760","034730",
    "032830","000270","068270","207940","006400","051900","028260","009150",
    "086790","033780","017670","030200","011200","010130",
]


def load_aligned():
    """전 종목 close/ai_drop_score를 공통 날짜축에 정렬한 행렬로 반환."""
    eng = AIEngine()
    closes, drops = {}, {}
    dfs = {}
    for sym in UNIVERSE:
        try:
            df = pd.read_parquet(f"../data/ohlcv/{sym}.parquet")
        except Exception:
            continue
        df = df[["date", "close"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        dfs[sym] = df
    # AI 하락 스코어 (배치)
    score_in = {sym: pd.read_parquet(f"../data/ohlcv/{sym}.parquet") for sym in dfs}
    batch = eng.predict_signals_batch(score_in)
    for sym, df in dfs.items():
        up, down = batch[sym]
        down = np.asarray(down)
        idx = pd.to_datetime(pd.read_parquet(f"../data/ohlcv/{sym}.parquet")["date"])
        s = pd.Series(down, index=idx)
        s = s[~s.index.duplicated()]
        closes[sym] = df["close"][~df.index.duplicated()]
        drops[sym] = s
    close_mat = pd.DataFrame(closes).sort_index()
    drop_mat = pd.DataFrame(drops).reindex(close_mat.index)
    return close_mat, drop_mat


def metrics(equity, dates):
    """equity: 1-기준 누적 시리즈. (총수익%, CAGR%, MDD%, Sharpe, 연환산변동성%)"""
    equity = np.asarray(equity, dtype=float)
    total = (equity[-1] - 1) * 100
    days = (dates[-1] - dates[0]).days or 1
    years = days / 365.25
    cagr = ((equity[-1]) ** (1 / years) - 1) * 100 if equity[-1] > 0 else -100.0
    peak = np.maximum.accumulate(equity)
    mdd = ((equity - peak) / peak).min() * 100
    rets = np.diff(equity) / equity[:-1]
    sharpe = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    vol = rets.std() * np.sqrt(252) * 100
    return total, cagr, mdd, sharpe, vol


def main():
    close_mat, drop_mat = load_aligned()
    mask = (close_mat.index >= pd.Timestamp(START)) & (close_mat.index <= pd.Timestamp(END))
    close_mat = close_mat[mask]; drop_mat = drop_mat[mask]
    dates = close_mat.index

    # 동일가중 일간수익 (그날 데이터 있는 종목 평균)
    daily_ret = close_mat.pct_change()
    ew_ret = daily_ret.mean(axis=1).fillna(0.0).values  # B&H 코어 일간수익

    # breadth_t = AI하락 발화 종목 비율 (스코어 유효[>0]인 종목 중)
    valid = drop_mat > 0
    firing = (drop_mat >= DOWN) & valid
    breadth = (firing.sum(axis=1) / valid.sum(axis=1).replace(0, np.nan)).fillna(0.0).values

    dates_np = dates.to_pydatetime()
    dates_np = np.array([pd.Timestamp(d) for d in dates_np])

    # B&H 벤치마크
    bh_eq = np.cumprod(1 + ew_ret)
    bh_m = metrics(bh_eq, dates_np)

    print(f"[설정] per-stock 하락임계={DOWN}, 스위치비용={SWITCH_COST*100:.1f}%/플립, 구간 {START}~{END}")
    print(f"[breadth 분포] 평균 {breadth.mean()*100:.1f}%  p50 {np.percentile(breadth,50)*100:.1f}%  "
          f"p90 {np.percentile(breadth,90)*100:.1f}%  p95 {np.percentile(breadth,95)*100:.1f}%  최대 {breadth.max()*100:.1f}%")
    print("="*104)
    print(f"{'전략(현금화 임계)':<26}{'총수익%':>9}{'CAGR%':>8}{'MDD%':>8}{'Sharpe':>8}{'변동성%':>9}{'현금일%':>8}{'스위치':>7}")
    print("-"*104)
    print(f"{'바이앤홀드(코어)':<26}{bh_m[0]:>9.1f}{bh_m[1]:>8.1f}{bh_m[2]:>8.1f}{bh_m[3]:>8.2f}{bh_m[4]:>9.1f}{0:>8}{0:>7}")

    results = [{"strategy": "buy_and_hold", "total": round(bh_m[0],1), "cagr": round(bh_m[1],1),
                "mdd": round(bh_m[2],1), "sharpe": round(bh_m[3],2), "vol": round(bh_m[4],1),
                "cash_pct": 0.0, "switches": 0}]

    # 현금화 임계 스캔: breadth가 임계 초과면 다음날 현금
    for exit_th in [0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25]:
        in_market = (breadth < exit_th).astype(float)
        exposure = np.empty_like(in_market)
        exposure[0] = 1.0
        exposure[1:] = in_market[:-1]          # +1일 지연 (룩어헤드 방지)
        port_ret = exposure * ew_ret
        switches = int(np.abs(np.diff(exposure)).sum())  # 0<->1 플립 횟수
        cost = np.zeros_like(port_ret)
        flip_idx = np.where(np.abs(np.diff(exposure)) > 0)[0] + 1
        cost[flip_idx] = SWITCH_COST
        net_ret = port_ret - cost
        eq = np.cumprod(1 + net_ret)
        m = metrics(eq, dates_np)
        cash_pct = (1 - exposure.mean()) * 100
        print(f"{('오버레이 breadth>'+str(int(exit_th*100))+'%'):<26}{m[0]:>9.1f}{m[1]:>8.1f}{m[2]:>8.1f}"
              f"{m[3]:>8.2f}{m[4]:>9.1f}{cash_pct:>8.1f}{switches:>7}")
        results.append({"strategy": f"overlay_breadth>{int(exit_th*100)}%", "total": round(m[0],1),
                        "cagr": round(m[1],1), "mdd": round(m[2],1), "sharpe": round(m[3],2),
                        "vol": round(m[4],1), "cash_pct": round(cash_pct,1), "switches": switches})

    # 연도별: 최선 임계(가장 높은 Sharpe) vs B&H
    best = max(results[1:], key=lambda r: r["sharpe"])
    best_th = int(best["strategy"].split(">")[1].rstrip("%")) / 100
    print("\n" + "="*104)
    print(f"[연도별] 최고Sharpe 오버레이({best['strategy']}) vs 바이앤홀드")
    print(f"{'연도':<8}{'B&H 수익%':>12}{'오버레이 수익%':>16}{'B&H MDD%':>12}{'오버레이 MDD%':>16}")
    print("-"*104)
    in_market = (breadth < best_th).astype(float)
    exposure = np.empty_like(in_market); exposure[0]=1.0; exposure[1:]=in_market[:-1]
    cost = np.zeros_like(ew_ret); fi = np.where(np.abs(np.diff(exposure))>0)[0]+1; cost[fi]=SWITCH_COST
    ov_ret = exposure*ew_ret - cost
    yr = dates.year
    for y in range(2017, 2026):
        ysel = (yr == y)
        if ysel.sum() < 5: continue
        bh_y = np.cumprod(1+ew_ret[ysel]); ov_y = np.cumprod(1+ov_ret[ysel])
        def mdd(e):
            p=np.maximum.accumulate(e); return ((e-p)/p).min()*100
        print(f"{y:<8}{(bh_y[-1]-1)*100:>12.1f}{(ov_y[-1]-1)*100:>16.1f}{mdd(bh_y):>12.1f}{mdd(ov_y):>16.1f}")

    with open("../ai_breadth_overlay_results.json", "w") as f:
        json.dump({"down_th": DOWN, "switch_cost": SWITCH_COST, "start": START, "end": END,
                   "breadth_mean_pct": round(float(breadth.mean()*100),2),
                   "best_overlay": best["strategy"], "results": results}, f, ensure_ascii=False, indent=2)
    print("\n결과 저장: ai_breadth_overlay_results.json")


if __name__ == "__main__":
    main()
