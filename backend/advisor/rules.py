"""
Strategy Advisor — Rule definitions.

Each Rule is a dataclass with an evaluate() method that returns an Issue or None.
Rules are grouped by domain: structure, risk, backtest, news.
All rules operate on normalised inputs from the diagnoser — no raw Pydantic models here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .schemas import Issue, Severity


# ─── Rule base ────────────────────────────────────────────────────────────────

@dataclass
class RuleContext:
    """Flat context passed to every rule."""
    # strategy fields
    has_exit_signals: bool = False
    filter_count: int = 0
    has_liquidity_filter: bool = False
    has_stop_loss: bool = False
    stop_loss_pct: Optional[float] = None        # positive number, e.g. 10.0
    has_take_profit: bool = False
    take_profit_pct: Optional[float] = None
    has_trailing_stop: bool = False
    max_positions: Optional[int] = None          # None = 미설정
    universe_size_estimate: int = 200            # KOSPI200=200, KOSPI=838, etc.
    entry_signal_count: int = 0
    has_ranking_entry: bool = False           # 모멘텀/상대강도 랭킹(수익률 상위) — 순위 자체가 진입
    has_ai_signal: bool = False
    hold_period_days: Optional[int] = None
    initial_capital: Optional[float] = None      # e.g. 10_000_000

    # backtest fields (None = not available)
    cagr: Optional[float] = None
    mdd: Optional[float] = None                  # negative, e.g. -0.35
    sharpe: Optional[float] = None
    profit_factor: Optional[float] = None
    trade_count: Optional[int] = None
    win_rate: Optional[float] = None
    backtest_available: bool = False

    # news fields (pre-aggregated by news_adapter)
    news_negative_ratio: float = 0.0             # 0.0 – 1.0
    news_positive_ratio: float = 0.0
    news_weighted_impact: float = 0.0            # signed, e.g. -0.4
    news_max_risk_level: str = "none"            # none/low/medium/high
    news_event_types: List[str] = field(default_factory=list)
    news_high_confidence_negative: int = 0       # count of high-conf negative articles
    has_fundamental_filters: bool = False
    filter_names: List[str] = field(default_factory=list)   # 사용자 표시용 필터명
    news_available: bool = False


def _issue(code: str, severity: Severity, message: str) -> Issue:
    return Issue(code=code, severity=severity, message=message)


# ─── Structure rules ──────────────────────────────────────────────────────────

def rule_missing_exit(ctx: RuleContext) -> Optional[Issue]:
    """전략에 명시적 청산 조건이 없을 때."""
    has_risk_exit = ctx.has_stop_loss or ctx.has_take_profit or ctx.has_trailing_stop
    has_hold_period = ctx.hold_period_days is not None
    if not ctx.has_exit_signals and not has_risk_exit and not has_hold_period:
        return _issue(
            "MISSING_EXIT_RULE",
            "high",
            "청산 조건이 없습니다. 손절/익절/보유기간 중 하나 이상을 반드시 설정하세요. "
            "청산 규칙 없이는 하락장에서 무한 손실 위험이 있습니다.",
        )
    return None


def rule_too_many_filters(ctx: RuleContext) -> Optional[Issue]:
    """필터가 너무 많으면 종목 수 부족 / 과최적화 가능성."""
    if ctx.filter_count > 5:
        return _issue(
            "TOO_MANY_FILTERS",
            "medium",
            f"재무 필터가 {ctx.filter_count}개로 과도합니다. "
            "필터가 많을수록 통과 종목이 줄어 과최적화 위험이 높아집니다. "
            "핵심 필터 3개 이하로 줄이는 것을 권장합니다.",
        )
    return None


def _liquidity_suggestion(
    capital: Optional[float],
    max_positions: int = 10,
) -> Optional[tuple[float, str]]:
    """
    포지션당 투자금의 10배 = 최소 필요 일평균거래대금 (10% ADV 원칙).
    의미있는 필터 기준이 나오지 않으면 None 반환 (필터 제안 불필요).
    """
    if capital is None:
        return 10.0, "10억"  # 자본금 미정의 시 보수적 기본값

    per_position = capital / max(max_positions or 10, 1)
    min_volume = per_position * 10  # 포지션이 일거래량의 10% 이내여야 슬리피지 무시 가능

    # 최소 기준(1억) 미만이면 상장 종목 대부분이 해당 → 의미없는 필터
    if min_volume < 100_000_000:
        return None

    if min_volume <= 300_000_000:
        return 3.0, "3억"
    if min_volume <= 500_000_000:
        return 5.0, "5억"
    if min_volume <= 1_000_000_000:
        return 10.0, "10억"
    return 30.0, "30억"


def rule_no_liquidity_filter(ctx: RuleContext) -> Optional[Issue]:
    """유동성 필터(거래대금) 없을 때 — 포지션 크기 기반으로 필요성 판단."""
    if ctx.has_liquidity_filter or ctx.universe_size_estimate <= 200:
        return None

    result = _liquidity_suggestion(ctx.initial_capital, ctx.max_positions)
    if result is None:
        return None  # 포지션 크기 대비 의미있는 필터 기준이 없음

    _, label = result
    return _issue(
        "NO_LIQUIDITY_FILTER",
        "medium",
        f"거래대금(유동성) 필터가 없습니다. "
        f"유동성 낮은 종목은 실제 매매 시 슬리피지가 극심해 백테스트와 실거래 괴리가 커집니다. "
        f"일평균거래대금 {label} 이상 필터를 추가하세요.",
    )


def rule_no_entry_signals(ctx: RuleContext) -> Optional[Issue]:
    """진입 신호가 전혀 없을 때.

    재무 필터, 기술적 신호, 또는 모멘텀/상대강도 랭킹(수익률 상위 선정) 중
    하나라도 있으면 진입 규칙이 정의된 것으로 본다. 랭킹은 순위 자체가 진입이다.
    """
    if (
        ctx.entry_signal_count == 0
        and not ctx.has_fundamental_filters
        and not ctx.has_ranking_entry
    ):
        return _issue(
            "NO_ENTRY_SIGNALS",
            "high",
            "진입 신호가 정의되지 않았습니다. "
            "기술적 지표 또는 재무 조건 중 하나 이상의 매수 조건이 필요합니다.",
        )
    return None


# ─── Risk rules ───────────────────────────────────────────────────────────────

def rule_no_stop_loss(ctx: RuleContext) -> Optional[Issue]:
    if not ctx.has_stop_loss and not ctx.has_trailing_stop:
        return _issue(
            "NO_STOP_LOSS",
            "high",
            "손절 조건이 없습니다. 하락장 또는 개별 종목 급락 시 큰 손실을 방어할 수단이 없습니다. "
            "손절 8~15% 또는 트레일링 스탑 설정을 강력히 권장합니다.",
        )
    return None


def rule_no_take_profit(ctx: RuleContext) -> Optional[Issue]:
    """손절은 있는데 익절 기준이 없을 때 — 수익 실현 시점 불명확."""
    if ctx.has_take_profit or ctx.has_trailing_stop or ctx.has_exit_signals:
        return None  # 명시적 익절 수단이 있음
    if not ctx.has_stop_loss:
        return None  # MISSING_EXIT_RULE / NO_STOP_LOSS가 더 우선적으로 다룸
    return _issue(
        "NO_TAKE_PROFIT",
        "low",
        "익절 기준이 없습니다. 손절은 설정되어 있지만 수익 실현 시점이 불명확합니다. "
        "주가가 크게 올라도 언제 팔아야 할지 모르면 심리적 판단이 어렵습니다. "
        "익절 비율 또는 트레일링 스탑 추가를 검토하세요.",
    )


def rule_too_tight_stop(ctx: RuleContext) -> Optional[Issue]:
    """손절이 너무 타이트하면 정상 변동성에서도 잦은 청산 발생."""
    pct = ctx.stop_loss_pct or (ctx.has_trailing_stop and 5.0)
    if pct and pct < 3.0:
        return _issue(
            "TOO_TIGHT_STOP",
            "medium",
            f"손절 {pct:.1f}%는 일봉 변동성 대비 너무 타이트합니다. "
            "정상적인 가격 흔들림에도 청산되어 거래비용만 증가합니다. "
            "최소 5~8% 이상으로 조정하세요.",
        )
    return None


def rule_position_overexposed(ctx: RuleContext) -> Optional[Issue]:
    """최대 종목 수가 너무 적으면 개별 종목 위험 집중."""
    if ctx.max_positions is not None and ctx.max_positions <= 3:
        return _issue(
            "POSITION_OVEREXPOSED",
            "medium",
            f"최대 보유 종목이 {ctx.max_positions}개로 집중도가 매우 높습니다. "
            "개별 종목 이슈 발생 시 포트폴리오 전체가 크게 흔들릴 수 있습니다. "
            "최소 5종목 이상 분산을 권장합니다.",
        )
    return None


# ─── Backtest-based rules ─────────────────────────────────────────────────────

def rule_low_trade_count(ctx: RuleContext) -> Optional[Issue]:
    if not ctx.backtest_available or ctx.trade_count is None:
        return None
    if ctx.trade_count < 30:
        return _issue(
            "LOW_TRADE_COUNT",
            "high" if ctx.trade_count < 15 else "medium",
            f"백테스트 거래 횟수가 {ctx.trade_count}회로 매우 적습니다. "
            "통계적 신뢰도가 낮아 성과 지표가 의미 없을 수 있습니다. "
            "최소 30회 이상 거래가 발생하도록 기간을 늘리거나 조건을 완화하세요.",
        )
    return None


def rule_high_mdd(ctx: RuleContext) -> Optional[Issue]:
    if not ctx.backtest_available or ctx.mdd is None:
        return None
    if ctx.mdd < -0.30:
        sev: Severity = "high" if ctx.mdd < -0.50 else "medium"
        return _issue(
            "HIGH_MDD",
            sev,
            f"최대낙폭(MDD)이 {ctx.mdd*100:.1f}%입니다. "
            "실거래에서 이 수준의 손실을 견디기 매우 어렵습니다. "
            "손절 강화, 포지션 축소, 분산 확대를 검토하세요.",
        )
    return None


def rule_overfit_suspect(ctx: RuleContext) -> Optional[Issue]:
    """고수익 + 낮은 거래 수 + 많은 필터 = 과최적화 의심."""
    if not ctx.backtest_available:
        return None
    high_cagr = ctx.cagr is not None and ctx.cagr > 0.40
    low_trades = ctx.trade_count is not None and ctx.trade_count < 50
    many_filters = ctx.filter_count >= 4
    if high_cagr and (low_trades or many_filters):
        return _issue(
            "OVERFIT_SUSPECT",
            "high",
            f"CAGR {(ctx.cagr or 0)*100:.0f}%이지만 거래 수({ctx.trade_count})가 적거나 필터가 많습니다. "
            "과최적화(커브피팅) 가능성이 높습니다. "
            "Walk-forward 검증 또는 Monte Carlo 시뮬레이션을 반드시 실행하세요.",
        )
    return None


def rule_low_sharpe(ctx: RuleContext) -> Optional[Issue]:
    if not ctx.backtest_available or ctx.sharpe is None:
        return None
    if ctx.sharpe < 0.5:
        return _issue(
            "LOW_SHARPE",
            "medium",
            f"Sharpe Ratio {ctx.sharpe:.2f}는 무위험 수익률 대비 위험 조정 수익이 낮습니다. "
            "수익률보다 변동성이 과도한 전략입니다. "
            "손절/포지션 크기 조정으로 변동성을 낮추세요.",
        )
    return None


# ─── News-based rules ─────────────────────────────────────────────────────────

def rule_negative_news_cluster(ctx: RuleContext) -> Optional[Issue]:
    """부정 뉴스가 60% 이상 집중."""
    if not ctx.news_available:
        return None
    if ctx.news_negative_ratio >= 0.6:
        return _issue(
            "NEGATIVE_NEWS_CLUSTER",
            "high" if ctx.news_negative_ratio >= 0.75 else "medium",
            f"관련 뉴스의 {ctx.news_negative_ratio*100:.0f}%가 부정적입니다. "
            "현재 뉴스 환경에서 매수 전략은 역풍을 받을 수 있습니다. "
            "진입 조건 강화 또는 포지션 축소를 고려하세요.",
        )
    return None


def rule_high_news_risk_alert(ctx: RuleContext) -> Optional[Issue]:
    if not ctx.news_available:
        return None
    if ctx.news_max_risk_level == "high":
        return _issue(
            "HIGH_NEWS_RISK_ALERT",
            "high",
            "하나 이상의 종목에서 높은 뉴스 리스크 경보가 발생했습니다. "
            "규제 조사, 소송, 회계 이슈 등 기업 고유 위험이 감지되었습니다. "
            "해당 종목을 유니버스에서 제외하거나 포지션 크기를 대폭 줄이세요.",
        )
    if ctx.news_max_risk_level == "medium":
        return _issue(
            "HIGH_NEWS_RISK_ALERT",
            "medium",
            "일부 종목에서 중간 수준의 뉴스 리스크가 감지되었습니다. "
            "포지션 크기 축소 또는 손절 강화를 고려하세요.",
        )
    return None


def rule_event_driven_volatility(ctx: RuleContext) -> Optional[Issue]:
    """이벤트 기반 변동성 경고: 다수의 high-impact 이벤트 감지."""
    if not ctx.news_available:
        return None
    volatile_events = {
        "earnings_beat", "earnings_miss", "rights_offering",
        "convertible_bond", "regulatory_probe", "lawsuit_loss",
        "factory_fire", "accounting_issue", "delisting_risk",
    }
    detected = [e for e in ctx.news_event_types if e in volatile_events]
    if len(detected) >= 2:
        return _issue(
            "EVENT_DRIVEN_VOLATILITY",
            "medium",
            f"단기 변동성을 유발하는 이벤트({', '.join(detected[:3])})가 감지되었습니다. "
            "이벤트 직후 갭 상하는 손절/익절을 무력화할 수 있습니다. "
            "트레일링 스탑 또는 이벤트 기간 진입 회피를 검토하세요.",
        )
    return None


def rule_value_trap_risk(ctx: RuleContext) -> Optional[Issue]:
    """저PBR/저PER + 부정 뉴스 = 가치 함정 가능성."""
    if not ctx.news_available or not ctx.has_fundamental_filters:
        return None
    fundamental_negative = ctx.news_high_confidence_negative >= 2 and ctx.news_negative_ratio >= 0.5
    if fundamental_negative:
        return _issue(
            "VALUE_TRAP_RISK",
            "medium",
            "저평가 재무 지표를 사용하지만 부정 뉴스가 다수 감지됩니다. "
            "'저렴한 이유'가 있는 가치 함정(value trap)일 수 있습니다. "
            "ROE, 부채비율 등 질적 지표를 추가 필터로 결합하세요.",
        )
    return None


# ─── Rule registry ────────────────────────────────────────────────────────────

ALL_RULES = [
    # structure
    rule_missing_exit,
    rule_too_many_filters,
    rule_no_liquidity_filter,
    rule_no_entry_signals,
    # risk
    rule_no_stop_loss,
    rule_no_take_profit,
    rule_too_tight_stop,
    rule_position_overexposed,
    # backtest
    rule_low_trade_count,
    rule_high_mdd,
    rule_overfit_suspect,
    rule_low_sharpe,
    # news
    rule_negative_news_cluster,
    rule_high_news_risk_alert,
    rule_event_driven_volatility,
    rule_value_trap_risk,
]
