"""IndicatorRegistry — 지표 지원 여부의 단일 진실 소스(시스템 계약).

LLM에게 금융 용어를 가르치는 사전이 아니다. LLM은 지표명을 자유롭게 추출하고,
실제 지원 여부·canonical ID·허용 연산자·파라미터 범위는 이 Registry가 최종
판정한다. 항목은 백테스트 엔진의 실지원(FundamentalFilter.metric,
TechnicalSignal.indicator Literal)과 1:1로 유지해야 한다 — 엔진에 지표를
추가/제거하면 여기도 함께 갱신할 것.

지원 상태 3단계:
  SUPPORTED           — 엔진 연결 + 전체 기간 데이터
  PARTIALLY_SUPPORTED — 엔진 연결 + 일부 종목/기간 데이터(실측 커버리지는
                        engine/data_coverage.py 런타임 로그가 정본)
  UNSUPPORTED         — LLM이 개념은 이해하지만 엔진/데이터 파이프라인 미지원
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

SupportStatus = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED"]

_COMPARISON_OPS = ("<", "<=", ">", ">=")


@dataclass(frozen=True)
class ParamSpec:
    default: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    required: bool = False


@dataclass(frozen=True)
class IndicatorSpec:
    id: str                         # canonical ID (예: fundamental.per)
    display_name: str
    category: str                   # valuation/profitability/stability/growth/technical/...
    supported: SupportStatus
    data_source: str                # financial_statements / ohlcv / ai_model / none
    value_type: Optional[str] = None  # percent / ratio / 억원 / point / event
    allowed_operators: Tuple[str, ...] = ()
    parameters: Dict[str, ParamSpec] = field(default_factory=dict)
    value_range: Optional[Tuple[float, float]] = None  # 임계값(value) 유효 범위
    recommended_value: Optional[float] = None          # 되묻기 시 제시할 시작값
    engine_binding: Optional[Tuple[str, str]] = None   # (종류, 엔진 필드값)
    available_from: Optional[str] = None               # 데이터 시작일(알려진 경우)
    partial_data: bool = False                         # 종목/기간별 커버리지 편차 존재
    alternatives: Tuple[str, ...] = ()                 # UNSUPPORTED 시 제안 가능한 대체 지표
    notes: Optional[str] = None


def _fundamental(
    metric: str, name: str, category: str, value_type: str,
    recommended: Optional[float] = None, value_range: Optional[Tuple[float, float]] = None,
    notes: Optional[str] = None,
) -> IndicatorSpec:
    # 재무 데이터는 KIS 백필 기반으로 종목·기간별 커버리지 편차가 있다 —
    # 정확한 결측은 데이터 커버리지 로그(FR-BT-016)가 실측으로 알린다.
    return IndicatorSpec(
        id=f"fundamental.{metric}",
        display_name=name,
        category=category,
        supported="PARTIALLY_SUPPORTED",
        data_source="financial_statements",
        value_type=value_type,
        allowed_operators=_COMPARISON_OPS,
        value_range=value_range,
        recommended_value=recommended,
        engine_binding=("fundamental_filter", metric),
        partial_data=True,
        notes=notes,
    )


def _technical(
    indicator: str, name: str, value_type: Optional[str],
    operators: Tuple[str, ...], params: Dict[str, ParamSpec],
    value_range: Optional[Tuple[float, float]] = None,
    recommended: Optional[float] = None, notes: Optional[str] = None,
) -> IndicatorSpec:
    return IndicatorSpec(
        id=f"technical.{indicator}",
        display_name=name,
        category="technical",
        supported="SUPPORTED",
        data_source="ohlcv",
        value_type=value_type,
        allowed_operators=operators,
        parameters=params,
        value_range=value_range,
        recommended_value=recommended,
        engine_binding=("technical_signal", indicator),
        notes=notes,
    )


def _unsupported(
    key: str, name: str, category: str,
    alternatives: Tuple[str, ...] = (), notes: Optional[str] = None,
) -> IndicatorSpec:
    return IndicatorSpec(
        id=f"unsupported.{key}",
        display_name=name,
        category=category,
        supported="UNSUPPORTED",
        data_source="none",
        alternatives=alternatives,
        notes=notes,
    )


_SPECS: Tuple[IndicatorSpec, ...] = (
    # ── 재무 지표 (엔진 FundamentalFilter.metric과 1:1) ──────────────────────
    _fundamental("per", "PER(주가수익비율)", "valuation", "ratio", recommended=10, value_range=(0, 1000)),
    _fundamental("pbr", "PBR(주가순자산비율)", "valuation", "ratio", recommended=1, value_range=(0, 100)),
    _fundamental("psr", "PSR(주가매출비율)", "valuation", "ratio", recommended=1, value_range=(0, 100)),
    _fundamental("ev_ebitda", "EV/EBITDA", "valuation", "ratio", recommended=8, value_range=(0, 500)),
    _fundamental("roe_or_gpa", "ROE(자기자본이익률)", "profitability", "percent", recommended=15, value_range=(-100, 200)),
    _fundamental("roa", "ROA(총자본순이익률)", "profitability", "percent", recommended=5, value_range=(-100, 100)),
    _fundamental("debt_ratio", "부채비율", "stability", "percent", recommended=100, value_range=(0, 10000)),
    _fundamental("current_ratio", "유동비율", "stability", "percent", recommended=150, value_range=(0, 10000)),
    _fundamental("quick_ratio", "당좌비율", "stability", "percent", recommended=100, value_range=(0, 10000)),
    _fundamental("reserve_ratio", "유보율", "stability", "percent", recommended=500, value_range=(0, 100000)),
    _fundamental("net_margin", "순이익률", "profitability", "percent", recommended=5, value_range=(-100, 100)),
    _fundamental("gross_margin", "매출총이익률", "profitability", "percent", recommended=20, value_range=(-100, 100)),
    _fundamental("operating_margin", "영업이익률", "profitability", "percent", recommended=10, value_range=(-100, 100)),
    _fundamental("revenue_growth", "매출액증가율", "growth", "percent", recommended=10, value_range=(-100, 1000)),
    _fundamental("operating_income_growth", "영업이익증가율", "growth", "percent", recommended=10, value_range=(-1000, 1000)),
    _fundamental("net_income_growth", "순이익증가율", "growth", "percent", recommended=10, value_range=(-1000, 1000)),
    _fundamental("market_cap", "시가총액", "size", "억원", recommended=5000, value_range=(0, 10_000_000)),
    _fundamental("trading_value", "일평균거래대금", "liquidity", "억원", recommended=10, value_range=(0, 1_000_000)),
    _fundamental("dividend_yield", "배당수익률", "dividend", "percent", recommended=3, value_range=(0, 100)),
    _fundamental("payout_rate", "배당성향", "dividend", "percent", recommended=30, value_range=(0, 1000)),
    _fundamental("dividend_growth", "배당성장률", "dividend", "percent", recommended=5, value_range=(-100, 1000)),

    # ── 기술적 지표 (엔진 TechnicalSignal.indicator와 1:1) ───────────────────
    _technical("ma_crossover", "이동평균 크로스오버", "event",
               ("crosses_above", "crosses_below"),
               {"short_period": ParamSpec(default=20, minimum=2, maximum=250, required=True),
                "long_period": ParamSpec(default=60, minimum=3, maximum=500, required=True)},
               notes="crosses_above=골든크로스, crosses_below=데드크로스"),
    _technical("ema", "지수이동평균(EMA)", "event",
               ("crosses_above", "crosses_below", ">", "<"),
               {"short_period": ParamSpec(default=20, minimum=2, maximum=250),
                "long_period": ParamSpec(default=60, minimum=3, maximum=500)},
               notes=">/'<'는 가격 vs EMA 지속 상태 추세 필터(mode above/below)"),
    _technical("rsi", "RSI", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(0, 100), recommended=30),
    _technical("macd", "MACD", "event",
               ("crosses_above", "crosses_below"),
               {},
               notes="엔진은 fast/slow/signal 기간 커스텀을 지원하지 않음(12/26/9 고정). "
                     "crosses_above/below=시그널선 교차"),
    _technical("bollinger_bands", "볼린저 밴드", "event",
               ("crosses_above", "crosses_below"),
               {"period": ParamSpec(default=20, minimum=5, maximum=250)}),
    _technical("breakout", "신고가 돌파", "event", ("crosses_above",),
               {"lookback_period": ParamSpec(default=60, minimum=5, maximum=500, required=True)}),
    _technical("volume_spike", "거래량 급증(OBV)", "event", ("crosses_above",),
               {"period": ParamSpec(default=20, minimum=2, maximum=250)},
               notes="OBV 크로스오버 기반 — '평소 대비 N배' 배수 임계값은 표현 불가"),
    _technical("stochastic", "스토캐스틱", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(0, 100), recommended=20),
    _technical("cci", "CCI", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=20, minimum=2, maximum=250)},
               value_range=(-500, 500), recommended=-100),
    _technical("adx", "ADX", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(0, 100), recommended=25),
    _technical("williams_r", "Williams %R", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(-100, 0), recommended=-80),
    _technical("mfi", "MFI(자금흐름지표)", "point", _COMPARISON_OPS,
               {"period": ParamSpec(default=14, minimum=2, maximum=250)},
               value_range=(0, 100), recommended=20),
    _technical("roc", "ROC(변화율/모멘텀)", "percent", _COMPARISON_OPS,
               {"period": ParamSpec(default=20, minimum=2, maximum=250)},
               value_range=(-100, 1000), recommended=0),
    _technical("trading_value", "거래대금 신호", "억원", _COMPARISON_OPS, {},
               value_range=(0, 1_000_000)),
    IndicatorSpec(
        id="technical.ai_model", display_name="AI 상승 예측", category="ai",
        supported="SUPPORTED", data_source="ai_model", value_type="percent",
        allowed_operators=(">", ">="),
        parameters={"threshold": ParamSpec(default=70, minimum=50, maximum=100)},
        value_range=(0, 100), engine_binding=("technical_signal", "ai_model"),
        notes="진입 신호 단독 사용은 성과가 검증되지 않음(보조 용도)"),
    IndicatorSpec(
        id="technical.ai_drop_model", display_name="AI 하락 예측 청산", category="ai",
        supported="SUPPORTED", data_source="ai_model", value_type="percent",
        allowed_operators=(">", ">="),
        parameters={"threshold": ParamSpec(default=70, minimum=50, maximum=100)},
        value_range=(0, 100), engine_binding=("technical_signal", "ai_drop_model")),

    # ── 랭킹 지표 ─────────────────────────────────────────────────────────────
    IndicatorSpec(
        id="ranking.return", display_name="기간 수익률 랭킹(모멘텀)", category="ranking",
        supported="SUPPORTED", data_source="ohlcv", value_type="percent",
        parameters={"lookback_days": ParamSpec(default=60, minimum=5, maximum=500)},
        engine_binding=("ranking", "return")),

    # ── 개념은 이해하지만 엔진/데이터 미지원 (조용한 대체 금지 — 명시 제안만) ──
    _unsupported("fcf_yield", "FCF Yield(잉여현금흐름 수익률)", "valuation",
                 alternatives=("fundamental.per", "fundamental.operating_margin"),
                 notes="현금흐름 데이터 파이프라인 없음"),
    _unsupported("cash_flow", "현금흐름(FCF/PCF) 조건", "valuation",
                 alternatives=("fundamental.operating_margin",)),
    _unsupported("volatility", "변동성 조건", "risk"),
    _unsupported("roic", "ROIC(투하자본이익률)", "profitability",
                 alternatives=("fundamental.roe_or_gpa", "fundamental.roa")),
    _unsupported("beta", "베타(시장 민감도)", "risk"),
    _unsupported("interest_coverage", "이자보상배율", "stability",
                 alternatives=("fundamental.debt_ratio", "fundamental.current_ratio")),
    _unsupported("quality_score", "피오트로스키/알트만 점수", "quality"),
    _unsupported("turnover_ratio", "회전율(재고·매출채권)", "efficiency"),
    _unsupported("buyback", "자사주 매입", "event"),
    _unsupported("news", "뉴스/공시/재료 조건", "event"),
    _unsupported("supply_demand", "수급(외국인·기관·공매도)", "flow"),
    _unsupported("profitability_sign", "흑자/적자 여부", "profitability",
                 alternatives=("fundamental.net_margin", "fundamental.operating_margin")),
    _unsupported("ema_alignment", "정배열/역배열", "technical"),
    _unsupported("partial_exit", "분할 매도/부분 청산", "execution"),
    _unsupported("new_low", "신저가 조건", "technical"),
    _unsupported("volume_multiple", "거래량 배수(평소 대비 N배)", "technical",
                 alternatives=("technical.volume_spike",)),
    _unsupported("earnings_estimate", "실적 컨센서스/추정치", "fundamental"),
    _unsupported("moat", "경제적 해자 등 정성 평가", "quality"),
)

REGISTRY: Dict[str, IndicatorSpec] = {spec.id: spec for spec in _SPECS}

# ── 이름 해석(alias → canonical ID) ─────────────────────────────────────────
# LLM이 추출한 지표명을 canonical ID로 매핑한다. 여기의 alias는 '동의어 사전'이
# 아니라 canonical 표기 변형(영문/한글 공식 명칭)만 담는다 — 구어체 긴 꼬리
# ("이익에 비해 싼")의 해석은 LLM의 몫이고, LLM은 아래 canonical 이름 중 하나로
# 출력하도록 프롬프트로 계약한다.
_ALIASES: Dict[str, str] = {
    "per": "fundamental.per", "주가수익비율": "fundamental.per",
    "pbr": "fundamental.pbr", "주가순자산비율": "fundamental.pbr",
    "psr": "fundamental.psr", "주가매출비율": "fundamental.psr",
    "ev/ebitda": "fundamental.ev_ebitda", "ev_ebitda": "fundamental.ev_ebitda",
    "roe": "fundamental.roe_or_gpa", "자기자본이익률": "fundamental.roe_or_gpa",
    "roa": "fundamental.roa", "총자본순이익률": "fundamental.roa", "총자산이익률": "fundamental.roa",
    "부채비율": "fundamental.debt_ratio", "debt_ratio": "fundamental.debt_ratio",
    "유동비율": "fundamental.current_ratio", "current_ratio": "fundamental.current_ratio",
    "당좌비율": "fundamental.quick_ratio", "quick_ratio": "fundamental.quick_ratio",
    "유보율": "fundamental.reserve_ratio", "reserve_ratio": "fundamental.reserve_ratio",
    "순이익률": "fundamental.net_margin", "net_margin": "fundamental.net_margin",
    "매출총이익률": "fundamental.gross_margin", "gross_margin": "fundamental.gross_margin",
    "영업이익률": "fundamental.operating_margin", "operating_margin": "fundamental.operating_margin",
    "매출액증가율": "fundamental.revenue_growth", "매출증가율": "fundamental.revenue_growth",
    "revenue_growth": "fundamental.revenue_growth",
    "영업이익증가율": "fundamental.operating_income_growth",
    "operating_income_growth": "fundamental.operating_income_growth",
    "순이익증가율": "fundamental.net_income_growth", "net_income_growth": "fundamental.net_income_growth",
    "시가총액": "fundamental.market_cap", "market_cap": "fundamental.market_cap",
    "거래대금": "fundamental.trading_value", "trading_value": "fundamental.trading_value",
    "배당수익률": "fundamental.dividend_yield", "dividend_yield": "fundamental.dividend_yield",
    "배당성향": "fundamental.payout_rate", "payout_rate": "fundamental.payout_rate",
    "배당성장률": "fundamental.dividend_growth", "dividend_growth": "fundamental.dividend_growth",
    "ma_crossover": "technical.ma_crossover", "이동평균크로스오버": "technical.ma_crossover",
    "골든크로스": "technical.ma_crossover", "데드크로스": "technical.ma_crossover",
    "이동평균": "technical.ma_crossover",
    "ema": "technical.ema", "지수이동평균": "technical.ema",
    "rsi": "technical.rsi",
    "macd": "technical.macd",
    "볼린저밴드": "technical.bollinger_bands", "bollinger": "technical.bollinger_bands",
    "bollinger_bands": "technical.bollinger_bands", "볼린저": "technical.bollinger_bands",
    "breakout": "technical.breakout", "신고가돌파": "technical.breakout", "신고가": "technical.breakout",
    "volume_spike": "technical.volume_spike", "거래량급증": "technical.volume_spike",
    "스토캐스틱": "technical.stochastic", "stochastic": "technical.stochastic",
    "cci": "technical.cci",
    "adx": "technical.adx",
    "williams_r": "technical.williams_r", "williams%r": "technical.williams_r",
    "윌리엄스": "technical.williams_r",
    "mfi": "technical.mfi", "자금흐름지표": "technical.mfi",
    "roc": "technical.roc", "모멘텀": "technical.roc",
    "ai_model": "technical.ai_model", "ai상승예측": "technical.ai_model",
    "ai_drop_model": "technical.ai_drop_model", "ai하락예측": "technical.ai_drop_model",
    "return": "ranking.return", "수익률랭킹": "ranking.return", "기간수익률": "ranking.return",
    # 미지원 개념의 canonical 표기(LLM이 이 이름으로 출력하면 UNSUPPORTED로 판정된다)
    "fcf": "unsupported.fcf_yield", "fcf_yield": "unsupported.fcf_yield",
    "잉여현금흐름": "unsupported.fcf_yield",
    "현금흐름": "unsupported.cash_flow", "pcf": "unsupported.cash_flow",
    "변동성": "unsupported.volatility", "volatility": "unsupported.volatility",
    "roic": "unsupported.roic", "투하자본이익률": "unsupported.roic",
    "베타": "unsupported.beta", "beta": "unsupported.beta",
    "이자보상배율": "unsupported.interest_coverage",
    "피오트로스키": "unsupported.quality_score", "f-score": "unsupported.quality_score",
    "회전율": "unsupported.turnover_ratio",
    "자사주매입": "unsupported.buyback", "자사주": "unsupported.buyback",
    "뉴스": "unsupported.news", "공시": "unsupported.news",
    "수급": "unsupported.supply_demand", "외국인순매수": "unsupported.supply_demand",
    "흑자": "unsupported.profitability_sign", "적자": "unsupported.profitability_sign",
    "정배열": "unsupported.ema_alignment", "역배열": "unsupported.ema_alignment",
    "분할매도": "unsupported.partial_exit",
    "신저가": "unsupported.new_low",
    "경제적해자": "unsupported.moat",
}


def resolve(name: str) -> Optional[IndicatorSpec]:
    """지표명(canonical ID/공식 명칭)을 IndicatorSpec으로 해석한다. 미지 시 None."""
    if not name:
        return None
    key = name.strip()
    if key in REGISTRY:
        return REGISTRY[key]
    normalized = key.replace(" ", "").lower()
    canonical = _ALIASES.get(normalized)
    if canonical:
        return REGISTRY[canonical]
    return None


def supported_factor_lines() -> List[str]:
    """LLM 프롬프트에 주입할 지원 지표 목록(한 줄 요약)."""
    lines = []
    for spec in _SPECS:
        if spec.supported == "UNSUPPORTED":
            continue
        ops = "/".join(spec.allowed_operators) if spec.allowed_operators else "-"
        unit = spec.value_type or "-"
        lines.append(f"- {spec.id} ({spec.display_name}) 단위={unit} 연산자={ops}")
    return lines
