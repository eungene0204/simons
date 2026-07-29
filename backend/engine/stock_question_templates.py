"""단일 종목 질문 템플릿 — 프로파일 기반 동적 필터링 (FR-STR-068b).

각 질문 템플릿은 필요한 데이터 피처·전략 카테고리·최소 신호 횟수를 선언하고,
select_stock_questions()가 StockResearchProfile을 근거로 노출/제외/경고를 결정한다.

원칙:
  - 단일 종목 기본 질문에는 횡단면(종목 선별) 조건을 넣지 않는다 — "언제 사고 언제 팔까"만.
  - 재무 지표(PBR·PER·배당수익률)는 advanced=True(고급 — 그 종목의 당시 값 시계열 신호)로만
    제공하며, PIT 안전성이 확인된 경우에만 노출한다.
  - 데이터가 없는 템플릿은 조용히 숨기지 않고 excluded에 이유와 함께 담는다.
  - 신호가 희소하면 경고를 붙여 노출하고, 과다하면 거래비용 경고를 붙인다.
  - 수익률 기준 최적값(best_value)은 어디에도 없다 — 탐색 범위만 제안한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .stock_profile import StockResearchProfile

# 신호 통계 기준 희소/과다 판정 임계.
SPARSE_SIGNAL_MIN = 10          # 전체 기간 발생 횟수가 이보다 적으면 희소 경고
FREQUENT_SIGNAL_PER_YEAR = 30.0  # 연간 빈도가 이보다 크면 거래비용 경고


@dataclass(frozen=True)
class StockQuestionTemplate:
    question_id: str
    category: str                       # supported_strategy_categories 키
    text: str
    required_features: frozenset[str]
    # 프로파일 signal_statistics에서 이 템플릿의 발생 횟수를 읽을 키(없으면 빈도 검사 생략).
    signal_stat_key: Optional[str] = None
    minimum_signal_count: Optional[int] = None
    advanced: bool = False
    # 파라미터 탐색 범위 제안(해석 가능한 범위 — 사후 최적값 아님, best_value는 항상 None).
    suggested_search_range: Optional[Dict[str, Any]] = None


QUESTION_TEMPLATES: tuple[StockQuestionTemplate, ...] = (
    # ── 추세 추종 ──
    StockQuestionTemplate(
        question_id="ma_golden_cross",
        category="trend_following",
        text="단기 이동평균선이 장기 이동평균선을 상향 돌파(골든크로스)할 때 매수할까요?",
        required_features=frozenset({"ohlcv", "moving_average"}),
        signal_stat_key="golden_cross_5_20",
        minimum_signal_count=5,
        suggested_search_range={
            "indicator": "ma_periods", "candidates": [[5, 20], [10, 60], [20, 120]],
            "reason": "일반적으로 해석 가능한 단기/장기 조합에서 신호 수를 비교하기 위한 범위",
            "best_value": None,
        },
    ),
    StockQuestionTemplate(
        question_id="macd_cross",
        category="trend_following",
        text="MACD가 시그널선을 상향 돌파할 때 매수할까요?",
        required_features=frozenset({"ohlcv", "macd"}),
        signal_stat_key="macd_buy_cross",
        minimum_signal_count=5,
    ),
    StockQuestionTemplate(
        question_id="trend_ma_filter",
        category="trend_following",
        text="20일 이동평균선 위에 있을 때만 신규 진입하도록 제한할까요?",
        required_features=frozenset({"ohlcv", "moving_average"}),
    ),
    # ── 평균회귀 ──
    StockQuestionTemplate(
        question_id="rsi_oversold_entry",
        category="mean_reversion",
        text="RSI가 설정한 기준 이하로 내려가면 매수하는 과매도 반등 전략을 테스트할까요?",
        required_features=frozenset({"ohlcv", "rsi"}),
        signal_stat_key="rsi_below_30",
        minimum_signal_count=10,
        suggested_search_range={
            "indicator": "rsi_threshold", "min": 20, "max": 40, "step": 5,
            "reason": "해석 가능한 과매도 범위 내에서 신호 수를 비교하기 위한 탐색 범위",
            "best_value": None,
        },
    ),
    StockQuestionTemplate(
        question_id="bollinger_lower_entry",
        category="mean_reversion",
        text="볼린저밴드 하단에 닿으면 매수하고 상단에 닿으면 매도할까요?",
        required_features=frozenset({"ohlcv", "bollinger"}),
        signal_stat_key="bollinger_lower_touch",
        minimum_signal_count=10,
    ),
    StockQuestionTemplate(
        question_id="drop_rebound_entry",
        category="mean_reversion",
        text="최근 고점 대비 일정 비율 하락했을 때 매수하도록 설정할까요?",
        required_features=frozenset({"ohlcv"}),
        signal_stat_key="drop_10pct_from_60d_high",
        minimum_signal_count=5,
        suggested_search_range={
            "indicator": "drop_pct", "min": 5, "max": 20, "step": 5,
            "reason": "고점 대비 하락 폭 후보를 비교하기 위한 범위",
            "best_value": None,
        },
    ),
    # ── 돌파 ──
    StockQuestionTemplate(
        question_id="breakout_entry",
        category="breakout",
        text="일정 기간의 최고가(신고가)를 돌파할 때 매수할까요?",
        required_features=frozenset({"ohlcv", "breakout"}),
        signal_stat_key="breakout_60d",
        minimum_signal_count=5,
        suggested_search_range={
            "indicator": "breakout_lookback_days", "candidates": [20, 60, 120],
            "reason": "관용적인 신고가 기준 기간에서 신호 수를 비교하기 위한 범위",
            "best_value": None,
        },
    ),
    # ── 거래량 ──
    StockQuestionTemplate(
        question_id="volume_spike_entry",
        category="volume",
        text="거래량이 평소보다 크게 늘어난 날 매수 신호로 사용할까요?",
        required_features=frozenset({"ohlcv", "volume"}),
        signal_stat_key="volume_spike_3x",
        minimum_signal_count=10,
    ),
    # ── 고급: 단일 종목 시계열 밸류에이션(PIT) — 기본 노출 안 함 ──
    StockQuestionTemplate(
        question_id="historical_pbr_entry",
        category="valuation_timeseries",
        text="이 종목의 당시 PBR이 지정한 수준 이하일 때 매수할까요? (공시 반영 시점 기준)",
        required_features=frozenset({"pbr"}),
        minimum_signal_count=5,
        advanced=True,
    ),
    StockQuestionTemplate(
        question_id="historical_per_entry",
        category="valuation_timeseries",
        text="이 종목의 당시 PER이 지정한 수준 이하일 때 매수할까요? (공시 반영 시점 기준)",
        required_features=frozenset({"per"}),
        minimum_signal_count=5,
        advanced=True,
    ),
    StockQuestionTemplate(
        question_id="historical_dividend_yield_entry",
        category="dividend_yield_timeseries",
        text="이 종목의 당시 배당수익률이 지정한 수준 이상일 때 매수할까요? (공시 반영 시점 기준)",
        required_features=frozenset({"dividend_yield"}),
        minimum_signal_count=5,
        advanced=True,
    ),
    # ── 데이터가 파이프라인에 없어 항상 제외되는 템플릿(이유 노출용) ──
    StockQuestionTemplate(
        question_id="market_regime_filter",
        category="market_filter",
        text="시장지수가 상승 추세일 때만 매수하도록 필터를 추가할까요?",
        required_features=frozenset({"market_index"}),
    ),
    StockQuestionTemplate(
        question_id="foreign_flow_entry",
        category="flow",
        text="외국인 순매수가 이어질 때 매수할까요?",
        required_features=frozenset({"foreign_flow"}),
    ),
    StockQuestionTemplate(
        question_id="short_interest_entry",
        category="flow",
        text="공매도 잔고 변화를 진입 조건으로 사용할까요?",
        required_features=frozenset({"short_interest"}),
    ),
    StockQuestionTemplate(
        question_id="earnings_event_entry",
        category="event",
        text="실적 발표 전후 구간을 진입 조건으로 사용할까요?",
        required_features=frozenset({"earnings_events"}),
    ),
)

# 미지원 피처 → 사용자 안내 문구.
_FEATURE_LABELS: Dict[str, str] = {
    "market_index": "시장지수 시계열 데이터",
    "sector_index": "업종지수 시계열 데이터",
    "foreign_flow": "외국인 수급 데이터",
    "institution_flow": "기관 수급 데이터",
    "short_interest": "공매도 데이터",
    "earnings_events": "실적 발표일 데이터",
    "dividend_events": "배당 발표일 데이터",
    "news_events": "뉴스 이벤트 데이터",
    "disclosure_events": "공시 이벤트 데이터",
    "pbr": "PBR(공시 반영) 데이터",
    "per": "PER(공시 반영) 데이터",
    "dividend_yield": "배당수익률(공시 반영) 데이터",
}

_CATEGORY_LABELS: Dict[str, str] = {
    "trend_following": "추세 추종",
    "mean_reversion": "과매도 후 반등",
    "breakout": "돌파",
    "volume": "거래량",
    "valuation_timeseries": "당시 밸류에이션 기준(고급)",
    "dividend_yield_timeseries": "당시 배당수익률 기준(고급)",
}


@dataclass(frozen=True)
class SelectedQuestion:
    question_id: str
    category: str
    text: str
    reason: str                      # 데이터 근거(수익 보장·우월 표현 금지)
    advanced: bool = False
    warning: Optional[str] = None    # 희소/과다 신호 경고
    suggested_search_range: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ExcludedQuestion:
    question_id: str
    reason: str


@dataclass(frozen=True)
class QuestionSelection:
    recommended: tuple[SelectedQuestion, ...]
    excluded: tuple[ExcludedQuestion, ...]


def _signal_count(profile: StockResearchProfile, key: Optional[str]) -> Optional[int]:
    if not key:
        return None
    v = profile.signal_statistics.get(f"{key}_count")
    return int(v) if isinstance(v, (int, float)) else None


def _signal_per_year(profile: StockResearchProfile, key: Optional[str]) -> Optional[float]:
    if not key:
        return None
    v = profile.signal_statistics.get(f"{key}_per_year")
    return float(v) if isinstance(v, (int, float)) else None


def _availability_reason(profile: StockResearchProfile, template: StockQuestionTemplate) -> str:
    count = _signal_count(profile, template.signal_stat_key)
    if count is not None:
        return f"과거 데이터에서 관련 신호가 {count}회 발생했습니다."
    if template.advanced:
        cov = profile.data_coverage.get(next(iter(template.required_features)))
        if cov and cov.start_date:
            return f"공시 반영(Point-in-Time) 데이터가 {cov.start_date}부터 존재합니다."
    return "필요한 데이터가 백테스트 기간에 존재합니다."


def select_stock_questions(
    profile: StockResearchProfile, *, include_advanced: bool = False,
) -> QuestionSelection:
    """프로파일을 근거로 노출할 질문과 제외 사유를 결정한다.

    include_advanced=False(기본)에서는 advanced 템플릿(재무 시계열)을 recommended에 넣지
    않는다 — 사용자가 명시적으로 요청하거나 고급 모드를 선택했을 때만 노출한다.
    제외 시에도 조용히 숨기지 않고 excluded에 이유를 담는다.
    """
    recommended: list[SelectedQuestion] = []
    excluded: list[ExcludedQuestion] = []

    for template in QUESTION_TEMPLATES:
        # 파이프라인 미지원/종목 미보유 피처가 하나라도 빠지면 제외 + 이유.
        missing = template.required_features - profile.supported_features
        if missing:
            labels = [_FEATURE_LABELS.get(f, f) for f in sorted(missing)]
            excluded.append(ExcludedQuestion(
                question_id=template.question_id,
                reason=f"{'·'.join(labels)}가 제공되지 않습니다.",
            ))
            continue
        if template.advanced and not include_advanced:
            excluded.append(ExcludedQuestion(
                question_id=template.question_id,
                reason="여러 종목을 비교·선별하는 조건이 아닌, 이 종목의 당시 값 기준 고급 조건으로만 제공됩니다. 명시적으로 요청하면 사용할 수 있습니다.",
            ))
            continue

        warning: Optional[str] = None
        count = _signal_count(profile, template.signal_stat_key)
        per_year = _signal_per_year(profile, template.signal_stat_key)
        min_count = template.minimum_signal_count
        if count is not None and min_count is not None and count < min_count:
            warning = (
                f"이 조건은 해당 종목의 과거 데이터에서 {count}회만 발생했습니다. "
                "통계적으로 신뢰할 수 있는 결과를 얻기 어려울 수 있습니다. "
                "기준을 완화하거나 기간을 늘리는 것을 고려해 주세요."
            )
        elif per_year is not None and per_year > FREQUENT_SIGNAL_PER_YEAR:
            warning = (
                f"이 조건은 연평균 약 {per_year:.0f}회로 매우 자주 발생합니다. "
                "거래비용과 슬리피지의 영향을 크게 받을 수 있으니 조건을 "
                "좁히는 것을 고려해 주세요."
            )

        recommended.append(SelectedQuestion(
            question_id=template.question_id,
            category=template.category,
            text=template.text,
            reason=_availability_reason(profile, template),
            advanced=template.advanced,
            warning=warning,
            suggested_search_range=template.suggested_search_range,
        ))

    return QuestionSelection(recommended=tuple(recommended), excluded=tuple(excluded))


def strategy_category_options(profile: StockResearchProfile) -> List[Dict[str, str]]:
    """첫 화면용 전략 유형 옵션(3~5개). reason은 데이터 근거만 — 우열·수익 표현 금지."""
    options: List[Dict[str, str]] = []

    def count(key: str) -> Optional[int]:
        return _signal_count(profile, key)

    if "trend_following" in profile.supported_strategy_categories:
        gc = count("golden_cross_5_20")
        options.append({
            "id": "trend_following", "label": _CATEGORY_LABELS["trend_following"],
            "reason": (
                f"이동평균 교차 신호가 과거 데이터에서 {gc}회 발생했습니다."
                if gc is not None else "이동평균과 가격 추세 데이터를 사용할 수 있습니다."
            ),
        })
    if "mean_reversion" in profile.supported_strategy_categories:
        rsi = count("rsi_below_30")
        options.append({
            "id": "mean_reversion", "label": _CATEGORY_LABELS["mean_reversion"],
            "reason": (
                f"RSI 30 이하 진입 신호가 과거 데이터에서 {rsi}회 발생했습니다."
                if rsi is not None else "RSI·볼린저밴드 신호 데이터를 사용할 수 있습니다."
            ),
        })
    if "breakout" in profile.supported_strategy_categories:
        brk = count("breakout_60d")
        options.append({
            "id": "breakout", "label": _CATEGORY_LABELS["breakout"],
            "reason": (
                f"60일 신고가 돌파가 과거 데이터에서 {brk}회 발생했습니다."
                if brk is not None else "가격·신고가 데이터를 사용할 수 있습니다."
            ),
        })
    if "volume" in profile.supported_strategy_categories:
        vs = count("volume_spike_3x")
        options.append({
            "id": "volume", "label": _CATEGORY_LABELS["volume"],
            "reason": (
                f"거래량 급증이 과거 데이터에서 {vs}회 발생했습니다."
                if vs is not None else "거래량 데이터를 사용할 수 있습니다."
            ),
        })
    return options[:5]
