"""StrategyIntent 중간 표현 — LLM 출력과 백테스트 DSL 사이의 계약.

인터프리터 LLM(STRATEGY_INTERPRETER_MODEL, 현재 Qwen 3.5 9B)은 이 스키마의 JSON만
출력한다. LLM이 직접 백테스트 DSL(ParsedStrategy)을 생성하지 않으며, 검증 계층을
통과한 StrategyIntent만 compiler가 ParsedStrategy로 변환한다.

소형 로컬 모델의 흔한 스키마 드리프트(숫자를 문자열로, 단일 값을 배열로, "10%" 같은
단위 붙은 값 — 아래 4B 실측 주석들은 당시 모델 기준 기록)는 ValidationError로 통째로
버리지 않고 field validator에서 복구한다 — 이는 자연어 해석이 아니라 형식 정규화이므로
결정론 코드의 영역이다.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

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

# 이벤트(교차/터치) 연산자 — 임계값 없이 방향만으로 신호가 성립한다.
_EVENT_OPERATORS = frozenset({"crosses_above", "crosses_below"})

# 스키마 밖 표기 → 정본 연산자. 표기 차이만 흡수한다(새 의미를 만들지 않는다).
_OPERATOR_ALIASES = {
    "above": ">", "below": "<",
    "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "golden_cross": "crosses_above", "dead_cross": "crosses_below",
    "cross_above": "crosses_above", "cross_below": "crosses_below",
}

# 연산자가 가리키는 방향. 같은 지표라도 진입과 방향이 반대면 서로 다른 신호다
# (골든크로스↔데드크로스, 20일선 위↔아래). 미러 복제 판정에만 쓴다.
_OPERATOR_DIRECTION = {
    "crosses_above": "up", ">": "up", ">=": "up",
    "crosses_below": "down", "<": "down", "<=": "down",
}


def _opposes_entry_direction(exit_operator: Optional[str], entry_operators: set) -> bool:
    """청산 연산자가 같은 팩터의 진입 방향과 반대인가(= 새 정보인가)."""
    direction = _OPERATOR_DIRECTION.get(exit_operator)
    if direction is None:
        return False
    entry_directions = {_OPERATOR_DIRECTION.get(op) for op in entry_operators}
    entry_directions.discard(None)
    return bool(entry_directions) and direction not in entry_directions

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

    @field_validator("operator", mode="before")
    @classmethod
    def _normalize_operator(cls, v):
        # 9B 드리프트 실측(2026-08-05): 스키마에 없는 낱말 연산자를 낸다("5일 EMA가 20일
        # EMA 위에 있을 때" → operator="above"). 그대로 두면 registry 허용 목록에 걸려
        # 조건이 통째로 미지원 처리되고, 컴파일러도 방향(mode)을 정하지 못해 신호가 빈다.
        # 표기만 보고 결정 가능한 동의어이므로 형식 정규화한다(의미 판정 아님).
        if not isinstance(v, str):
            return v
        return _OPERATOR_ALIASES.get(v.strip().lower(), v)

    @field_validator("parameters", mode="before")
    @classmethod
    def _coerce_parameters(cls, v):
        # 9B 드리프트 실측(2026-07-30): 기간을 말하지 않은 조건에 parameters를 빈 dict가
        # 아니라 null로 낸다("20일선을 깨고 내려오면 매도" → parameters=null). 그대로
        # 두면 dict_type ValidationError로 출력 전체가 버려져 복구 재요청 1회(수 초)를
        # 무조건 태우고, 재요청 결과도 기간을 채워 오지 않았다. 없음의 표기 차이일 뿐이므로
        # 형식 정규화한다(sectors·symbols의 null 처리와 동형).
        if v is None:
            return {}
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
    # 기본값을 "top"으로 두면 **LLM이 방향을 말하지 않은 것**과 사용자가 높은 순을
    # 지정한 것이 구별되지 않는다 — PER처럼 낮을수록 저평가인 지표에서 무언의 top은
    # '가장 비싼 종목 선정'이 되어 전략이 뒤집힌다(물질화 기본값이 명시로 둔갑하는
    # 것과 같은 함정). 미지정은 None으로 남기고, 컴파일러가 지표의 자연 방향
    # (concept_ontology.natural_ranking_direction)으로 채운다.
    direction: Optional[Literal["top", "bottom"]] = Field(default=None)
    quantile_groups: Optional[int] = Field(
        default=None,
        description=(
            "분위 그룹 수 — '10개 그룹으로 나눠 비교'/'십분위 분석'=10. "
            "그룹별로 각각 백테스트해 비교하는 요청일 때만. 언급 없으면 null"
        ),
    )
    source_text: Optional[str] = None


class UniverseSpec(BaseModel):
    markets: List[Literal["KOSPI", "KOSDAQ", "KOSPI200", "KOSDAQ150", "ETF"]] = Field(
        default_factory=list,
        description=(
            "투자 대상 시장. **언급이 없으면 빈 배열** — 기본값은 시스템이 정하므로 "
            "지어내지 말 것(빈 배열이 '사용자가 시장을 말하지 않았다'는 신호다). "
            "ETF/ETN/상장지수펀드 상품 대상이면 ['ETF'] 단독(주식 시장과 혼합 금지)"
        ),
    )
    sectors: List[str] = Field(
        default_factory=list, description="업종/섹터 제한. 언급 없으면 빈 배열"
    )
    symbols: List[str] = Field(
        default_factory=list,
        description=(
            "지정 종목(단일/지정 종목 백테스트). 사용자가 특정 종목을 지목하면 그 표현을 "
            "그대로 넣는다('삼성전자', 'SK하이닉스', '005930'). 종목코드 변환은 시스템이 "
            "하므로 코드를 지어내지 말 것. 언급 없으면 빈 배열"
        ),
    )
    etf_theme: Optional[str] = Field(
        default=None,
        description=(
            "ETF 전용 테마/상품명 키워드. markets=['ETF']이고 '반도체 ETF'·'미국 ETF'·"
            "'KODEX 200' 등 테마/상품명이 언급되면 그 키워드('반도체', '미국', 'KODEX 200'). "
            "엔진이 ETF 상품명과 매칭해 유니버스를 좁힌다. 언급 없으면 null"
        ),
    )
    # 테마 유니버스 **출처 표기**(FR-STR-071 ⑤) — 시스템이 채우고 시스템이 읽는다.
    # symbols에는 이미 해석된 종목코드만 있어서, 이 표기가 없으면 초안만 보고는 "이
    # 종목들이 어느 테마에서 왔는지"를 알 수 없다. 그러면 테마를 바꾸라는 요청에
    # 이전 테마의 종목을 비워도 되는지 판정할 근거가 사라진다(2026-07-30 사고).
    # LLM은 채우지 않는다 — 테마 교체 요청도 sectors 패치로 표현한다(규칙 10-2).
    theme: Optional[str] = Field(
        default=None,
        description=(
            "지정 종목이 어느 테마 조회에서 왔는지(시스템이 채움). 초안에서 참고만 하고 "
            "직접 채우거나 패치하지 말 것 — 업종·테마 지정·교체는 sectors로 표현한다"
        ),
    )

    # 신규 상장 유니버스(FR-STR-073)는 '개념'과 '값'을 분리한다 — 조건의 factor/value와
    # 같은 이유다. "신규 상장 종목"에는 기간 수치가 없으므로 값을 지어내면 무단 확정이
    # 되고, 개념까지 비우면 사용자가 말한 제한이 조용히 사라진다.
    new_listing_only: bool = Field(
        default=False,
        description=(
            "신규 상장(IPO) 종목만 대상으로 하는지. '신규 상장 종목', '최근 상장한 종목', "
            "'상장한 지 얼마 안 된 종목', '공모주' 언급 시 true. 기간 수치가 없어도 true"
        ),
    )
    listing_from: Optional[str] = Field(
        default=None,
        description=(
            "그 '신규'의 시기 — 상장일 하한(YYYY-MM-DD, 포함). "
            "'2026년 신규 상장'=2026-01-01, '최근 1년 내 상장'=오늘로부터 1년 전 날짜. "
            "시기를 말하지 않았으면 null(시스템이 되묻는다 — 날짜를 지어내지 말 것)"
        ),
    )
    listing_to: Optional[str] = Field(
        default=None,
        description=(
            "상장일 상한(YYYY-MM-DD, 포함). '2026년 신규 상장'=2026-12-31. "
            "'최근 N개월 내 상장'처럼 상한이 없는 표현이면 null"
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
                "KOSDAQ150": "KOSDAQ150", "코스닥150": "KOSDAQ150",
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

    @model_validator(mode="after")
    def _imply_new_listing_concept(self):
        # 구간만 내고 개념 플래그를 빠뜨리는 드리프트("2026년 상장"→listing_from만) 정규화 —
        # 구간이 있으면 개념은 자명하다(형식 정규화, 의미 추론 아님).
        if self.listing_from is not None or self.listing_to is not None:
            self.new_listing_only = True
        return self

    @field_validator("sectors", "symbols", mode="before")
    @classmethod
    def _coerce_str_list(cls, v):
        # 단일 문자열·null 드리프트 정규화. 조건형 객체 드리프트 — /universe/symbols/- 패치
        # 값을 {"factor":null,...,"source_text":"..."} 객체로 내는 실측(2026-07-26) — 는
        # 그 인용(source_text)을 표현 문자열로 구제한다. 여기서 조용히 버리면 항목이
        # universe_resolver에 도달하지 못해 unresolved 보고조차 안 되고, 종목 추가 수정이
        # '변경 없음'으로 끝난다(테마 유니버스 종목 추가 소실 사고).
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, dict):
                    item = item.get("source_text") or item.get("value")
                if isinstance(item, str):
                    out.append(item)
            return out
        return v


class PortfolioSpec(BaseModel):
    selection_count: Optional[int] = Field(default=None, description="선택 종목 수. 언급 없으면 null")
    selection_percent: Optional[float] = Field(
        default=None,
        description="선택 비율(%) — '상위 10% 종목 편입'=10. 개수가 아니라 비율로 말했을 때만. 언급 없으면 null",
    )
    weighting: Optional[str] = Field(default=None, description="비중 방식 (예: 'equal'). 언급 없으면 null")
    rebalance_frequency: Optional[str] = Field(
        default=None,
        description="리밸런싱 주기: daily/weekly/monthly/bimonthly/quarterly/yearly. 언급 없으면 null",
    )
    hold_period_days: Optional[int] = Field(default=None, description="최대 보유 기간(거래일)")

    _coerce_count = field_validator("selection_count", "hold_period_days", mode="before")(_coerce_number)
    _coerce_pct = field_validator("selection_percent", mode="before")(_coerce_number)


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


# 버킷(1y/3y/5y/full)이 아닌 상대 기간 표기. 오늘 기준 명시 날짜로 바꾼다.
_RELATIVE_YEARS_RE = re.compile(r"^(\d{1,2})\s*(?:y|년)$")
_RELATIVE_MONTHS_RE = re.compile(r"^(\d{1,3})\s*(?:m|개월|달)$")


class BacktestSpec(BaseModel):
    period: Optional[Literal["1y", "3y", "5y", "full"]] = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _relative_period_to_dates(cls, data):
        """버킷 밖 상대 기간("10y"·"18개월")을 오늘 기준 명시 날짜 창으로 바꾼다.

        period가 가질 수 있는 값은 넷뿐이라 그 밖의 표기는 Literal 검증에서 탈락하고,
        수정 턴에서는 패치가 통째로 폐기돼 "해석하지 못했어요"로 끝났다(2026-07-31 QA:
        '10년' 2/2 실패). 가장 가까운 버킷으로 올리는 방식은 쓰지 않는다 — 사용자가 말한
        적 없는 창이 된다. 명시 날짜 변환은 `nl_parser._extract_backtest_dates`가 같은
        입력에 이미 쓰는 정본 정책이며, 창의 길이가 사용자가 말한 그대로 보존된다.
        """
        if not isinstance(data, dict):
            return data
        period = data.get("period")
        if not isinstance(period, str):
            return data
        s = period.strip().lower()
        if s in ("1y", "3y", "5y", "full"):
            return data
        if data.get("start_date") or data.get("end_date"):
            # 명시 날짜가 이미 창을 정했다 — 버킷 밖 표기를 남겨 Literal 검증을
            # 실패시키느니 비운다(날짜가 우선이라는 기존 계약과 같은 방향).
            return {**data, "period": None}
        years_match = _RELATIVE_YEARS_RE.match(s)
        months_match = _RELATIVE_MONTHS_RE.match(s)
        if years_match:
            years = int(years_match.group(1))
            if years in (1, 3, 5) or not 1 <= years <= 30:
                return data
            months = years * 12
        elif months_match:
            months = int(months_match.group(1))
            if not 12 <= months <= 360:   # 12개월 미만은 백테스트 최소 기간 미달
                return data
        else:
            return data
        today = date.today()
        start_year = today.year - months // 12
        start_month = today.month - months % 12
        if start_month <= 0:
            start_month += 12
            start_year -= 1
        try:
            start = date(start_year, start_month, today.day)
        except ValueError:            # 2월 29일 등 존재하지 않는 날짜 보정
            start = date(start_year, start_month, 28)
        return {**data, "period": None,
                "start_date": start.isoformat(), "end_date": today.isoformat()}

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
            # 9B 드리프트 실측(2026-07-31): '전체 기간' 자유 입력에 period="all"을 낸다 —
            # Literal 밖이라 패치가 통째로 폐기돼 "해석하지 못했어요"로 끝났다(2/2 재현).
            # 뜻이 같은 표기를 정본 값으로 맞추는 것뿐이므로 의미 판단이 아니다.
            if s in ("all", "entire", "max", "전체", "전체기간", "전체 기간", "가능한 전체"):
                return "full"
            # 버킷 연수의 표기 변형("5년"·"5 y"·"5Y")도 같은 정규화 대상이다. 버킷이 아닌
            # 연수(2년·10년)는 여기서 바꾸지 않는다 — 가장 가까운 버킷으로 올리면 사용자가
            # 말하지 않은 창이 된다. 그 경우의 정본은 명시 날짜 변환이다(프롬프트 규칙 12-1).
            bucket_year = re.fullmatch(r"(1|3|5)\s*(?:y|년)", s)
            if bucket_year:
                return f"{bucket_year.group(1)}y"
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
    execution_timing: Optional[Literal["next_open", "current_close"]] = Field(
        default=None,
        description=(
            "체결 시점. '당일 종가에 매수/체결'처럼 종가 체결을 명시하면 'current_close', "
            "언급이 없으면 null(시스템 기본 next_open=다음 날 시가)"
        ),
    )
    initial_capital: Optional[float] = Field(default=None, description="초기 자본금(원)")
    fee_rate: Optional[float] = Field(default=None, description="수수료율(%)")
    slippage_rate: Optional[float] = Field(default=None, description="슬리피지율(%)")

    _coerce = field_validator("initial_capital", "fee_rate", "slippage_rate", mode="before")(_coerce_number)


# 조건 목록에 미러된 스칼라 설정 슬롯의 정본 자리. 트레이스 전수 조사(2026-08-06,
# 4일치 조건 관측 2,366건)에서 Registry 밖 factor 7종 중 6종이 이 미러였다:
#   risk_management.stop_loss(1) · stop_loss(8) · fundamental.stop_loss(4, 오염
#   네임스페이스) · portfolio.hold_period_days(8) · hold_period_days(8) ·
#   time.days_held(16 — 프롬프트가 금지해도 낸다). 나머지 1종(technical.beta)만
#   진짜 미지원 개념이라 "반영하지 못했어요" 안내가 정당하다.
# 맨 이름은 세 스펙에 걸쳐 유일할 때만 등록한다. "period"만 제외 — 지표 파라미터 이름
# (RSI period 등)과 겹쳐, 흡수하면 사용자가 말한 적 없는 백테스트 창을 지어낸다.
_SCALAR_SLOT_SPECS: tuple = (
    ("risk_management", RiskSpec),
    ("portfolio", PortfolioSpec),
    ("backtest", BacktestSpec),
)
_SLOT_FACTOR_MAP: Dict[str, tuple] = {}
for _attr, _spec_cls in _SCALAR_SLOT_SPECS:
    for _field in _spec_cls.model_fields:
        _SLOT_FACTOR_MAP[f"{_attr}.{_field}"] = (_attr, _field)
        if _field != "period" and _field not in _SLOT_FACTOR_MAP:
            _SLOT_FACTOR_MAP[_field] = (_attr, _field)
# 같은 슬롯의 다른 표기 — LLM 실측(time.days_held)과 엔진 DSL 이름(max_holding_days).
# 표기만 보고 결정 가능한 동의어라 _OPERATOR_ALIASES와 같은 형식 정규화 레인이다.
_SLOT_FACTOR_MAP["days_held"] = ("portfolio", "hold_period_days")
_SLOT_FACTOR_MAP["max_holding_days"] = ("portfolio", "hold_period_days")


def _scalar_slot_target(factor: Any) -> Optional[tuple]:
    """factor 표기 → (스펙 attr, 필드명). 미러가 아니면 None.

    정확 일치 후 마지막 세그먼트로 재조회한다 — 9B가 네임스페이스를 지어내거나
    (fundamental.stop_loss, time.days_held) 틀리게 붙인 실측 대응. Registry 정본 id
    68종의 마지막 세그먼트와 슬롯 필드명은 겹치지 않음을 확인했다(2026-08-06) —
    겹치는 지표가 새로 생기면 여기 판정보다 Registry 등재가 우선이 되도록
    capability_validator가 먼저 factor를 정본화하지 않는 현 순서(모델 검증이 먼저)를
    감안해 이름을 피해서 등재한다.
    """
    name = str(factor or "")
    target = _SLOT_FACTOR_MAP.get(name)
    if target is not None:
        return target
    if "." in name:
        return _SLOT_FACTOR_MAP.get(name.rsplit(".", 1)[-1])
    return None


class StrategySpec(BaseModel):
    """전략 초안 본체. 값이 null인 필드는 '사용자가 말하지 않음'을 뜻하며,
    compiler가 기본값을 적용하기 전까지 확정값이 아니다."""

    name: Optional[str] = None
    universe: UniverseSpec = Field(default_factory=UniverseSpec)
    entry_conditions: List[StrategyCondition] = Field(default_factory=list)
    exit_conditions: List[StrategyCondition] = Field(default_factory=list)
    # entry_conditions가 여러 개일 때의 결합 방식. 기본 AND — "동시에"·"그리고"처럼
    # 자연어에서 여러 기술적 조건은 모두 성립해야 하는 것이 일반적 의미다. "또는"·
    # "둘 중 하나"처럼 대안 관계를 명시했을 때만 OR(스펙 § entry_logic).
    entry_logic: Literal["AND", "OR"] = "AND"

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

    @model_validator(mode="after")
    def _drop_mirrored_valueless_exits(self):
        # 4B 드리프트 실측(2026-07-20): 진입 조건(PER<=10, RSI 등)을 임계값 없이 청산
        # 조건에 그대로 복제해 출력 → 사용자가 진입에서 이미 준 값을 "청산 조건의 PER
        # 기준값?"이라며 되묻는 사고. 값이 없고 진입 팩터를 중복하는 청산 조건은 새 정보가
        # 없으므로 버린다(사용자가 실제 청산 임계값을 줬다면 value가 채워져 보존된다).
        #
        # 단, **반대 방향** 청산은 정상적인 짝이다 — 골든크로스 진입/데드크로스 청산,
        # 볼린저 하단 매수/상단 매도는 둘 다 value가 없고 factor도 같지만 서로 다른
        # 신호다(2026-07-26 A/B 실측: 이 가드가 정당한 청산을 삼켰고, 원문 정규식 재추출이
        # 그것을 가리고 있었다).
        #
        # 방향은 교차(crosses_*)뿐 아니라 부등호로도 표현된다 — "5일 EMA가 20일 EMA 위에
        # 있으면 매수, 아래로 내려오면 매도"의 청산은 `<`다. 예외를 교차 연산자에만 열어
        # 두면 이 부등호 짝이 미러로 오인돼 사용자가 명시한 청산이 조용히 사라진다
        # (2026-08-05 전수 QA 치명 2건). 연산자를 방향(up/down)으로 환산해 판정한다.
        if self.exit_conditions and self.entry_conditions:
            entry_ops: Dict[str, set] = {}
            for c in self.entry_conditions:
                entry_ops.setdefault(c.factor, set()).add(c.operator)
            self.exit_conditions = [
                c for c in self.exit_conditions
                if not (
                    c.value is None
                    and c.factor in entry_ops
                    and not _opposes_entry_direction(c.operator, entry_ops[c.factor])
                )
            ]
        return self

    @model_validator(mode="after")
    def _absorb_scalar_slot_conditions(self):
        # 9B 드리프트 실측(2026-08-05): "손절 -8%"를 risk_management.stop_loss에 채우고
        # **같은 사실을** exit_conditions에 factor="risk_management.stop_loss"로 한 번 더
        # 출력. 손절·보유 기간은 의미상 청산 규칙이 맞지만 스키마 자리는 하나다
        # (사용자 판정: 중복은 환각이 아니라 자리 문제) — 조건 목록의 스칼라 슬롯 항목은
        # 값을 빈 슬롯으로 흡수한 뒤 제거해 한 번만 남긴다. 값도 없고 슬롯도 비어 있으면
        # 남긴다(미지원 팩터 레인이 안내를 담당 — 조용한 누락 금지).
        #
        # 2026-08-06 확장(보유 기간 사고 2건): 종전에는 risk_management.*만 판정해
        # factor="hold_period_days"(맨 이름)·"portfolio.hold_period_days" 미러가
        # Registry 부재로 컴파일에서 버려지고, portfolio.hold_period_days에 정상 반영된
        # 값이 "'보유는 최대 25거래일' 조건은 반영하지 못했어요"라는 거짓 안내를 받았다.
        # 판정을 _SLOT_FACTOR_MAP(risk/portfolio/backtest 스칼라 슬롯 전부 + 유일한
        # 맨 이름)으로 넓힌다. 값 흡수는 스펙 자체 검증(model_validate)을 통과할 때만 —
        # RiskSpec._abs_ratio(크기만)·BacktestSpec 버킷 정규화가 그대로 적용되고,
        # Literal 밖 값은 흡수하지 않고 조건으로 남겨 안내 레인으로 보낸다.
        for attr in ("entry_conditions", "exit_conditions"):
            kept = []
            for cond in getattr(self, attr):
                target = _scalar_slot_target(cond.factor)
                if target is not None:
                    slot_attr, field = target
                    spec_obj = getattr(self, slot_attr)
                    current = getattr(spec_obj, field)
                    if current is None and cond.value is not None:
                        try:
                            setattr(self, slot_attr, spec_obj.__class__.model_validate(
                                {**spec_obj.model_dump(), field: cond.value}))
                            current = getattr(getattr(self, slot_attr), field)
                        except ValidationError:
                            current = None
                    if current is not None:
                        continue
                kept.append(cond)
            setattr(self, attr, kept)
        return self


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


# Planner/Interpreter가 제안할 수 있는 연산의 전부(2026-07-30 하이브리드 상태 모델).
# **상태를 바꾸는 연산은 여기 없다.** MARK_NOT_APPLICABLE·MARK_INVALID·MARK_CONFLICT·
# REVALIDATE를 추가하지 않는 것은 누락이 아니라 계약이다:
#   · NOT_APPLICABLE·INVALID·CONFLICTED는 저장하지 않는 파생 상태이고, 판정은 매 턴
#     결정론 evaluator(validation/pipeline.py → field_state.py → strategy_slots.py)가
#     현재 전략 전체를 보고 다시 내린다. 패치로 기록하면 같은 판정이 두 곳에서 갈라지고,
#     되돌림 패치를 LLM이 빠뜨리는 순간 멀쩡한 조건에 '적용 불가'가 영구히 남는다.
#   · REVALIDATE는 파이프라인이 무조건 수행하는 일이라 지시할 대상이 없다 — 필드를
#     만들면 LLM이 그것을 **빠뜨릴 수 있게** 되어 없을 때보다 나빠진다.
# 도메인 의미가 더 분명한 Patch DSL이 필요해지면 별도 마이그레이션으로 분리한다
# (지금 개명하면 수정 RAG 코퍼스·프롬프트 예시·9B 수정 레인을 전부 재검증해야 한다).
ALLOWED_PATCH_OPS: frozenset[str] = frozenset({"add", "replace", "remove"})


class PatchOp(BaseModel):
    """기존 StrategyDraft에 적용할 수정 연산(JSON Patch 부분집합).

    wire format은 JSON Patch를 유지한다 — 코퍼스와 프롬프트 예시가 이 어휘를 가르친다.
    허용 연산은 ALLOWED_PATCH_OPS가 정본이며, 상태 표시 연산은 포함하지 않는다.
    """

    op: Literal["replace", "add", "remove"]
    path: str = Field(description="JSON Pointer 경로 (예: '/portfolio/rebalance_frequency')")
    value: Any = None
    source_text: Optional[str] = Field(
        default=None,
        description="이 패치를 요청한 사용자 원문 조각(그대로 인용). 환각 게이트의 출처 대조에 쓰인다",
    )


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
    # 모순이 발견된 진행 골격 슬롯 필드(engine.strategy_slots 어휘: 'entry'/'exit').
    # 오류 문장만으로는 어느 필드가 모순인지 알 수 없어 상태 축(§ 5 CONFLICTED)을
    # 붙일 수 없다 — 판정한 자리에서 함께 기록한다.
    conflicted_slots: List[str] = Field(default_factory=list)
