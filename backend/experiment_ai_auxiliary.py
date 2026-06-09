"""
AI 모델을 '보조 도구'로 활용했을 때 최대 수익을 내는 방법 탐색 실험.

배경: AI 모델 단독 진입/청산으로는 수익이 약하다(점수 분포가 좁고 보정 안 됨).
목표: AI를 (1)확인 필터 (2)청산 타이밍 (3)리스크 결합 등으로 조합해
      기술적 전략 단독 대비 수익/위험을 개선하는 사용법을 찾는다.

한 프로세스에서 단일 BacktestEngine을 재사용 → AI 점수는 종목당 1회만 추론(캐시).
"""
import sys, time, json
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from backtest_engine import BacktestEngine

PERIOD = "3Y"
POS_SIZE = 10          # 종목당 자본 비중 % (분산)
INIT_CASH = 10_000_000
OPTIONS = {"execution_type": "next_open", "fee_rate": 0.015, "slippage_rate": 0.05}

# 대표 KOSPI200 유니버스 (대/중형주 30종목, 3Y 데이터 보유)
UNIVERSE = [
    "005930","000660","005380","035420","051910","005490","035720","005935",
    "012330","105560","055550","096770","066570","003550","015760","034730",
    "032830","000270","068270","207940","006400","051900","028260","009150",
    "086790","033780","017670","030200","011200","010130",
]


def derive_thresholds(engine):
    """유니버스 전체 AI 점수 풀드 분포에서 보정된 threshold를 도출."""
    ai = engine.ai_engine
    ups, downs = [], []
    for sym in UNIVERSE:
        try:
            df = pd.read_parquet(f"../data/ohlcv/{sym}.parquet")
        except Exception:
            continue
        up, down = ai.predict_signals(df)
        up = np.asarray(up); down = np.asarray(down)
        ups.append(up[up > 0]); downs.append(down[down > 0])
    up_all = np.concatenate(ups); down_all = np.concatenate(downs)
    th = {
        "up_p75": float(np.percentile(up_all, 75)),
        "up_p85": float(np.percentile(up_all, 85)),
        "up_p90": float(np.percentile(up_all, 90)),
        "up_p95": float(np.percentile(up_all, 95)),
        "down_p85": float(np.percentile(down_all, 85)),
        "down_p90": float(np.percentile(down_all, 90)),
        "down_p95": float(np.percentile(down_all, 95)),
        "down_p98": float(np.percentile(down_all, 98)),
    }
    print("\n[AI 점수 풀드 분포]")
    print(f"  상승점수 p50={np.percentile(up_all,50):.3f} p75={th['up_p75']:.3f} "
          f"p85={th['up_p85']:.3f} p90={th['up_p90']:.3f} p95={th['up_p95']:.3f} max={up_all.max():.3f}")
    print(f"  하락점수 p50={np.percentile(down_all,50):.3f} p85={th['down_p85']:.3f} "
          f"p90={th['down_p90']:.3f} p95={th['down_p95']:.3f} p98={th['down_p98']:.3f} max={down_all.max():.3f}")
    return th


# ── 조건 빌더 헬퍼 ────────────────────────────────────────────────
def ai_buy(th, as_filter=False):
    c = {"id": "ai_model", "params": {"signalType": "buy", "threshold": th}}
    if as_filter:
        c["type"] = "filter"
    return c

def ai_sell(th):
    return {"id": "ai_drop_model", "params": {"signalType": "sell", "threshold": th}}

def golden():
    return {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
def dead():
    return {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "sell"}}
def rsi_buy():
    return {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<=", "signalType": "buy"}}
def rsi_sell():
    return {"id": "rsi", "params": {"period": 14, "value": 70, "operator": ">=", "signalType": "sell"}}
def breakout():
    return {"id": "breakout", "params": {"lookbackPeriod": 20, "signalType": "buy"}}


def run(engine, name, entry, exit_, risk_extra=None):
    risk = {"position_size_pct": POS_SIZE, "init_cash": INIT_CASH}
    if risk_extra:
        risk.update(risk_extra)
    req = {
        "symbols": UNIVERSE,
        "entry": entry,
        "exit": exit_,
        "risk": risk,
        "options": OPTIONS,
        "period": PERIOD,
    }
    t = time.time()
    r = engine.run_backtest(req)
    return {
        "name": name,
        "totalReturn": round(r["totalReturn"], 1),
        "buyHold": round(r["buyAndHoldReturn"], 1),
        "cagr": round(r["cagr"], 1),
        "sharpe": round(r["sharpe"], 2),
        "mdd": round(r["maxDrawdown"], 1),
        "winRate": round(r["winRate"], 1),
        "trades": r["trades"],
        "profitFactor": round(r["profitFactor"], 2),
        "secs": round(time.time() - t, 1),
    }


def main():
    eng = BacktestEngine()
    eng.ai_engine  # warm load
    th = derive_thresholds(eng)

    UP = th["up_p90"]        # 보조 필터용 상승 임계 (상위 10%만 통과)
    UP_STRICT = th["up_p95"]
    # 하락점수는 0.33~0.40에 밀집 → 청산에 쓰려면 매우 선택적(p98)이어야 과매매를 피한다.
    DOWN = th["down_p98"]    # 청산용 하락 임계 (상위 2%만 발화)

    print(f"\n[사용 threshold] 진입 AI상승>={UP:.3f}(p90), 엄격>={UP_STRICT:.3f}(p95), 청산 AI하락>={DOWN:.3f}(p98)")
    print("="*108)

    OR = lambda *cs: {"logic": "OR", "conditions": list(cs)}
    AND = lambda *cs: {"logic": "AND", "conditions": list(cs)}

    results = []
    # ── 기준선 ──
    results.append(run(eng, "T1 골든크로스 단독(진입GC/청산DC)", OR(golden()), OR(dead())))
    results.append(run(eng, "T2 RSI 단독(진입<30/청산>70)", OR(rsi_buy()), OR(rsi_sell())))
    results.append(run(eng, "T3 돌파 단독(20일+트레일10%)", OR(breakout()), OR(dead()), {"trailing_stop_pct": 10}))
    results.append(run(eng, "A1 ★AI단독(진입AI상승/청산AI하락)", OR(ai_buy(UP)), OR(ai_sell(DOWN))))
    results.append(run(eng, "A2 AI단독+손절7%익절20%", OR(ai_buy(UP)), OR(ai_sell(DOWN)), {"stop_loss_pct":7,"take_profit_pct":20}))

    # ── B. AI를 '확인 필터'로 (기술적 진입 + AI 게이트) ──
    results.append(run(eng, "B1 골든크로스+AI필터 / 청산DC", AND(golden(), ai_buy(UP, as_filter=True)), OR(dead())))
    results.append(run(eng, "B2 RSI<30+AI필터 / 청산RSI>70", AND(rsi_buy(), ai_buy(UP, as_filter=True)), OR(rsi_sell())))
    results.append(run(eng, "B3 돌파+AI필터 / 트레일10%", AND(breakout(), ai_buy(UP, as_filter=True)), OR(dead()), {"trailing_stop_pct":10}))
    results.append(run(eng, "B1s 골든크로스+AI엄격필터(p95)", AND(golden(), ai_buy(UP_STRICT, as_filter=True)), OR(dead())))

    # ── C. 기술적 진입 + AI를 '청산 타이밍'으로 ──
    results.append(run(eng, "C1 골든진입 / 청산=AI하락", OR(golden()), OR(ai_sell(DOWN))))
    results.append(run(eng, "C2 골든진입 / 청산=AI하락+DC", OR(golden()), OR(ai_sell(DOWN), dead())))
    results.append(run(eng, "C3 RSI진입 / 청산=AI하락+손절7%", OR(rsi_buy()), OR(ai_sell(DOWN)), {"stop_loss_pct":7}))

    # ── D. AI 진입 + 리스크 관리 강화 ──
    results.append(run(eng, "D1 AI진입+트레일10% / 청산DC", OR(ai_buy(UP)), OR(dead()), {"trailing_stop_pct":10}))
    results.append(run(eng, "D2 AI진입+손절5%익절15%트레일", OR(ai_buy(UP)), OR(ai_sell(DOWN)), {"stop_loss_pct":5,"take_profit_pct":15,"trailing_stop_pct":12}))

    # ── E. AI 양쪽 보조: 골든+AI필터 진입, AI하락 청산, 트레일 ──
    results.append(run(eng, "E1 골든+AI필터 / 청산AI하락+트레일", AND(golden(), ai_buy(UP, as_filter=True)), OR(ai_sell(DOWN)), {"trailing_stop_pct":10}))

    # ── 출력 ──
    print(f"\n{'전략':<36}{'수익%':>8}{'CAGR':>7}{'Sharpe':>8}{'MDD%':>8}{'승률%':>7}{'거래':>6}{'PF':>6}")
    print("-"*108)
    bh = results[0]["buyHold"]
    for r in results:
        print(f"{r['name']:<36}{r['totalReturn']:>8}{r['cagr']:>7}{r['sharpe']:>8}"
              f"{r['mdd']:>8}{r['winRate']:>7}{r['trades']:>6}{r['profitFactor']:>6}")
    print("-"*108)
    print(f"{'(바이앤홀드 벤치마크)':<36}{bh:>8}")

    with open("../ai_auxiliary_results.json", "w") as f:
        json.dump({"thresholds": th, "universe": UNIVERSE, "period": PERIOD,
                   "pos_size_pct": POS_SIZE, "results": results}, f, ensure_ascii=False, indent=2)
    print("\n결과 저장: ai_auxiliary_results.json")


if __name__ == "__main__":
    main()
