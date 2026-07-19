"""StrategyIntent 중간 표현 — LLM 출력과 백테스트 DSL 사이의 계약.

LLM(Qwen 3.5 4B)은 이 스키마의 JSON만 출력한다. LLM이 직접 백테스트 DSL
(ParsedStrategy)을 생성하지 않으며, 검증 계층을 통과한 StrategyIntent만
compiler가 ParsedStrategy로 변환한다.

4B 모델의 흔한 스키마 드리프트(숫자를 문자열로, 단일 값을 배열로, "10%" 같은
단위 붙은 값)는 ValidationError로 통째로 버리지 않고 field validator에서
복구한다 — 이는 자연어 해석이 아니라 형식 정규화이므로 결정론 코드의 영역이다.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# ─── Enum 계약 ────────────────────────────────────────────────────────────────

IntentType = Literal[
    "CREATE_STRATEGY",
    "MODIFY_STRATEGY",
    "EXPLAIN_INDICATOR",
    "RUN_BACKTEST",
    "COMPARE_STRATEGIES",
    "CLARIFY_STRATEGY",
    "CONFIRM_RECOMMENDATION",
    "CANCEL_OPERATION",
    "UNSUPPORTED_REQUEST",
    "NON_STRATEGY_REQUEST",
]

IntentStatus = Literal["READY", "NEEDS_CLARIFICATION", "UNSUPPORTED", "REJECTED"]

# 값의 출처 — 추천값과 확정값을 분리한다. SYSTEM_RECOMMENDED는 사용자 확인 전까지
# 확정값으로 쓰지 않는다(무단 확정 금지).
ValueSource = Literal[
    "USER_PROVIDED",
    "USER_CONFIRMED",
    "SYSTEM_RECOMMENDED",
    "SYSTEM_DEFAULT",
    "INFERRED",
    "MISSING",
]

ConditionRole = Literal["entry", "exit"]

_NUMBER_RE = re.compile(r"^-?\d+(?:[.,]\d+)?")


def _coerce_number(v: Any) -> Any:
    """"10%", "12배", "1,000" 같은 문자열 수치를 float로 정규화한다(형식 정규화).

    숫자로 시작하지 않는 문자열은 그대로 반환해 pydantic이 ValidationError를 내게
    둔다 — 의미를 추측해 조용히 값을 만들지 않는다.
    """
    if isinstance(v, str):
        m = _NUMBER_RE.match(v.replace(",", "").strip())
        if m:
            return float(m.group(0))
    return v


# ─── 조건 표현 ────────────────────────────────────────────────────────────────

class StrategyCondition(BaseModel):
    """단일 진입/청산 조건. factor는 LLM이 추출한 지표명(자유 문자열)이며,
    실제 지원 여부·canonical ID 매핑은 IndicatorRegistry가 최종 판정한다."""

    factor: str = Field(description="지표명 (예: 'PER', 'ROE', 'RSI', '골든크로스')")
    operator: Optional[str] = Field(
        default=None,
        description="비교/이벤트 연산자: <, <=, >, >=, crosses_above, crosses_below",
    )
    value: Optional[float] = Field(default=None, description="임계값. 사용자가 말하지 않았으면 null")
    unit: Optional[str] = Field(default=None, description="값 단위: percent, ratio, 억원, point")
    parameters: Dict[str, Optional[float]] = Field(
        default_factory=dict,
        description="지표 파라미터 (예: period, short_period, long_period, lookback_period, threshold)",
    )
    recommended_value: Optional[float] = Field(
        default=None, description="시스템 추천값(확정 아님). 사용자 확인 필요"
    )
    requires_confirmation: bool = Field(
        default=False, description="추천값이 있고 사용자 확인이 필요한지"
    )
    value_source: ValueSource = Field(
        default="USER_PROVIDED", description="값의 출처. 값이 없으면 MISSING"
    )
    source_text: Optional[str] = Field(
        default=None, description="이 조건을 추출한 사용자 원문 표현(디버깅·추적용)"
    )

    _coerce_value = field_validator("value", "recommended_value", mode="before")(_coerce_number)

    @field_validator("parameters", mode="before")
    @classmethod
    def _coerce_parameters(cls, v):
        if isinstance(v, dict):
            return {k: _coerce_number(val) for k, val in v.items()}
        return v

    @model_validator(mode="after")
    def _mark_missing_value(self):
        if self.value is None and self.value_source == "USER_PROVIDED":
            self.value_source = "MISSING"
        return self


class RankingSpec(BaseModel):
    """횡단면 랭킹 선정 (예: 최근 수익률 상위 N종목 = 모멘텀)."""

    metric: str = Field(description="랭킹 기준 (예: 'return')")
    lookback_days: Optional[int] = Field(default=None, description="산정 기간(거래일)")
    direction: Literal["top", "bottom"] = Field(default="top")
    source_text: Optional[str] = None


class UniverseSpec(BaseModel):
    markets: List[Literal["KOSPI", "KOSDAQ", "KOSPI200", "ETF"]] = Field(
        default_factory=lambda: ["KOSPI200"],
        description=(
            "투자 대상 시장. 언급 없으면 ['KOSPI200']. "
            "ETF/ETN/상장지수펀드 상품 대상이면 ['ETF'] 단독(주식 시장과 혼합 금지)"
        ),
    )
    sectors: List[str] = Field(
        default_factory=list, description="업종/섹터 제한. 언급 없으면 빈 배열"
    )
    etf_theme: Optional[str] = Field(
        default=None,
        description=(
            "ETF 전용 테마/상품명 키워드. markets=['ETF']이고 '반도체 ETF'·'미국 ETF'·"
            "'KODEX 200' 등 테마/상품명이 언급되면 그 키워드('반도체', '미국', 'KODEX 200'). "
            "엔진이 ETF 상품명과 매칭해 유니버스를 좁힌다. 언급 없으면 null"
        ),
    )

    @field_validator("etf_theme", mode="before")
    @classmethod
    def _coerce_etf_theme(cls, v):
        if isinstance(v, list):
            v = v[0] if v else None
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("markets", mode="before")
    @classmethod
    def _coerce_markets(cls, v):
        # 문자열 단일 값·한글 시장명 드리프트 정규화 (nl_parser 스키마 드리프트 복구와 동형)
        if isinstance(v, str):
            v = [v]
        if isinstance(v, list):
            market_map = {
                "KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ", "KOSPI200": "KOSPI200",
                "코스피": "KOSPI", "코스닥": "KOSDAQ", "코스피200": "KOSPI200",
                "ETF": "ETF", "ETN": "ETF", "이티에프": "ETF", "상장지수펀드": "ETF",
                "KOSPI_KOSDAQ": None,  # 아래에서 양시장으로 전개
            }
            out: list[str] = []
            for item in v:
                if not isinstance(item, str):
                    continue
                key = item.replace(" ", "").upper() if item.isascii() else item.replace(" ", "")
                if key == "KOSPI_KOSDAQ":
                    out.extend(m for m in ("KOSPI", "KOSDAQ") if m not in out)
                    continue
                token = market_map.get(key)
                if token and token not in out:
                    out.append(token)
            if "ETF" in out:
                return ["ETF"]  # ETF는 주식 시장과 혼합하지 않는 독립 유니버스
            if out:
                return out
        return v

    @field_validator("sectors", mode="before")
    @classmethod
    def _coerce_sectors(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


class PortfolioSpec(BaseModel):
    selection_count: Optional[int] = Field(default=None, description="선택 종목 수. 언급 없으면 null")
    weighting: Optional[str] = Field(default=None, description="비중 방식 (예: 'equal'). 언급 없으면 null")
    rebalance_frequency: Optional[str] = Field(
        default=None,
        description="리밸런싱 주기: daily/weekly/monthly/bimonthly/quarterly/yearly. 언급 없으면 null",
    )
    hold_period_days: Optional[int] = Field(default=None, description="최대 보유 기간(거래일)")

    _coerce_count = field_validator("selection_count", "hold_period_days", mode="before")(_coerce_number)


class RiskSpec(BaseModel):
    stop_loss: Optional[float] = Field(default=None, description="손절 비율(%). 크기만(부호 무시)")
    take_profit: Optional[float] = Field(default=None, description="익절 비율(%)")
    trailing_stop: Optional[float] = Field(default=None, description="트레일링 스탑 비율(%)")
    max_mdd_limit: Optional[float] = Field(default=None, description="포트폴리오 MDD 한도(%)")
    max_position_weight: Optional[float] = Field(default=None, description="종목당 최대 비중(%)")

    _coerce = field_validator(
        "stop_loss", "take_profit", "trailing_stop", "max_mdd_limit", "max_position_weight",
        mode="before",
    )(_coerce_number)

    @field_validator("stop_loss", "take_profit", "trailing_stop", "max_mdd_limit")
    @classmethod
    def _abs_ratio(cls, v):
        # 방향이 필드 의미에 내장돼 있어 크기만 유효 ("-8% 손절" → 8.0)
        return abs(v) if v is not None else None


class BacktestSpec(BaseModel):
    period: Optional[Literal["1y", "3y", "5y", "full"]] = Field(default=None)

    @field_validator("period", mode="before")
    @classmethod
    def _coerce_period(cls, v):
        # 4B 드리프트 실측(2026-07-16): "10년간" → period=1080(일수) 숫자 출력 —
        # 일수를 가장 가까운 지원 버킷으로 결정적 매핑(달력일 기준).
        # 정상 버킷 문자열("3y")을 숫자로 오인하지 않도록 먼저 통과시킨다.
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("1y", "3y", "5y", "full"):
                return s
            if not s.replace(",", "").replace(".", "", 1).isdigit():
                return v
        v = _coerce_number(v)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            days = float(v)
            if days <= 548:       # ~1.5년까지 1y
                return "1y"
            if days <= 1460:      # ~4년까지 3y
                return "3y"
            if days <= 2555:      # ~7년까지 5y
                return "5y"
            return "full"
        return v
    start_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    initial_capital: Optional[float] = Field(default=None, description="초기 자본금(원)")
    fee_rate: Optional[float] = Field(default=None, description="수수료율(%)")
    slippage_rate: Optional[float] = Field(default=None, description="슬리피지율(%)")

    _coerce = field_validator("initial_capital", "fee_rate", "slippage_rate", mode="before")(_coerce_number)


class StrategySpec(BaseModel):
    """전략 초안 본체. 값이 null인 필드는 '사용자가 말하지 않음'을 뜻하며,
    compiler가 기본값을 적용하기 전까지 확정값이 아니다."""

    name: Optional[str] = None
    universe: UniverseSpec = Field(default_factory=UniverseSpec)
    entry_conditions: List[StrategyCondition] = Field(default_factory=list)
    exit_conditions: List[StrategyCondition] = Field(default_factory=list)

    @field_validator("entry_conditions", "exit_conditions", mode="before")
    @classmethod
    def _drop_factorless_conditions(cls, v):
        # 4B 드리프트 실측(2026-07-16): 미지원 개념(FCF 등)을 unsupported_features에
        # 넣으면서 factor=null인 조건 껍데기를 함께 출력 → 조건으로 표현 불가하므로
        # 버린다(개념 자체는 unsupported_features 채널이 보존).
        if isinstance(v, list):
            return [
                item for item in v
                if not (isinstance(item, dict) and not item.get("factor"))
            ]
        return v
    ranking: List[RankingSpec] = Field(default_factory=list)
    portfolio: PortfolioSpec = Field(default_factory=PortfolioSpec)
    risk_management: RiskSpec = Field(default_factory=RiskSpec)
    backtest: BacktestSpec = Field(default_factory=BacktestSpec)


# ─── 되묻기·패치 ──────────────────────────────────────────────────────────────

class ClarificationQuestion(BaseModel):
    field: str = Field(description="누락 필드 경로 (예: 'strategy.entry_conditions[0].value')")
    question: str
    recommended_value: Optional[Union[float, str]] = None
    recommendation_reason: Optional[str] = None

    @field_validator("recommended_value", mode="before")
    @classmethod
    def _coerce_recommended(cls, v):
        # 4B 드리프트 실측(2026-07-16): 유니버스 질문에 ["KOSPI","KOSDAQ"] 리스트 추천 —
        # 표시용 문자열로 정규화(형식 정규화)
        if isinstance(v, list):
            return ", ".join(str(item) for item in v)
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return _coerce_number(v)


class PatchOp(BaseModel):
    """기존 StrategyDraft에 적용할 수정 연산(JSON Patch 부분집합)."""

    op: Literal["replace", "add", "remove"]
    path: str = Field(description="JSON Pointer 경로 (예: '/portfolio/rebalance_frequency')")
    value: Any = None


# ─── 최상위 계약 ──────────────────────────────────────────────────────────────

class StrategyIntent(BaseModel):
    """LLM Strategy Interpreter의 출력 계약(schema_version 1.0)."""

    schema_version: str = "1.0"
    intent: IntentType
    status: IntentStatus = "NEEDS_CLARIFICATION"
    strategy: Optional[StrategySpec] = None
    patches: List[PatchOp] = Field(
        default_factory=list, description="MODIFY_STRATEGY일 때 기존 draft에 적용할 패치"
    )
    missing_fields: List[str] = Field(default_factory=list)
    unsupported_features: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    clarification_questions: List[ClarificationQuestion] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        v = _coerce_number(v)
        if isinstance(v, (int, float)):
            # 4B가 0~100 스케일로 내는 드리프트 정규화
            return v / 100.0 if v > 1.0 else max(0.0, float(v))
        return 0.0 if v is None else v

    @model_validator(mode="before")
    @classmethod
    def _repair_common_drift(cls, data):
        if not isinstance(data, dict):
            return data
        # intent가 소문자/미지 값이면 대문자 정규화 후 그대로 검증에 맡긴다
        intent = data.get("intent")
        if isinstance(intent, str):
            data = {**data, "intent": intent.strip().upper()}
        status = data.get("status")
        if isinstance(status, str):
            data = {**data, "status": status.strip().upper()}
        # clarification_questions가 문자열 배열이면 구조화 형태로 승격
        cq = data.get("clarification_questions")
        if isinstance(cq, list):
            promoted = []
            for item in cq:
                if isinstance(item, str):
                    promoted.append({"field": "", "question": item})
                else:
                    promoted.append(item)
            data = {**data, "clarification_questions": promoted}
        # assumptions/missing_fields/unsupported_features에 dict 등 비문자열을 내는
        # 드리프트(실측: {"text": "...", "field": "..."}) → 문자열로 정규화
        for key in ("assumptions", "missing_fields", "unsupported_features"):
            items = data.get(key)
            if isinstance(items, list) and any(not isinstance(i, str) for i in items):
                coerced = []
                for item in items:
                    if isinstance(item, str):
                        coerced.append(item)
                    elif isinstance(item, dict):
                        coerced.append(
                            str(item.get("text") or item.get("field")
                                or json.dumps(item, ensure_ascii=False))
                        )
                    else:
                        coerced.append(str(item))
                data = {**data, key: coerced}
        return data


class ValidationReport(BaseModel):
    """검증 계층의 통합 결과. 오류/경고/누락/지원불가를 구분한다."""

    is_valid: bool = False
    status: IntentStatus = "NEEDS_CLARIFICATION"
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    unsupported_features: List[str] = Field(default_factory=list)
    suggested_fixes: List[str] = Field(default_factory=list)
    clarification_questions: List[ClarificationQuestion] = Field(default_factory=list)
