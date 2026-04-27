"""
Strategy Advisor — Suggestion Engine.

Maps diagnosed Issues + RuleContext → actionable Recommendations.
Each issue code has a corresponding recommendation builder.
Additional news-driven and backtest-driven recommendations are appended.
"""

from __future__ import annotations

from typing import List, Optional

from .news_adapter import NormalizedNewsSignals
from .rules import RuleContext, _liquidity_suggestion
from .schemas import (
    AIModelRecommendation,
    AdviceItem,
    Issue,
    OverfitRisk,
    ProposedChange,
    Recommendation,
)


def _rec(
    type_: str,
    priority: int,
    title: str,
    reason: str,
    change: Optional[ProposedChange] = None,
) -> Recommendation:
    return Recommendation(
        type=type_,
        priority=priority,
        title=title,
        reason=reason,
        proposed_change=change,
    )


def _no_liquidity_rec(ctx: RuleContext) -> Recommendation:
    result = _liquidity_suggestion(ctx.initial_capital, ctx.max_positions)
    amount, label = result if result else (10.0, "10억")
    return _rec(
        "filter",
        2,
        f"거래대금 필터 추가 (일평균 {label} 이상)",
        "유동성 낮은 종목은 실거래 슬리피지가 커서 백테스트와 실거래 수익이 크게 다릅니다.",
        ProposedChange(
            field="fundamental_filters",
            action="add",
            value={"metric": "trading_value", "operator": ">=", "value": amount},
            description=f"일평균거래대금 {label} 이상 필터 추가",
        ),
    )


# ─── Issue-driven recommendations ────────────────────────────────────────────

_ISSUE_RECS = {
    "MISSING_EXIT_RULE": lambda ctx: _rec(
        "risk_management", 1,
        "손절 조건 추가",
        "청산 규칙 없이는 장기 하락 시 손실이 무제한 누적됩니다.",
        ProposedChange(field="stop_loss_pct", action="set", value=10.0,
                       description="매수가 대비 10% 손절 설정"),
    ),
    "NO_STOP_LOSS": lambda ctx: _rec(
        "risk_management", 1,
        "손절 또는 트레일링 스탑 추가",
        "손절이 없으면 개별 종목 급락 방어가 불가능합니다.",
        ProposedChange(field="stop_loss_pct", action="set", value=10.0,
                       description="10% 손절 또는 트레일링 스탑 15% 중 선택"),
    ),
    "NO_TAKE_PROFIT": lambda _ctx: _rec(
        "risk_management", 3,
        "익절 또는 트레일링 스탑 추가",
        "수익 실현 기준이 없으면 주가가 크게 올라도 언제 팔지 판단하기 어렵습니다. "
        "고정 익절 또는 트레일링 스탑으로 수익을 자동 확정하세요.",
        ProposedChange(
            field="take_profit_pct",
            action="set",
            value=20.0,
            description="20% 익절 설정 또는 트레일링 스탑 15% 중 선택",
        ),
    ),
    "TOO_TIGHT_STOP": lambda ctx: _rec(
        "risk_management", 2,
        f"손절 완화 ({(ctx.stop_loss_pct or 3):.1f}% → 7~10%)",
        "너무 타이트한 손절은 정상 변동성에서 불필요한 청산을 유발합니다.",
        ProposedChange(field="stop_loss_pct", action="modify", value=8.0,
                       description="손절을 8%로 완화"),
    ),
    "NO_ENTRY_SIGNALS": lambda ctx: _rec(
        "structure", 1,
        "진입 신호 추가 — RSI·MA 크로스·MACD 중 하나 이상",
        "매수 조건이 없으면 전략이 실행되지 않습니다. "
        "기술적 지표(RSI, MA 크로스오버, MACD 등) 또는 재무 조건 중 하나 이상을 설정하세요.",
        ProposedChange(
            field="entry_signals",
            action="add",
            value={"indicator": "rsi", "signal_type": "oversold"},
            description="RSI 30 이하 과매도 매수 신호 추가 (또는 다른 지표로 교체)",
        ),
    ),
    "VALUE_TRAP_RISK": lambda _ctx: _rec(
        "filter", 3,
        "가치 함정 방어 — ROE·부채비율 필터 추가",
        "저평가 지표(PER·PBR)만으로는 실적 악화 종목을 걸러내기 어렵습니다. "
        "ROE 또는 부채비율 필터를 추가해 질적 요소를 결합하세요.",
        ProposedChange(
            field="fundamental_filters",
            action="add",
            value={"metric": "roe_or_gpa", "operator": ">=", "value": 10.0},
            description="ROE 10% 이상 필터 추가",
        ),
    ),
    "NO_LIQUIDITY_FILTER": lambda ctx: _no_liquidity_rec(ctx),
    "TOO_MANY_FILTERS": lambda ctx: _rec(
        "filter", 3,
        f"재무 필터 축소 ({ctx.filter_count}개 → 3개 이하)",
        "과도한 필터는 통과 종목 수를 급감시켜 과최적화 위험을 높입니다.",
        ProposedChange(field="fundamental_filters", action="modify",
                       value=None, description="필터를 PER + PBR + 거래대금 3개로 줄이기"),
    ),
    "POSITION_OVEREXPOSED": lambda ctx: _rec(
        "risk_management", 2,
        f"최대 종목 수 확대 ({ctx.max_positions if ctx.max_positions is not None else '미설정'}개 → 5~10개)",
        "집중 포트폴리오는 개별 종목 이벤트에 크게 노출됩니다.",
        ProposedChange(field="max_positions", action="set", value=5,
                       description="최소 5종목 분산 보유"),
    ),
    "LOW_TRADE_COUNT": lambda ctx: _rec(
        "validation", 2,
        "백테스트 기간 연장 또는 진입 조건 완화",
        f"거래 횟수 {ctx.trade_count}회는 통계적 유의성을 보장하기 어렵습니다.",
        ProposedChange(field="backtest_period", action="modify", value="5y",
                       description="백테스트 기간을 5년으로 연장"),
    ),
    "HIGH_MDD": lambda ctx: _rec(
        "risk_management", 1,
        f"MDD 개선 (현재 {(ctx.mdd or 0)*100:.0f}%) — 손절 + 포지션 크기 조정",
        "MDD가 30% 초과 시 실거래에서 전략을 포기하는 투자자가 많습니다.",
        ProposedChange(field="stop_loss_pct", action="set", value=12.0,
                       description="손절 12% 설정 + 최대 보유 종목 수 10개로 분산"),
    ),
    "OVERFIT_SUSPECT": lambda ctx: _rec(
        "validation", 1,
        "Walk-forward 검증 실행",
        "높은 수익률과 낮은 거래 수는 과최적화의 전형적 패턴입니다. "
        "미래 데이터로 검증이 필수입니다.",
        ProposedChange(field="_meta", action="set", value="walk_forward",
                       description="Walk-forward 검증 실행 후 out-of-sample 성과 확인"),
    ),
    "LOW_SHARPE": lambda ctx: _rec(
        "risk_management", 3,
        "변동성 감소 — 손절 강화 또는 포지션 크기 축소",
        "Sharpe가 낮으면 수익 대비 위험이 과도합니다.",
        ProposedChange(field="max_positions", action="modify", value=None,
                       description="포지션당 비중을 줄여 포트폴리오 변동성 감소"),
    ),
}


def _build_news_recommendations(
    news: NormalizedNewsSignals,
    issue_codes: set,
) -> List[Recommendation]:
    recs: List[Recommendation] = []

    if "NEGATIVE_NEWS_CLUSTER" in issue_codes:
        recs.append(_rec(
            "news_driven", 2,
            "부정 뉴스 환경 — 진입 조건 강화",
            f"부정 뉴스 비중 {news.negative_ratio*100:.0f}%: 현재 시장 정서가 불리합니다. "
            "RSI 과매도 조건 강화 또는 진입 신호 수 늘리기를 고려하세요.",
        ))

    if "HIGH_NEWS_RISK_ALERT" in issue_codes:
        recs.append(_rec(
            "news_driven", 1,
            "고위험 뉴스 종목 제외 또는 포지션 축소",
            "기업 고유 위험(규제·소송·회계 이슈)이 감지된 종목은 예측 불가 하락 위험이 있습니다.",
            ProposedChange(field="max_positions", action="modify", value=None,
                           description="해당 종목 제외 또는 포지션 크기 50% 축소"),
        ))

    if "EVENT_DRIVEN_VOLATILITY" in issue_codes:
        recs.append(_rec(
            "news_driven", 2,
            "트레일링 스탑 추가 — 이벤트 변동성 대응",
            "실적·소송 등 이벤트 뉴스 후 갭 하락은 고정 손절을 무력화합니다. "
            "트레일링 스탑으로 수익 보호를 강화하세요.",
            ProposedChange(field="trailing_stop_pct", action="set", value=15.0,
                           description="최고가 대비 15% 트레일링 스탑 추가"),
        ))

    if news.available and news.positive_ratio >= 0.6 and news.weighted_impact > 0.3:
        recs.append(_rec(
            "news_driven", 3,
            "긍정 뉴스 모멘텀 — 보유 기간 연장 고려",
            f"가중 임팩트 {news.weighted_impact:+.2f}, 긍정 뉴스 비중 {news.positive_ratio*100:.0f}%. "
            "강한 긍정 모멘텀 환경에서는 보유 기간을 늘리면 추가 수익 가능성이 있습니다.",
            ProposedChange(field="hold_period_days", action="modify", value=None,
                           description="현재 보유 기간의 1.5~2배로 연장 검토"),
        ))

    return recs


def _build_experiments(
    ctx: RuleContext,
    issues: List[Issue],
    news: NormalizedNewsSignals,
) -> List[str]:
    exps: List[str] = []
    issue_codes = {i.code for i in issues}

    exps.append("Monte Carlo 시뮬레이션 — 수익률 신뢰 구간 확인 (±2σ 범위가 양수인지 검증)")

    if "OVERFIT_SUSPECT" in issue_codes or ctx.filter_count >= 3:
        exps.append("Walk-forward 검증 — IS 기간 3년 + OOS 기간 1년으로 실제 예측력 검증")

    if not ctx.has_trailing_stop:
        exps.append("트레일링 스탑 15% 추가 후 MDD/Sharpe 변화 비교")

    if ctx.max_positions is not None and ctx.max_positions <= 5:
        exps.append("최대 보유 종목 수 10개 vs 20개 비교 백테스트 — 분산 효과 정량화")

    if ctx.universe_size_estimate > 500 and not ctx.has_liquidity_filter:
        result = _liquidity_suggestion(ctx.initial_capital, ctx.max_positions)
        if result:
            _, label = result
            exps.append(f"거래대금 {label} 필터 적용 후 수익률 및 MDD 비교")

    if not ctx.has_ai_signal:
        exps.append("AI 예측 신호 추가 후 성과 비교 — AI 예측 레이어 효과 검증")

    if news.available and abs(news.weighted_impact) > 0.2:
        exps.append("뉴스 임팩트 점수 임계값(0.3) 기반 진입 필터 추가 후 Sharpe 변화 확인")

    return exps[:5]


def _build_ai_recommendation(ctx: RuleContext) -> AIModelRecommendation:
    if ctx.has_ai_signal:
        return AIModelRecommendation(
            recommended=True,
            reason="이미 AI 신호를 활용 중입니다. AI 예측 임계값을 60~70%로 조정해 정밀도를 높이세요.",
        )
    if ctx.entry_signal_count <= 1 or (ctx.cagr is not None and ctx.cagr < 0.10):
        return AIModelRecommendation(
            recommended=True,
            reason="진입 신호가 단순하거나 수익률이 낮습니다. "
                   "AI 예측 신호(상승 확률 70% 이상) 조건을 추가하면 정밀도를 크게 높일 수 있습니다.",
        )
    return AIModelRecommendation(
        recommended=False,
        reason="현재 전략 구조로도 충분한 진입 필터가 있습니다. "
               "AI 예측 신호 추가 시 거래 횟수가 줄어들 수 있으므로 비교 테스트 후 결정하세요.",
    )


def _priority_to_severity(priority: int) -> str:
    if priority <= 1:
        return "high"
    if priority <= 3:
        return "medium"
    return "low"


def _overfit_info_advice(overfit_risk: OverfitRisk, ctx: RuleContext, issue_codes: set) -> AdviceItem:
    if overfit_risk == "high":
        body = (
            "거래 횟수 대비 수익률이 지나치게 높거나 과최적화 패턴이 감지되었습니다. "
            "이 전략은 과거 데이터에 과도하게 맞춰졌을 가능성이 높아 실거래에서 성과가 크게 달라질 수 있습니다. "
            "Walk-forward 검증으로 실제 예측력을 반드시 확인하세요."
        )
        return AdviceItem(severity="high", title="과최적화 위험 높음", body=body)
    if overfit_risk == "medium":
        reasons = []
        if ctx.filter_count >= 4:
            reasons.append(f"필터 조건이 {ctx.filter_count}개로 많아 특정 과거 구간에 맞춰졌을 수 있습니다")
        if "LOW_TRADE_COUNT" in issue_codes:
            reasons.append("거래 횟수가 적어 통계적 신뢰도가 충분하지 않습니다")
        reason_text = ", ".join(reasons) + "." if reasons else "필터 과다 또는 거래 횟수 부족 패턴이 감지되었습니다."
        body = (
            f"{reason_text} "
            "Walk-forward 검증으로 미래 구간에서도 유효한 전략인지 확인하세요."
        )
        return AdviceItem(severity="medium", title="과최적화 위험 중간", body=body)
    # low
    reasons = []
    if ctx.backtest_available and ctx.trade_count is not None and ctx.trade_count >= 50:
        reasons.append(f"거래 횟수 {ctx.trade_count}회로 통계적 신뢰도가 충분합니다")
    if ctx.backtest_available and ctx.cagr is not None and ctx.cagr <= 0.35:
        reasons.append(f"CAGR {ctx.cagr*100:.0f}%로 비현실적인 고수익 패턴이 없습니다")
    if ctx.filter_count < 4:
        if ctx.filter_names:
            names = ", ".join(ctx.filter_names)
            reasons.append(f"필터 조건 {ctx.filter_count}개({names})로 적정합니다")
        else:
            reasons.append(f"필터 조건 {ctx.filter_count}개로 적정합니다")
    reason_text = ", ".join(reasons) + "." if reasons else "과최적화 패턴이 감지되지 않았습니다."
    body = (
        f"{reason_text} "
        "전략 구조가 특정 과거 구간에 과도하게 맞춰졌을 가능성은 낮습니다. "
        "단, 이는 과최적화 측면만의 평가이며 아래의 리스크 관리·청산 조건 개선과는 별개입니다."
    )
    return AdviceItem(severity="low", title="과최적화 위험 낮음", body=body)


# ─── Public API ───────────────────────────────────────────────────────────────

class SuggestionEngine:
    def generate(
        self,
        issues: List[Issue],
        ctx: RuleContext,
        news: NormalizedNewsSignals,
        overfit_risk: OverfitRisk = "low",
    ) -> tuple[List[AdviceItem], List[str], AIModelRecommendation]:
        """
        Returns (advice, suggested_experiments, ai_model_recommendation).
        진단(Issue)과 해결 방법(Recommendation)을 AdviceItem으로 통합.
        """
        issue_codes = {i.code for i in issues}
        advice: List[AdviceItem] = [_overfit_info_advice(overfit_risk, ctx, issue_codes)]
        seen_titles: set = {advice[0].title}

        for issue in issues:
            builder = _ISSUE_RECS.get(issue.code)
            if builder:
                rec = builder(ctx)
                if rec.title not in seen_titles:
                    seen_titles.add(rec.title)
                    advice.append(AdviceItem(
                        severity=issue.severity,
                        title=rec.title,
                        body=rec.reason,
                        proposed_change=rec.proposed_change,
                    ))
            else:
                if issue.message not in seen_titles:
                    seen_titles.add(issue.message)
                    advice.append(AdviceItem(
                        severity=issue.severity,
                        title=issue.message,
                        body="",
                        proposed_change=None,
                    ))

        for rec in _build_news_recommendations(news, issue_codes):
            if rec.title not in seen_titles:
                seen_titles.add(rec.title)
                advice.append(AdviceItem(
                    severity=_priority_to_severity(rec.priority),
                    title=rec.title,
                    body=rec.reason,
                    proposed_change=rec.proposed_change,
                ))

        experiments = _build_experiments(ctx, issues, news)
        ai_rec = _build_ai_recommendation(ctx)

        return advice, experiments, ai_rec
