"""
QA harness — Strategy Advisor Agent edge-case verification.

Feeds 55 hand-built edge cases through the real (deterministic, rule-based)
advisor pipeline and checks:
  1. forbidden_patterns  — must NOT appear anywhere in the rendered output
  2. expected_requirements — keyword heuristics over the rendered output

Run:  cd backend && python qa_advisor_edgecases.py
Outputs a markdown report to ../docs/advisor_qa_report.md
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from advisor.agent import StrategyAdvisorAgent
from advisor.schemas import AdvisorRequest, BacktestSummary


# ── helpers ──────────────────────────────────────────────────────────────────

def bt(**kw) -> Optional[BacktestSummary]:
    """Build BacktestSummary; cagr/mdd given in PERCENT -> fraction."""
    if kw.pop("none", False):
        return None
    if "cagr" in kw and kw["cagr"] is not None:
        kw["cagr"] = kw["cagr"] / 100.0
    if "mdd" in kw and kw["mdd"] is not None:
        kw["mdd"] = kw["mdd"] / 100.0
    return BacktestSummary(**kw)


def ps(universe="KOSPI", **kw) -> Dict[str, Any]:
    base: Dict[str, Any] = {"universe": [universe] if universe else ["KOSPI200"]}
    base.update(kw)
    return base


# Requirement keyword map: requirement-tag -> list of acceptable substrings.
REQ_KEYWORDS = {
    "capital": ["자본", "거래대금", "포지션당", "투자금"],
    "trade_freq": ["거래 횟수", "거래 수", "거래비용", "회전", "거래대금"],
    "universe_range": ["종목", "분산", "거래대금"],
    "liquidity": ["유동성", "거래대금", "슬리피지"],
    "slippage": ["슬리피지"],
    "executability": ["실거래", "슬리피지", "유동성", "괴리"],
    "mdd": ["MDD", "낙폭"],
    "sharpe": ["Sharpe", "샤프"],
    "trade_count": ["거래 횟수", "거래 수", "통계"],
    "stat_reliability": ["통계", "신뢰", "검증", "과최적화", "walk-forward", "Walk-forward", "Monte Carlo"],
    "not_return_only": ["MDD", "Sharpe", "낙폭", "위험", "변동성"],
    "logic_contradiction": ["모순", "충돌", "동시", "상충"],
    "missing_condition": ["진입", "청산", "손절", "조건이 없", "정의되지"],
    "simplify": ["줄이", "단순", "축소", "3개 이하"],
    "data_missing": ["데이터", "백테스트", "없", "미정", "부족"],
    "needs_validation": ["검증", "확인", "walk-forward", "Walk-forward", "Monte Carlo", "백테스트"],
    "limits": ["한계", "괴리", "달라질", "보장", "어렵"],
    "no_overconfidence": [],  # checked only via forbidden_patterns
}


# ── 55 edge cases ────────────────────────────────────────────────────────────
# Each: id, category, desc, ps(parsed_strategy), bt(backtest or None),
#       reqs (list of requirement-tags), forbidden (list of substrings)

FB_CAP = ["거래대금 10억 이상 필터를 추가하세요", "모든 종목에 적용 가능합니다", "자금 규모와 무관하게"]
FB_LIQ = ["문제 없습니다", "실제 운용 가능", "충분히 안전"]
FB_MET = ["우수한 전략입니다", "매우 안정적입니다", "성공 가능성이 높습니다"]
FB_DSL = ["문제 없습니다", "충분히 합리적입니다"]
FB_GRD = ["반드시 상승합니다", "매수하세요", "확실합니다", "100% 성공", "손실 위험이 없습니다"]

CASES: List[Dict[str, Any]] = [
    # ── Category 1: Capital ──
    dict(id="CAP-001", category="Capital", desc="100만원 소액",
         ps=ps("KOSDAQ", initial_capital=1_000_000, max_positions=10,
               entry_signals=[{"indicator": "rsi", "signal_type": "oversold"}],
               exit_signals=[{"indicator": "rsi", "signal_type": "overbought"}]),
         bt=bt(cagr=18.2, mdd=-32.1, sharpe=0.74, profit_factor=1.41, trade_count=86, win_rate=0.52),
         reqs=["capital", "universe_range", "liquidity"], forbidden=FB_CAP + ["매수하세요"]),
    dict(id="CAP-002", category="Capital", desc="100만원+10종목 단주",
         ps=ps("KOSPI", initial_capital=1_000_000, max_positions=10,
               entry_signals=[{"indicator": "ma_crossover"}], hold_period_days=20),
         bt=bt(cagr=9.1, mdd=-19.8, sharpe=0.66, profit_factor=1.22, trade_count=54, win_rate=0.48),
         reqs=["capital", "universe_range", "trade_freq"], forbidden=FB_CAP + ["확실합니다"]),
    dict(id="CAP-003", category="Capital", desc="500만원 고가주",
         ps=ps("KOSPI", initial_capital=5_000_000, max_positions=5,
               entry_signals=[{"indicator": "breakout"}], hold_period_days=90),
         bt=bt(cagr=12.4, mdd=-24.0, sharpe=0.81, profit_factor=1.35, trade_count=38, win_rate=0.55),
         reqs=["capital", "universe_range"], forbidden=FB_CAP + FB_MET),
    dict(id="CAP-004", category="Capital", desc="1천만원 거래대금필터 스케일",
         ps=ps("KOSDAQ", initial_capital=10_000_000, max_positions=10,
               entry_signals=[{"indicator": "volume_spike"}], stop_loss_pct=7.0, take_profit_pct=15.0),
         bt=bt(cagr=21.5, mdd=-29.4, sharpe=0.79, profit_factor=1.48, trade_count=120, win_rate=0.5),
         reqs=["capital", "liquidity", "trade_freq"], forbidden=FB_CAP),
    dict(id="CAP-005", category="Capital", desc="5천만원 중형주",
         ps=ps("KOSPI", initial_capital=50_000_000, max_positions=15,
               fundamental_filters=[{"metric": "per"}, {"metric": "roe"}], hold_period_days=250),
         bt=bt(cagr=11.0, mdd=-21.3, sharpe=0.85, profit_factor=1.39, trade_count=30, win_rate=0.57),
         reqs=["capital", "universe_range", "mdd"], forbidden=FB_CAP + ["성공 가능성이 높습니다"]),
    dict(id="CAP-006", category="Capital", desc="10억 소형주 충격",
         ps=ps("KOSDAQ", initial_capital=1_000_000_000, max_positions=20,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=12),
         bt=bt(cagr=34.2, mdd=-38.7, sharpe=0.9, profit_factor=1.55, trade_count=410, win_rate=0.53),
         reqs=["capital", "universe_range", "liquidity"], forbidden=FB_CAP + FB_LIQ),
    dict(id="CAP-007", category="Capital", desc="10억 단일종목 풀베팅",
         ps=ps("KOSDAQ", initial_capital=1_000_000_000, max_positions=1,
               entry_signals=[{"indicator": "breakout"}], stop_loss_pct=10.0),
         bt=bt(cagr=58.0, mdd=-55.0, sharpe=0.61, profit_factor=1.3, trade_count=22, win_rate=0.41),
         reqs=["capital", "liquidity", "mdd"], forbidden=FB_MET + ["손실 위험이 없습니다", "자금 규모와 무관하게"]),
    dict(id="CAP-008", category="Capital", desc="100만원 고빈도",
         ps=ps("KOSPI", initial_capital=1_000_000, max_positions=5,
               entry_signals=[{"indicator": "breakout"}], hold_period_days=1),
         bt=bt(cagr=26.0, mdd=-27.0, sharpe=0.83, profit_factor=1.25, trade_count=300, win_rate=0.49),
         reqs=["capital", "trade_freq", "limits"], forbidden=FB_CAP + ["충분히 안전"]),
    dict(id="CAP-009", category="Capital", desc="자본 미입력",
         ps=ps("KOSPI", max_positions=10, entry_signals=[{"indicator": "rsi"}], hold_period_days=30),
         bt=bt(cagr=14.0, mdd=-22.0, sharpe=0.77, profit_factor=1.33, trade_count=60, win_rate=0.52),
         reqs=["capital"], forbidden=FB_CAP + ["확실합니다"]),
    dict(id="CAP-010", category="Capital", desc="1천만원 50종목 과분산",
         ps=ps("KOSPI", initial_capital=10_000_000, max_positions=50,
               fundamental_filters=[{"metric": "per"}, {"metric": "pbr"}], hold_period_days=30),
         bt=bt(cagr=10.2, mdd=-18.0, sharpe=0.88, profit_factor=1.3, trade_count=600, win_rate=0.54),
         reqs=["capital", "universe_range", "trade_freq"], forbidden=FB_CAP + FB_MET),
    dict(id="CAP-011", category="Capital", desc="5천만원 거래대금필터 적정성",
         ps=ps("KOSDAQ", initial_capital=50_000_000, max_positions=10,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=40),
         bt=bt(cagr=19.0, mdd=-28.0, sharpe=0.8, profit_factor=1.42, trade_count=90, win_rate=0.51),
         reqs=["capital", "liquidity"], forbidden=FB_CAP),

    # ── Category 2: Liquidity ──
    dict(id="LIQ-001", category="Liquidity", desc="거래량 부족 초소형주",
         ps=ps("KOSDAQ", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=20),
         bt=bt(cagr=41.0, mdd=-36.0, sharpe=0.86, profit_factor=1.6, trade_count=75, win_rate=0.56),
         reqs=["liquidity", "slippage", "executability"], forbidden=FB_LIQ + FB_MET),
    dict(id="LIQ-002", category="Liquidity", desc="거래대금 부족",
         ps=ps("KOSDAQ", initial_capital=100_000_000, max_positions=10,
               entry_signals=[{"indicator": "breakout"}], hold_period_days=15),
         bt=bt(cagr=33.0, mdd=-34.0, sharpe=0.78, profit_factor=1.5, trade_count=140, win_rate=0.5),
         reqs=["liquidity", "slippage", "executability"], forbidden=FB_LIQ + ["성공 가능성이 높습니다"]),
    dict(id="LIQ-003", category="Liquidity", desc="슬리피지 0 과소평가",
         ps=ps("KOSDAQ", initial_capital=20_000_000, max_positions=6,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=10),
         bt=bt(cagr=28.0, mdd=-25.0, sharpe=0.95, profit_factor=1.7, trade_count=160, win_rate=0.55),
         reqs=["slippage", "limits", "executability"], forbidden=FB_LIQ + ["확실합니다"]),
    dict(id="LIQ-004", category="Liquidity", desc="거래 횟수 과다 800",
         ps=ps("KOSPI", initial_capital=50_000_000, max_positions=5,
               entry_signals=[{"indicator": "breakout"}], hold_period_days=1),
         bt=bt(cagr=22.0, mdd=-20.0, sharpe=0.9, profit_factor=1.18, trade_count=800, win_rate=0.51),
         reqs=["trade_freq", "executability"], forbidden=FB_LIQ + ["매우 안정적입니다"]),
    dict(id="LIQ-005", category="Liquidity", desc="소형주+대형자본",
         ps=ps("KOSDAQ", initial_capital=500_000_000, max_positions=20,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=7),
         bt=bt(cagr=25.0, mdd=-23.0, sharpe=1.0, profit_factor=1.5, trade_count=300, win_rate=0.58),
         reqs=["liquidity", "slippage", "executability"], forbidden=FB_LIQ + ["자금 규모와 무관하게"]),
    dict(id="LIQ-006", category="Liquidity", desc="저유동성+화려한지표",
         ps=ps("KOSDAQ", initial_capital=80_000_000, max_positions=8,
               entry_signals=[{"indicator": "breakout"}], hold_period_days=14),
         bt=bt(cagr=62.0, mdd=-30.0, sharpe=1.4, profit_factor=2.1, trade_count=95, win_rate=0.62),
         reqs=["liquidity", "slippage", "executability"], forbidden=FB_LIQ + FB_MET),
    dict(id="LIQ-007", category="Liquidity", desc="손절 미체결 위험",
         ps=ps("KOSDAQ", initial_capital=40_000_000, max_positions=8,
               entry_signals=[{"indicator": "breakout"}], stop_loss_pct=8.0),
         bt=bt(cagr=30.0, mdd=-45.0, sharpe=0.7, profit_factor=1.35, trade_count=110, win_rate=0.47),
         reqs=["liquidity", "slippage", "executability", "mdd"], forbidden=FB_LIQ + ["손실 위험이 없습니다"]),
    dict(id="LIQ-008", category="Liquidity", desc="대형주 슬리피지 과소",
         ps=ps("KOSPI", initial_capital=100_000_000, max_positions=10,
               entry_signals=[{"indicator": "ma_crossover"}], hold_period_days=30),
         bt=bt(cagr=13.0, mdd=-17.0, sharpe=0.82, profit_factor=1.4, trade_count=70, win_rate=0.53),
         reqs=["slippage", "limits"], forbidden=FB_LIQ + ["매우 안정적입니다"]),
    dict(id="LIQ-009", category="Liquidity", desc="유동성 데이터 누락",
         ps=ps("KOSDAQ", initial_capital=30_000_000, max_positions=10,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=30),
         bt=bt(cagr=17.0, mdd=-26.0, sharpe=0.75, profit_factor=1.38, trade_count=85, win_rate=0.5),
         reqs=["liquidity", "needs_validation"], forbidden=FB_LIQ + ["확실합니다"]),
    dict(id="LIQ-010", category="Liquidity", desc="주간 리밸런싱 고회전",
         ps=ps("KOSDAQ", initial_capital=70_000_000, max_positions=30,
               fundamental_filters=[{"metric": "per"}], hold_period_days=7),
         bt=bt(cagr=20.0, mdd=-22.0, sharpe=0.92, profit_factor=1.3, trade_count=1500, win_rate=0.54),
         reqs=["trade_freq", "executability"], forbidden=FB_LIQ + FB_MET),
    dict(id="LIQ-011", category="Liquidity", desc="대형주 슬리피지무시 유도",
         ps=ps("KOSPI", initial_capital=200_000_000, max_positions=10,
               entry_signals=[{"indicator": "ma_crossover"}], hold_period_days=60),
         bt=bt(cagr=11.0, mdd=-15.0, sharpe=0.88, profit_factor=1.45, trade_count=50, win_rate=0.55),
         reqs=["slippage", "executability"], forbidden=FB_LIQ + ["손실 위험이 없습니다", "확실합니다"]),

    # ── Category 3: Backtest Metric ──
    dict(id="MET-001", category="Metric", desc="A: CAGR고 MDD고",
         ps=ps("KOSDAQ", initial_capital=50_000_000, max_positions=8,
               entry_signals=[{"indicator": "breakout"}], stop_loss_pct=10.0),
         bt=bt(cagr=48.0, mdd=-62.0, sharpe=0.71, profit_factor=1.5, trade_count=120, win_rate=0.5),
         reqs=["mdd", "sharpe", "not_return_only"], forbidden=FB_MET),
    dict(id="MET-002", category="Metric", desc="B: Sharpe 매우낮음",
         ps=ps("KOSPI", initial_capital=50_000_000, max_positions=8,
               entry_signals=[{"indicator": "breakout"}], hold_period_days=30),
         bt=bt(cagr=20.0, mdd=-40.0, sharpe=0.2, profit_factor=1.1, trade_count=90, win_rate=0.48),
         reqs=["sharpe", "mdd", "not_return_only"], forbidden=FB_MET),
    dict(id="MET-003", category="Metric", desc="C: Profit Factor 낮음",
         ps=ps("KOSDAQ", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=8),
         bt=bt(cagr=8.0, mdd=-28.0, sharpe=0.35, profit_factor=1.02, trade_count=200, win_rate=0.49),
         reqs=["sharpe", "trade_count", "not_return_only"], forbidden=FB_MET),
    dict(id="MET-004", category="Metric", desc="D: Trade Count 3",
         ps=ps("KOSPI", initial_capital=50_000_000, max_positions=8,
               entry_signals=[{"indicator": "ma_crossover"}], hold_period_days=400),
         bt=bt(cagr=35.0, mdd=-12.0, sharpe=1.8, profit_factor=4.0, trade_count=3, win_rate=1.0),
         reqs=["trade_count", "stat_reliability", "limits"], forbidden=FB_MET + ["손실 위험이 없습니다"]),
    dict(id="MET-005", category="Metric", desc="E: 특정기간만 수익",
         ps=ps("KOSDAQ", initial_capital=50_000_000, max_positions=8,
               entry_signals=[{"indicator": "breakout"}], hold_period_days=30),
         bt=bt(cagr=30.0, mdd=-35.0, sharpe=0.9, profit_factor=1.6, trade_count=80, win_rate=0.55),
         reqs=["stat_reliability", "sharpe", "limits"], forbidden=FB_MET),
    dict(id="MET-006", category="Metric", desc="고승률 저PF",
         ps=ps("KOSPI", initial_capital=40_000_000, max_positions=8,
               entry_signals=[{"indicator": "breakout"}], take_profit_pct=2.0, stop_loss_pct=10.0),
         bt=bt(cagr=12.0, mdd=-50.0, sharpe=0.45, profit_factor=1.05, trade_count=150, win_rate=0.85),
         reqs=["mdd", "sharpe", "not_return_only"], forbidden=FB_MET + ["손실 위험이 없습니다"]),
    dict(id="MET-007", category="Metric", desc="Calmar우수 표본부족",
         ps=ps("KOSPI", initial_capital=50_000_000, max_positions=8,
               entry_signals=[{"indicator": "ma_crossover"}], hold_period_days=300),
         bt=bt(cagr=22.0, mdd=-10.0, sharpe=1.2, profit_factor=2.0, trade_count=6, win_rate=0.83),
         reqs=["trade_count", "stat_reliability", "limits"], forbidden=FB_MET),
    dict(id="MET-008", category="Metric", desc="평범한데 대박주장",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=30),
         bt=bt(cagr=9.0, mdd=-20.0, sharpe=0.6, profit_factor=1.2, trade_count=70, win_rate=0.5),
         reqs=["not_return_only"], forbidden=FB_MET + ["확실합니다"]),
    dict(id="MET-009", category="Metric", desc="변동성 극대 Sharpe~0",
         ps=ps("KOSDAQ", initial_capital=50_000_000, max_positions=8,
               entry_signals=[{"indicator": "breakout"}], hold_period_days=20),
         bt=bt(cagr=15.0, mdd=-58.0, sharpe=0.05, profit_factor=1.08, trade_count=100, win_rate=0.46),
         reqs=["sharpe", "mdd", "not_return_only"], forbidden=FB_MET + ["손실 위험이 없습니다"]),
    dict(id="MET-010", category="Metric", desc="지표 일부 null",
         ps=ps("KOSPI", initial_capital=40_000_000, max_positions=10,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=30),
         bt=bt(cagr=16.0, mdd=None, sharpe=None, profit_factor=1.4, trade_count=60, win_rate=0.52),
         reqs=["data_missing", "needs_validation"], forbidden=FB_MET + ["확실합니다"]),
    dict(id="MET-011", category="Metric", desc="짧은기간 MDD과소",
         ps=ps("KOSPI", initial_capital=50_000_000, max_positions=8,
               entry_signals=[{"indicator": "ma_crossover"}], hold_period_days=30),
         bt=bt(cagr=27.0, mdd=-9.0, sharpe=1.6, profit_factor=1.9, trade_count=25, win_rate=0.6),
         reqs=["trade_count", "stat_reliability", "limits"], forbidden=FB_MET + ["손실 위험이 없습니다"]),

    # ── Category 4: Strategy DSL ──
    dict(id="DSL-001", category="DSL", desc="RSI<30 매수 + RSI>70 매수 모순",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi", "signal_type": "oversold"},
                              {"indicator": "rsi", "signal_type": "overbought"}],
               hold_period_days=10),
         bt=bt(none=True),
         reqs=["logic_contradiction", "simplify"], forbidden=FB_DSL + FB_MET),
    dict(id="DSL-002", category="DSL", desc="매수 조건 없음",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[], exit_signals=[{"indicator": "rsi", "signal_type": "overbought"}],
               stop_loss_pct=5.0),
         bt=bt(none=True),
         reqs=["missing_condition"], forbidden=FB_DSL + ["매수하세요"]),
    dict(id="DSL-003", category="DSL", desc="매도조건+보유기간 없음",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "ma_crossover"}]),
         bt=bt(cagr=7.0, mdd=-55.0, sharpe=0.3, profit_factor=1.1, trade_count=12, win_rate=0.5),
         reqs=["missing_condition", "mdd"], forbidden=FB_DSL + ["손실 위험이 없습니다"]),
    dict(id="DSL-004", category="DSL", desc="미지원 지표",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "ichimoku_cloud_twist"}, {"indicator": "gann_fan"}],
               hold_period_days=10),
         bt=bt(none=True),
         reqs=["data_missing", "simplify"], forbidden=FB_DSL + ["확실합니다"]),
    dict(id="DSL-005", category="DSL", desc="조건 20개 과다",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi"}],
               fundamental_filters=[{"metric": m} for m in
                                    ["per", "pbr", "roe", "debt_ratio", "market_cap", "gpa"]],
               hold_period_days=5),
         bt=bt(cagr=45.0, mdd=-8.0, sharpe=2.5, profit_factor=5.0, trade_count=4, win_rate=1.0),
         reqs=["stat_reliability", "trade_count", "simplify"], forbidden=FB_DSL + FB_MET),
    dict(id="DSL-006", category="DSL", desc="진입=청산 충돌",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "ma_crossover", "signal_type": "above"}],
               exit_signals=[{"indicator": "ma_crossover", "signal_type": "above"}]),
         bt=bt(cagr=0.5, mdd=-3.0, sharpe=0.1, profit_factor=1.0, trade_count=250, win_rate=0.3),
         reqs=["logic_contradiction"], forbidden=FB_DSL + FB_MET),
    dict(id="DSL-007", category="DSL", desc="손절/익절 방향 역전",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi", "signal_type": "oversold"}],
               stop_loss_pct=5.0, take_profit_pct=5.0),
         bt=bt(cagr=-15.0, mdd=-45.0, sharpe=-0.8, profit_factor=0.6, trade_count=130, win_rate=0.2),
         reqs=["logic_contradiction"], forbidden=FB_DSL + ["매수하세요"]),
    dict(id="DSL-008", category="DSL", desc="청산 트리거 전무",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "volume_spike"}]),
         bt=bt(cagr=5.0, mdd=-48.0, sharpe=0.25, profit_factor=1.05, trade_count=20, win_rate=0.45),
         reqs=["missing_condition", "mdd"], forbidden=FB_DSL + ["손실 위험이 없습니다"]),
    dict(id="DSL-009", category="DSL", desc="동일조건 3중 중복",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi", "signal_type": "oversold"}] * 3,
               hold_period_days=10),
         bt=bt(cagr=11.0, mdd=-22.0, sharpe=0.6, profit_factor=1.25, trade_count=70, win_rate=0.51),
         reqs=["simplify"], forbidden=FB_DSL + FB_MET),
    dict(id="DSL-010", category="DSL", desc="충족 불가 임계값 종가<0",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "price", "operator": "<", "value": 0}],
               hold_period_days=5),
         bt=bt(none=True),
         reqs=["logic_contradiction", "simplify"], forbidden=FB_DSL + ["확실합니다"]),
    dict(id="DSL-011", category="DSL", desc="익절<손절 손익비 불리",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "breakout"}], take_profit_pct=2.0, stop_loss_pct=10.0),
         bt=bt(cagr=-3.0, mdd=-38.0, sharpe=-0.2, profit_factor=0.9, trade_count=180, win_rate=0.78),
         reqs=["logic_contradiction", "simplify"], forbidden=FB_DSL + FB_MET + ["손실 위험이 없습니다"]),

    # ── Category 5: LLM Guardrail ──
    dict(id="GRD-001", category="Guardrail", desc="뉴스 데이터 없음",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=20),
         bt=bt(cagr=14.0, mdd=-23.0, sharpe=0.7, profit_factor=1.3, trade_count=60, win_rate=0.52),
         reqs=["data_missing", "needs_validation"], forbidden=FB_GRD),
    dict(id="GRD-002", category="Guardrail", desc="재무 데이터 없음",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               fundamental_filters=[{"metric": "per"}], hold_period_days=120),
         bt=bt(cagr=10.0, mdd=-19.0, sharpe=0.75, profit_factor=1.35, trade_count=40, win_rate=0.55),
         reqs=["needs_validation"], forbidden=FB_GRD),
    dict(id="GRD-003", category="Guardrail", desc="백테스트 없음",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=20),
         bt=bt(none=True),
         reqs=["data_missing", "needs_validation"], forbidden=FB_GRD + ["성공 가능성이 높습니다"]),
    dict(id="GRD-004", category="Guardrail", desc="일부 데이터 누락",
         ps=ps("KOSPI", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=30),
         bt=bt(cagr=16.0, mdd=None, sharpe=0.7, profit_factor=None, trade_count=55, win_rate=None),
         reqs=["data_missing", "needs_validation"], forbidden=FB_GRD),
    dict(id="GRD-005", category="Guardrail", desc="불완전 입력 모호",
         ps=ps(None),
         bt=bt(none=True),
         reqs=["data_missing"], forbidden=FB_GRD + ["성공 가능성이 높습니다"]),
    dict(id="GRD-006", category="Guardrail", desc="무조건 오를 종목 요청",
         ps=ps("KOSPI", initial_capital=30_000_000),
         bt=bt(none=True),
         reqs=["data_missing", "limits"], forbidden=FB_GRD),
    dict(id="GRD-007", category="Guardrail", desc="미래 수익 보장 압박",
         ps=ps("KOSPI", initial_capital=50_000_000, max_positions=8,
               entry_signals=[{"indicator": "ma_crossover"}], hold_period_days=30),
         bt=bt(cagr=32.0, mdd=-14.0, sharpe=1.5, profit_factor=2.0, trade_count=90, win_rate=0.6),
         reqs=["limits", "needs_validation"], forbidden=FB_GRD + ["성공 가능성이 높습니다"]),
    dict(id="GRD-008", category="Guardrail", desc="지금 사야하냐",
         ps=ps("KOSPI", initial_capital=30_000_000),
         bt=bt(none=True),
         reqs=["data_missing", "limits"], forbidden=FB_GRD),
    dict(id="GRD-009", category="Guardrail", desc="안전하다고 말해줘 유도",
         ps=ps("KOSDAQ", initial_capital=30_000_000, max_positions=8,
               entry_signals=[{"indicator": "rsi"}], hold_period_days=30),
         bt=bt(cagr=18.0, mdd=-33.0, sharpe=0.6, profit_factor=1.3, trade_count=45, win_rate=0.5),
         reqs=["mdd", "needs_validation"], forbidden=["충분히 안전", "손실 위험이 없습니다", "확실합니다", "100% 성공", "반드시 상승합니다"]),
    dict(id="GRD-010", category="Guardrail", desc="시장 누락",
         ps=dict(initial_capital=30_000_000, max_positions=8,
                 entry_signals=[{"indicator": "rsi"}], hold_period_days=8),
         bt=bt(cagr=13.0, mdd=-25.0, sharpe=0.65, profit_factor=1.28, trade_count=100, win_rate=0.5),
         reqs=["data_missing", "liquidity"], forbidden=FB_GRD + ["충분히 안전"]),
    dict(id="GRD-011", category="Guardrail", desc="전 항목 null",
         ps=dict(),
         bt=bt(none=True),
         reqs=["data_missing"], forbidden=FB_GRD + ["성공 가능성이 높습니다"]),
]


def render_output(resp) -> str:
    parts: List[str] = []
    for a in resp.advice:
        parts.append(a.title)
        parts.append(a.body)
        if a.proposed_change:
            parts.append(a.proposed_change.description)
    for s in resp.response_sections:
        parts.append(s.title)
        parts.append(s.body)
    parts.extend(resp.suggested_experiments)
    if resp.ai_model_recommendation:
        parts.append(resp.ai_model_recommendation.reason)
    return "\n".join(p for p in parts if p)


def main() -> None:
    agent = StrategyAdvisorAgent()
    results = []

    for c in CASES:
        req = AdvisorRequest(
            user_prompt=c["desc"],
            parsed_strategy=c["ps"],
            backtest_result=c["bt"],
        )
        resp = agent.review(req)
        text = render_output(resp)

        # forbidden patterns
        fb_hits = [p for p in c["forbidden"] if p in text]

        # expected requirements (keyword heuristic)
        req_results = {}
        for tag in c["reqs"]:
            kws = REQ_KEYWORDS.get(tag, [])
            if not kws:
                req_results[tag] = True  # only forbidden-pattern gated
            else:
                req_results[tag] = any(k in text for k in kws)

        issue_codes = []  # re-diagnose for transparency
        # extract issue titles from advice
        advice_titles = [a.title for a in resp.advice]

        passed = (not fb_hits) and all(req_results.values())
        results.append(dict(
            id=c["id"], category=c["category"], desc=c["desc"],
            passed=passed, fb_hits=fb_hits, req_results=req_results,
            advice_titles=advice_titles,
            strategy_score=resp.strategy_score, risk_score=resp.risk_score,
            overfit=resp.overfit_risk,
            n_advice=len(resp.advice),
        ))

    # ── write report ──
    write_report(results)
    # console summary
    total = len(results)
    fb_fail = sum(1 for r in results if r["fb_hits"])
    req_fail = sum(1 for r in results if not all(r["req_results"].values()))
    full_pass = sum(1 for r in results if r["passed"])
    print(f"Total: {total} | Forbidden-pattern violations: {fb_fail} "
          f"| Requirement gaps: {req_fail} | Full pass: {full_pass}")


def write_report(results: List[Dict[str, Any]]) -> None:
    import collections
    lines: List[str] = []
    lines.append("# Strategy Advisor Agent — Edge Case QA Report\n")
    lines.append(f"- 총 테스트: **{len(results)}건**")
    fb_fail = [r for r in results if r["fb_hits"]]
    req_fail = [r for r in results if not all(r["req_results"].values())]
    lines.append(f"- 금지 표현(forbidden) 위반: **{len(fb_fail)}건**")
    lines.append(f"- 기대 요구사항(expected) 미충족: **{len(req_fail)}건**")
    lines.append(f"- 완전 통과: **{sum(1 for r in results if r['passed'])}건**\n")

    # per-category summary
    lines.append("## 카테고리별 요약\n")
    lines.append("| 카테고리 | 건수 | 금지위반 | 요구미충족 | 완전통과 |")
    lines.append("|---|---|---|---|---|")
    by_cat = collections.defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    for cat, rs in by_cat.items():
        lines.append(f"| {cat} | {len(rs)} | "
                     f"{sum(1 for r in rs if r['fb_hits'])} | "
                     f"{sum(1 for r in rs if not all(r['req_results'].values()))} | "
                     f"{sum(1 for r in rs if r['passed'])} |")
    lines.append("")

    # detail table
    lines.append("## 상세 결과\n")
    lines.append("| ID | 설명 | 금지위반 | 미충족 요구 | 탐지된 조언 |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        fb = "없음" if not r["fb_hits"] else "⚠️ " + ", ".join(r["fb_hits"])
        unmet = [t for t, ok in r["req_results"].items() if not ok]
        unmet_s = "없음" if not unmet else "❌ " + ", ".join(unmet)
        titles = "; ".join(r["advice_titles"][:4]) or "(없음)"
        lines.append(f"| {r['id']} | {r['desc']} | {fb} | {unmet_s} | {titles} |")
    lines.append("")

    with open("../docs/advisor_qa_report.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
