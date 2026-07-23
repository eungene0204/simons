"""단일 종목 전략 사전 검증 — 프로파일 기반 비차단 리뷰 (FR-STR-068b).

파싱된 단일 종목 전략(ParsedStrategy)을 StockResearchProfile과 대조해:
  - 진입 조건의 과거 신호 발생 횟수가 희소하면 경고(기준 완화/기간 연장 제안)
  - 신호가 과도하게 빈번하면 거래비용·슬리피지 경고
  - 재무 조건이 데이터 미보유면 '지원 불가' 안내, 보유면 PIT(공시 시점) 적용 사실 안내
  - 프로파일의 데이터 품질 경고(짧은 이력·결측·상장폐지)를 전달

모든 결과는 비차단 notices 문자열이다 — 조건을 임의로 삭제하거나 실행을 막지 않고,
사용자에게 정확한 원인과 대안을 알린다(백테스트 최소 조건 게이트와 별개 층).
프로파일 조회 실패 시 조용히 빈 목록을 반환한다(파싱 흐름을 절대 깨지 않는다).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from .stock_profile import StockResearchProfile, get_stock_profile
from .stock_question_templates import (
    FREQUENT_SIGNAL_PER_YEAR,
    SPARSE_SIGNAL_MIN,
    select_stock_questions,
    strategy_category_options,
)

logger = logging.getLogger(__name__)

# 재무 지표 metric → 프로파일 커버리지 키(동일 명칭 — parquet 컬럼 기준).
_PROFILE_FUND_METRICS = {
    "per", "pbr", "psr", "roe_or_gpa", "debt_ratio", "dividend_yield",
    "operating_margin", "revenue_growth",
}

_METRIC_LABELS = {
    "per": "PER", "pbr": "PBR", "psr": "PSR", "roe_or_gpa": "ROE",
    "debt_ratio": "부채비율", "dividend_yield": "배당수익률",
    "operating_margin": "영업이익률", "revenue_growth": "매출액증가율",
}


def _nearest(candidates, value):
    return min(candidates, key=lambda c: abs(c - value))


def _signal_stat_for(profile: StockResearchProfile, sig) -> tuple[Optional[str], Optional[int], Optional[float]]:
    """TechnicalSignal → (설명 라벨, 발생 횟수, 연간 빈도). 격자에 없는 지표는 (None, None, None).

    격자 근사: 파라미터가 격자와 정확히 일치하지 않으면 가장 가까운 격자 항목으로
    근사하고 라벨에 격자 기준을 명시한다(값을 지어내지 않음 — '유사 조건 기준' 안내).
    """
    stats = profile.signal_statistics

    def read(key: str, label: str):
        count = stats.get(f"{key}_count")
        per_year = stats.get(f"{key}_per_year")
        if count is None:
            return (None, None, None)
        return (label, int(count), float(per_year) if per_year is not None else None)

    ind = sig.indicator
    if ind == "rsi" and sig.signal_type == "buy" and sig.value is not None \
            and (sig.operator or "<=").startswith("<"):
        thr = _nearest((20, 25, 30), float(sig.value))
        return read(f"rsi_below_{thr}", f"RSI {thr} 이하 진입(유사 조건 기준)")
    if ind == "rsi" and sig.signal_type == "sell" and sig.value is not None \
            and (sig.operator or ">=").startswith(">"):
        thr = _nearest((70, 75, 80), float(sig.value))
        return read(f"rsi_above_{thr}", f"RSI {thr} 이상 청산(유사 조건 기준)")
    if ind in ("ma_crossover", "ema") and sig.signal_type == "buy" \
            and sig.short_period and sig.long_period:
        pair = min(
            ((5, 20), (10, 60), (20, 120)),
            key=lambda p: abs(p[0] - sig.short_period) + abs(p[1] - sig.long_period),
        )
        return read(f"golden_cross_{pair[0]}_{pair[1]}",
                    f"{pair[0]}/{pair[1]}일 골든크로스(유사 조건 기준)")
    if ind == "macd" and sig.signal_type == "buy":
        return read("macd_buy_cross", "MACD 상향 교차")
    if ind == "bollinger_bands" and sig.signal_type == "buy":
        return read("bollinger_lower_touch", "볼린저밴드 하단 도달")
    if ind == "breakout" and sig.signal_type == "buy":
        lb = _nearest((20, 60, 120), sig.lookback_period or 60)
        return read(f"breakout_{lb}d", f"{lb}일 신고가 돌파(유사 조건 기준)")
    if ind == "volume_spike" and sig.signal_type == "buy":
        return read("volume_spike_3x", "거래량 급증(20일 평균 3배 기준)")
    if ind == "stochastic" and sig.signal_type == "buy":
        return read("stochastic_buy_cross", "스토캐스틱 상향 교차")
    if ind == "cci" and sig.signal_type == "buy":
        return read("cci_below_minus_100", "CCI -100 이하 진입(유사 조건 기준)")
    return (None, None, None)


def review_single_asset_strategy(
    parsed, profile: Optional[StockResearchProfile] = None,
) -> List[str]:
    """단일 종목 전략의 비차단 검증 안내 목록을 반환한다(실패 시 빈 목록)."""
    targets = list(getattr(parsed, "target_symbols", None) or [])
    if len(targets) != 1:
        return []
    symbol = targets[0]
    try:
        if profile is None:
            profile = get_stock_profile(symbol)
        if profile is None:
            return []
        return _review(parsed, profile)
    except Exception:
        logger.warning("단일 종목 프로파일 리뷰 실패: %s", symbol, exc_info=True)
        return []


def _review(parsed, profile: StockResearchProfile) -> List[str]:
    notices: List[str] = []

    # 1) 데이터 품질 경고(프로파일이 이미 계산한 사실 전달). 재무 데이터 시작일 안내는
    # 전략이 실제로 재무 조건을 쓸 때만 의미가 있어 그 경우에만 전달한다(노이즈 방지).
    uses_fundamentals = bool(getattr(parsed, "fundamental_filters", None))
    for w in profile.data_quality_warnings:
        if w.startswith("재무 지표는") and not uses_fundamentals:
            continue
        notices.append(w)

    # 2) 진입 신호 희소/과다 경고.
    for sig in getattr(parsed, "entry_signals", None) or []:
        label, count, per_year = _signal_stat_for(profile, sig)
        if label is None or count is None:
            continue
        if count < SPARSE_SIGNAL_MIN:
            notices.append(
                f"선택한 진입 조건({label})은 이 종목의 과거 데이터에서 {count}회만 발생했습니다. "
                "통계적으로 신뢰할 수 있는 결과를 얻기 어려울 수 있습니다. "
                "기준을 완화하거나 백테스트 기간을 늘리는 것을 고려해 주세요."
            )
        elif per_year is not None and per_year > FREQUENT_SIGNAL_PER_YEAR:
            notices.append(
                f"선택한 진입 조건({label})은 연평균 약 {per_year:.0f}회로 매우 자주 발생합니다. "
                "거래비용과 슬리피지의 영향을 크게 받을 수 있습니다. "
                "추가 필터나 최소 보유기간 설정을 고려해 주세요."
            )

    # 3) 재무 조건: 미보유 데이터는 지원 불가 안내, 보유 데이터는 PIT 적용 사실 안내.
    pit_metrics: List[str] = []
    for f in getattr(parsed, "fundamental_filters", None) or []:
        metric = getattr(f, "metric", None)
        if metric not in _PROFILE_FUND_METRICS:
            continue
        label = _METRIC_LABELS.get(metric, metric.upper())
        cov = profile.data_coverage.get(metric)
        if cov is None or not cov.available:
            notices.append(
                f"{profile.name}에는 {label} 데이터가 없거나 백테스트에 사용할 수 있는 충분한 "
                f"이력이 없습니다. 이 조건은 현재 지원할 수 없습니다. 기술적 지표(이동평균·RSI·"
                "거래량 등) 조건은 사용할 수 있습니다."
            )
        else:
            pit_metrics.append(f"{label}({cov.start_date}~)")
    if pit_metrics:
        notices.append(
            f"단일 종목 전략의 재무 조건({', '.join(pit_metrics)})은 종목 선별이 아니라 이 종목의 "
            "당시 값 기준 진입 신호로 적용되며, 각 수치는 실제 공시 반영 시점 이후에만 사용됩니다"
            "(미래 참조 편향 방지)."
        )
    return notices


# ─── API/프론트용 프로파일 요약 payload (§17 계약) ────────────────────────────────

def profile_summary_payload(
    profile: StockResearchProfile, *, include_advanced: bool = False,
) -> dict:
    selection = select_stock_questions(profile, include_advanced=include_advanced)
    ohlcv = profile.data_coverage.get("ohlcv")
    data_period = (
        f"{ohlcv.start_date} ~ {ohlcv.end_date}"
        if ohlcv and ohlcv.available else None
    )
    category_options = strategy_category_options(profile)
    return {
        "stock": {"symbol": profile.symbol, "name": profile.name},
        "profile_summary": {
            "data_period": data_period,
            "available_categories": [o["label"] for o in category_options],
            "warnings": list(profile.data_quality_warnings),
        },
        "category_options": category_options,
        "recommended_questions": [
            {
                "question_id": q.question_id,
                "category": q.category,
                "text": q.text,
                "reason": q.reason,
                "advanced": q.advanced,
                "warning": q.warning,
                "suggested_search_range": q.suggested_search_range,
            }
            for q in selection.recommended
        ],
        "excluded_questions": [
            {"question_id": q.question_id, "reason": q.reason}
            for q in selection.excluded
        ],
    }
