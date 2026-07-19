"""
자연어 전략 파서 (NL Strategy Parser)

사용자가 한국어로 입력한 전략 설명을 구조화된 ParsedStrategy로 변환한다.
LLM 백엔드: Ollama (instructor) 또는 MLX (outlines)
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import re
import time
from datetime import date
from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from llm_backend import OLLAMA_BASE_URL, is_local_ollama, ollama_auth_headers
from engine.universe_pit import (
    CANONICAL_SECTORS,
    normalize_sector,
    normalize_sector_value,
    sector_value_as_list,
    sectors_for_llm_prompt,
)

# ParsedStrategy.sector 필드 설명에 들어가는 지원 섹터 목록(정본은 universe_pit).
_CANONICAL_SECTORS_DOC = CANONICAL_SECTORS

logger = logging.getLogger(__name__)

# Modal serverless GPU 콜드스타트 내성.
#
# ★ 근본원인(프로덕션 실측 2026-06): Modal scale-to-zero 컨테이너로의 **첫 POST는 요청
#   본문이 유실된다**. 콜드스타트 프록시가 컨테이너를 깨우는 동안 POST body를 버퍼링/재전송
#   하지 못해, ollama에는 본문 없는 요청이 도착하고 `{"error":"missing request body"}` (HTTP
#   400) 또는 `Missing request, possibly due to expiry or cancellation` (HTTP 408)이 반환된다.
#   같은 POST를 재시도해도 컨테이너가 완전히 뜰 때까지 계속 body가 유실돼 실패한다(실측: 320s
#   동안 400 29회 연속).
#
# ★ 해결: 본문이 없는 **GET /api/tags로 컨테이너를 먼저 깨운다**(_ollama_ensure_warm). GET은
#   유실될 body가 없어 콜드스타트에도 안전하게 통과하고, 한 번 200을 받으면 컨테이너가 RUNNING
#   상태가 되어 이후 POST는 body가 보존된다(실측: tags→chat 순서면 콜드에서도 chat 200).
#   POST 자체에도 재시도(_ollama_open_with_retry)를 백업으로 둔다.
#
# 콜드스타트 후 첫 /api/chat은 모델 VRAM 로드 ~60s + 첫 추론 워밍업 ~70s = ~130s+ 가 더 걸린다.
#
# 재시도 전략(_ollama_open_with_retry):
#   - TimeoutError / OSError → 재시도 않고 즉시 raise (hang은 단일 long timeout으로 대기)
#   - URLError(연결거부 등) → 재시도. 단 로컬 엔드포인트는 콜드스타트가 없으므로
#     연결 실패 시 즉시 raise(_is_local_connection_error) — 503 친화 메시지로 빠른 안내
#   - HTTP 4xx/5xx(400/408 body-drop 포함, 영구 400 제외) → 재시도
#   ※ 프론트 코치 타임아웃(app/api/strategy/coach/route.ts)을 warmup+POST 예산 합보다 크게 유지
_OLLAMA_COLD_START_STATUSES = {400, 408, 425, 429, 500, 502, 503, 504}
_OLLAMA_RETRY_BUDGET_S = 320.0
_OLLAMA_RETRY_BACKOFF_S = 3.0
_OLLAMA_MAX_ATTEMPT_TIMEOUT_S = 240  # 콜드스타트 단일 요청(VRAM 로드 ~60s + 첫 추론 ~70s) 커버
_OLLAMA_WARMUP_BUDGET_S = 200.0  # 본문 없는 GET으로 콜드 컨테이너를 깨우는 예산
# 코치 system prompt(~5.5KB)+user+context는 ~5800토큰이라 ollama 기본 num_ctx(4096)를 넘어
# "exceeds the available context size" 400을 낸다(프로덕션 실측). 응답·후속대화 여유까지 커버.
_OLLAMA_NUM_CTX = 16384
# 콜드스타트 일시 400과 구별할 영구 400(설정 오류) 시그니처 — 이런 본문은 재시도하지 않는다.
_OLLAMA_PERMANENT_400_SIGNATURES = ("model is required", "not found", "no such model")


def _http_400_is_permanent(err) -> bool:
    """HTTP 400이 콜드스타트 일시 오류가 아니라 영구 설정 오류(모델명 누락/없음)인지 판정한다.

    본문을 읽어 영구 시그니처가 있으면 True. 본문을 못 읽으면(콜드스타트 프록시 400 등)
    보수적으로 False(=일시 오류로 보고 재시도)를 반환한다.
    """
    try:
        body = err.read().decode("utf-8", "replace").lower()
    except Exception:
        return False
    return any(sig in body for sig in _OLLAMA_PERMANENT_400_SIGNATURES)


def _is_local_connection_error(err: Exception) -> bool:
    """로컬 Ollama 엔드포인트의 연결 실패인지 판정한다(콜드스타트 재시도 제외 대상).

    재시도 루프는 Modal scale-to-zero 콜드스타트용이다. 로컬은 콜드스타트가 없어
    연결 거부 = 서버가 안 떠 있다는 뜻이고, 재시도해도 풀리지 않은 채 사용자만
    수 분 대기시킨다(프록시 120s 타임아웃 사고) — 즉시 raise해서 연결 실패 503
    친화 메시지로 빠르게 안내한다. HTTPError는 서버가 응답한 것이라 제외한다.
    """
    import urllib.error

    if not is_local_ollama():
        return False
    if isinstance(err, urllib.error.HTTPError):
        return False
    return isinstance(err, (urllib.error.URLError, ConnectionError, OSError))


def _ollama_ensure_warm(budget_s: float = _OLLAMA_WARMUP_BUDGET_S) -> None:
    """본문 없는 GET /api/tags로 Modal 콜드 컨테이너를 먼저 깨운다.

    콜드스타트 프록시는 첫 POST의 body를 유실시키지만(missing request body), body가 없는
    GET은 안전하게 통과한다. GET이 200을 받으면 컨테이너가 RUNNING 상태가 되어 이후 POST는
    body가 보존된다. 예산 안에서 깨우지 못하면 마지막 예외를 올린다. 로컬 Ollama처럼 이미
    떠 있으면 첫 GET이 즉시 200이라 비용이 거의 없다.
    """
    import urllib.error
    import urllib.request

    url = f"{OLLAMA_BASE_URL}/api/tags"
    deadline = time.monotonic() + budget_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        attempt_timeout = max(10, min(60, int(remaining)))
        req = urllib.request.Request(url, headers=ollama_auth_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=attempt_timeout) as resp:
                resp.read()
                return  # 컨테이너가 깨어남 → 이후 POST는 body가 보존된다
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            if _is_local_connection_error(e):
                raise
            last_err = e
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        logger.info(
            "ollama warmup waiting for Modal container | err=%r remaining_s=%.0f",
            last_err,
            remaining,
        )
        time.sleep(min(_OLLAMA_RETRY_BACKOFF_S, remaining))
    if last_err is not None:
        raise last_err


def _ollama_open_with_retry(req, timeout: int):
    """Ollama(Modal) HTTP 요청을 콜드스타트 내성 있게 연다.

    HTTP 4xx/5xx·연결오류는 예산 안에서 재시도한다.
    TimeoutError는 재시도하지 않는다 — Modal cold-start hang의 경우 단일 long
    timeout(110s)으로 기다리는 것이 반복 재시도보다 효과적이기 때문이다.
    """
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + _OLLAMA_RETRY_BUDGET_S
    attempt = 0
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        attempt += 1
        remaining = deadline - time.monotonic()
        attempt_timeout = max(15, min(_OLLAMA_MAX_ATTEMPT_TIMEOUT_S, int(remaining)))
        try:
            return urllib.request.urlopen(req, timeout=attempt_timeout)
        except urllib.error.HTTPError as e:
            last_err = e
            transient = e.code in _OLLAMA_COLD_START_STATUSES
            # 콜드스타트 400은 재시도하면 풀리지만, 설정 오류로 인한 영구 400은 즉시 올린다.
            if transient and e.code == 400 and _http_400_is_permanent(e):
                transient = False
        except urllib.error.URLError as e:
            if _is_local_connection_error(e):
                raise
            last_err = e
            transient = True
        except (TimeoutError, OSError) as e:
            # cold-start hang이 attempt_timeout을 초과한 것 — 재시도하면 역효과
            raise e
        if not transient:
            raise last_err
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        logger.warning(
            "ollama transient failure (Modal cold start?), retrying | attempt=%d err=%r remaining_s=%.0f",
            attempt,
            last_err,
            remaining,
        )
        time.sleep(min(_OLLAMA_RETRY_BACKOFF_S, remaining))
    assert last_err is not None
    raise last_err


def _ollama_preload_model(model: str, timeout: int = 600) -> None:
    """Ollama에 모델 가중치를 미리 메모리에 적재한다(첫 추론 호출 지연 제거).

    프롬프트 없는 POST /api/generate는 생성 없이 모델만 로드하고 즉시 반환한다
    (done_reason="load"). keep_alive=-1은 idle 언로드(기본 5분)를 막아 dev 중 모델을
    항상 상주시킨다. 로컬 Ollama 전용 — 원격(Modal)은 _ollama_ensure_warm을 쓴다.
    """
    import urllib.request

    body = json.dumps({"model": model, "keep_alive": -1}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=body,
        headers={"Content-Type": "application/json", **ollama_auth_headers()},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()


# ─── 스키마 정의 ──────────────────────────────────────────────────────────────

class FundamentalFilter(BaseModel):
    """재무 지표 필터 조건"""
    metric: Literal[
        "per", "pbr", "psr", "ev_ebitda", "roe_or_gpa", "roa", "debt_ratio",
        "current_ratio", "quick_ratio",
        "reserve_ratio", "net_margin", "gross_margin", "operating_margin", "revenue_growth",
        "operating_income_growth", "net_income_growth", "market_cap", "trading_value",
        "dividend_yield", "payout_rate", "dividend_growth",
    ] = Field(
        description=(
            "재무 지표 종류. "
            "per=주가수익비율, pbr=주가순자산비율, psr=주가매출비율, ev_ebitda=EV/EBITDA(배, 낮을수록 저평가), "
            "roe_or_gpa=자기자본이익률(%), "
            "roa=총자본순이익률(%), debt_ratio=부채비율(%), current_ratio=유동비율(%), "
            "quick_ratio=당좌비율(%), reserve_ratio=유보율(%), net_margin=순이익률(%), "
            "gross_margin=매출총이익률(%), operating_margin=영업이익률(%), revenue_growth=매출액증가율(%), "
            "operating_income_growth=영업이익증가율(%), net_income_growth=순이익증가율(%), "
            "market_cap=시가총액(억원), trading_value=일평균거래대금(억원), "
            "dividend_yield=배당수익률(%, 높을수록 고배당), payout_rate=배당성향(%), "
            "dividend_growth=배당성장률(%, 전년 대비 주당배당 증가율)"
        )
    )
    operator: Literal["<", ">", "<=", ">="] = Field(
        description="비교 연산자. '이하'='<=', '미만'='<', '이상'='>=', '초과'='>'"
    )
    value: float = Field(description="비교 기준값")


class TechnicalSignal(BaseModel):
    """기술적 지표 진입/청산 신호"""
    indicator: Literal[
        "ma_crossover", "rsi", "ema", "macd",
        "bollinger_bands", "breakout", "volume_spike",
        "stochastic", "cci", "adx", "williams_r", "mfi", "roc", "trading_value",
        "ai_model", "ai_drop_model"
    ] = Field(description="지표 종류. williams_r=Williams %R(-100~0), mfi=자금흐름지표(0~100), roc=변화율/모멘텀(%), ai_model=AI 상승 예측 매수, ai_drop_model=AI 하락 예측 매도")
    signal_type: Literal["buy", "sell"] = Field(default="buy", description="매수=buy, 매도=sell")

    # MA / EMA 크로스오버
    short_period: Optional[int] = Field(default=None, description="단기 이동평균 기간 (ma_crossover, ema)")
    long_period: Optional[int] = Field(default=None, description="장기 이동평균 기간 (ma_crossover, ema)")

    # RSI / CCI / ADX
    period: Optional[int] = Field(default=None, description="지표 계산 기간 (rsi, cci, adx, volume_spike)")
    operator: Optional[Literal["<", ">", "<=", ">="]] = Field(default=None, description="비교 연산자 (rsi, cci, adx)")
    value: Optional[float] = Field(default=None, description="비교 기준값 (rsi, cci, adx)")

    # MACD / RSI 모드. rsi 'rebound'=과매도/과매수 임계선을 다시 돌파하는 반등(단순 임계값 비교가 아님).
    # ema 'above'/'below'=지속 상태 추세 필터(가격이 EMA 위/아래에 머무는지 — 크로스오버 아님).
    mode: Optional[Literal["crossover", "zero", "rebound", "above", "below"]] = Field(default=None, description="MACD: crossover/zero. RSI: rebound. EMA: above/below=추세 필터(가격 vs EMA 지속 상태)")

    # 브레이크아웃
    lookback_period: Optional[int] = Field(default=None, description="브레이크아웃 기준 기간 (breakout)")

    # AI 모델
    threshold: Optional[float] = Field(default=None, description="AI 모델 신뢰도 임계값 (ai_model, ai_drop_model). 예: 70 = 70% 이상 확률")


# 리스크 비율 필드는 방향이 필드 의미에 내장돼 있어("손절 -8%"=8% 하락 시 매도) 부호 없는
# 크기만 유효하다. 규칙 추출기는 부호를 캡처하지 않지만 LLM은 사용자의 '-8%'를 그대로 옮길
# 수 있고, 그러면 하한선 보정(enforce_strategy_minimums)이 "0%보다 커야" 오탐으로 값을
# 드롭해 틀린 안내가 나간다 → 모든 파싱 경로가 지나는 모델 검증 단계에서 절댓값 정규화.
_RATIO_SIGN_FIELDS = ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_mdd_limit_pct")


def _abs_ratio(value: Optional[float]) -> Optional[float]:
    return abs(value) if value is not None else None


class ParsedStrategy(BaseModel):
    """자연어 전략 → 구조화된 전략 스키마"""

    _normalize_ratio_sign = field_validator(*_RATIO_SIGN_FIELDS)(_abs_ratio)

    description: str = Field(description="사용자가 입력한 원문 전략 설명 (그대로 복사)")

    # ── 유니버스
    universe: List[Literal["KOSPI", "KOSDAQ", "KOSPI200", "ETF"]] = Field(
        default=["KOSPI200"],
        description=(
            "투자 대상 시장. 언급 없으면 ['KOSPI200'] (KOSPI 전체 종목, 유동성 우선). "
            "'코스닥'/'KOSDAQ' 언급 시 ['KOSDAQ'], '전체'/'코스피+코스닥' 언급 시 ['KOSPI', 'KOSDAQ']. "
            "ETF/ETN/상장지수펀드 상품이 대상이면 ['ETF'] 단독(주식 시장과 혼합 금지 — "
            "ETF는 기업 재무지표 없이 가격·기술 지표만 사용 가능)"
        )
    )
    # ETF 유니버스 전용 테마/상품명 필터. "반도체 ETF"→"반도체", "KODEX 200"→상품명.
    # 엔진이 ETF 이름 키워드 매칭으로 유니버스를 좁힌다(universe_pit.filter_etf_by_theme).
    etf_theme: Optional[str] = Field(
        default=None,
        description="ETF 테마/상품명 키워드. universe=['ETF']일 때만. '미국 ETF'='미국', 'KODEX 200'=상품명. 없으면 null",
    )
    sector: Optional[Union[str, List[str]]] = Field(
        default=None,
        description=(
            "업종/섹터 제한. '반도체 관련주', '2차전지 업종' 등 언급 시 해당 섹터명. "
            "여러 업종을 함께 제한하면 배열(예: [\"반도체\", \"기계/장비\"]). "
            "지원 섹터: " + ", ".join(_CANONICAL_SECTORS_DOC) + ". "
            "목록에 없는 업종이거나 언급이 없으면 null"
        ),
    )

    @field_validator("sector")
    @classmethod
    def _normalize_sector_name(cls, v):
        # LLM이 자유 문자열('배터리', '2차전지')이나 배열을 내도 정규형으로 정규화한다
        # (없음=None, 단일=str — 기존 해시·직렬화 호환, 복수=list). 정규화 불가(미지원
        # 업종) 항목은 버린다 — 침묵 왜곡 방지는 미지원 개념 안내가 담당한다.
        return normalize_sector_value(v)

    @model_validator(mode="before")
    @classmethod
    def _repair_llm_schema_drift(cls, data):
        """4B LLM 폴백의 흔한 스키마 드리프트를 ValidationError로 통째로 버리지 않고 복구한다.

        실측 사고(2026-07-12): "2차전지에 투자하는 전략" → LLM이 업종을 universe에 넣고
        description을 빼먹어 ValidationError → _build_fallback_strategy가 LLM의 해석
        (sector 포함)을 전부 폐기 → 업종 제한 없는 전체 시장 전략이 조용히 만들어졌다.
        ① universe 항목 중 시장이 아닌 값: 정본 업종으로 해석되면 sector로 이동(비어 있을
           때만), 한글 시장명은 영문 코드로 정규화, 그 외는 제거. 업종만 있었으면 섹터 전략
           기본 유니버스(양시장)를, 아무것도 안 남고 이동도 없었으면 스키마 기본값을 따른다.
        ② description 누락/비문자열 → 빈 문자열(원문은 _apply_prompt_overrides가 채움).
        룰 파서·저장 DSL 등 정상 입력에는 no-op이다."""
        if not isinstance(data, dict):
            return data
        raw_universe = data.get("universe")
        if isinstance(raw_universe, str):
            raw_universe = [raw_universe]
        if isinstance(raw_universe, list):
            market_map = {
                "KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ", "KOSPI200": "KOSPI200",
                "코스피": "KOSPI", "코스닥": "KOSDAQ", "코스피200": "KOSPI200",
                "ETF": "ETF", "ETN": "ETF", "이티에프": "ETF", "상장지수펀드": "ETF",
            }
            markets: list[str] = []
            moved_sector = False
            for item in raw_universe:
                if not isinstance(item, str):
                    continue
                token = market_map.get(item.replace(" ", "").upper())
                if token:
                    if token not in markets:
                        markets.append(token)
                    continue
                canonical = normalize_sector(item)
                if canonical and not data.get("sector"):
                    data = {**data, "sector": canonical}
                    moved_sector = True
            if markets:
                data = {**data, "universe": markets}
            elif moved_sector:
                data = {**data, "universe": ["KOSPI", "KOSDAQ"]}
            elif any(not isinstance(i, str) or i not in ("KOSPI", "KOSDAQ", "KOSPI200")
                     for i in raw_universe):
                data = {k: v for k, v in data.items() if k != "universe"}
        desc = data.get("description")
        if (not isinstance(desc, str) or not desc.strip()) and (set(data) - {"description"}):
            # 다른 전략 내용이 있을 때만 채운다 — 빈/무의미 출력({})은 여전히 ValidationError로
            # 결정론 폴백에 위임한다(description을 사실상 optional로 만들지 않기 위한 가드).
            data = {**data, "description": ""}
        return data

    @model_validator(mode="after")
    def _normalize_etf_universe(self):
        """ETF 유니버스는 주식 시장과 혼합하지 않는다(단독) — ETF 데이터만 조회한다는
        계약의 스키마 강제. ETF엔 종목 섹터 분류가 없으므로 sector는 비우고(테마는
        etf_theme가 담당), 주식 유니버스에 남은 etf_theme는 의미가 없어 비운다."""
        if "ETF" in self.universe:
            if self.universe != ["ETF"]:
                self.universe = ["ETF"]
            if self.sector is not None:
                self.sector = None
        elif self.etf_theme is not None:
            self.etf_theme = None
        return self

    # ── 재무 필터
    fundamental_filters: List[FundamentalFilter] = Field(
        default_factory=list,
        description="재무 필터 목록. PBR, PER, ROE, 부채비율, 시가총액, 거래대금 조건"
    )

    # ── 기술적 신호
    entry_signals: List[TechnicalSignal] = Field(
        default_factory=list,
        description="매수 진입 기술 조건. 재무 필터만 있으면 빈 배열 []"
    )
    exit_signals: List[TechnicalSignal] = Field(
        default_factory=list,
        description="매도 청산 기술 조건. 보유기간 청산이면 빈 배열 []"
    )
    # 진입 신호와 AND로 결합되는 게이트(추세 필터·RSI 결합·거래대금 필터). 엔진은 type='filter'로
    # 항상 AND 결합한다. 빌더 전용 채널이며 LLM은 출력하지 않는다(기본 빈 배열, 하위호환).
    entry_filters: List[TechnicalSignal] = Field(
        default_factory=list,
        description="진입 게이트 필터(AND). 추세(EMA above/below)·RSI 결합·거래대금 등. 없으면 []"
    )

    # ── 종목 선정 랭킹 (횡단면)
    ranking_metric: Optional[Literal["return"]] = Field(
        default=None,
        description=(
            "종목 간 순위로 선정하는 방식. 'return'=최근 수익률 상위 종목 선정(상대강도/모멘텀 랭킹). "
            "예: '최근 60일 수익률 높은 상위 N종목'. 진입 신호 없이 순위 자체가 진입. 없으면 null"
        ),
    )
    ranking_lookback_days: Optional[int] = Field(
        default=None,
        description="랭킹 산정 기간(거래일). 예: '60거래일 수익률'=60. ranking_metric이 있을 때만. 없으면 null(기본 60)",
    )

    # ── 포트폴리오
    max_positions: int = Field(
        default=10, ge=1, le=100,
        description="동시 보유 최대 종목 수. '10개', '20종목' 등에서 추출"
    )
    hold_period_days: Optional[int] = Field(
        default=None,
        description="최대 보유 기간(거래일). 1년=252, 6개월=126, 3개월=63, 1개월=21. 없으면 null"
    )
    rebalancing_period: Literal["none", "daily", "weekly", "monthly", "bimonthly", "quarterly", "yearly"] = Field(
        default="none",
        description="정기 리밸런싱 주기. '매일'=daily, '매주/주간'=weekly, '매월'=monthly, '격월/두 달에 한 번'=bimonthly, '분기'=quarterly, '매년/1년마다'=yearly, 언급없음=none"
    )

    # ── 리스크 관리
    stop_loss_pct: Optional[float] = Field(
        default=None,
        description="손절 비율(%). 예: '10% 손절'=10.0. 없으면 null"
    )
    take_profit_pct: Optional[float] = Field(
        default=None,
        description="익절 비율(%). 예: '20% 익절'=20.0. 없으면 null"
    )
    trailing_stop_pct: Optional[float] = Field(
        default=None,
        description="트레일링 스탑 비율(%). 예: '최고가 대비 10% 하락 시 청산'=10.0. 없으면 null"
    )
    max_mdd_limit_pct: Optional[float] = Field(
        default=None,
        description="포트폴리오 최대 낙폭 한도(%). 예: 'MDD 20% 초과 시 전량 청산'=20.0. 없으면 null"
    )

    # ── 백테스트 설정
    backtest_period: Literal["1y", "3y", "5y", "full"] = Field(
        default="5y",
        description="백테스트 기간. 언급 없으면 '5y'"
    )
    backtest_start_date: Optional[str] = Field(
        default=None,
        description="명시적 백테스트 시작일(YYYY-MM-DD). 시스템이 '2002년부터' 같은 표현에서 자동 추출하므로 직접 채우지 말 것"
    )
    backtest_end_date: Optional[str] = Field(
        default=None,
        description="명시적 백테스트 종료일(YYYY-MM-DD). 시스템이 '2005년까지' 같은 표현에서 자동 추출하므로 직접 채우지 말 것"
    )
    initial_capital: float = Field(
        default=10_000_000.0,
        description="초기 자본금(원). 언급 없으면 10000000 (1천만원)"
    )
    execution_timing: Literal["next_open", "current_close"] = Field(
        default="next_open",
        description="체결 시점. '다음날 시가'=next_open, '당일 종가'=current_close. 언급 없으면 next_open"
    )
    fee_rate: float = Field(
        default=0.015,
        description="수수료율(%). 예: '수수료 0.1%'=0.1. 언급 없으면 0.015"
    )
    slippage_rate: float = Field(
        default=0.05,
        description="슬리피지율(%). 예: '슬리피지 0.1%'=0.1. 언급 없으면 0.05"
    )


# ─── Diff 스키마 (수정 모드용) ────────────────────────────────────────────────

class ParsedStrategyDiff(BaseModel):
    """수정된 필드만 포함. null이면 이전 값 그대로 유지."""

    _normalize_ratio_sign = field_validator(*_RATIO_SIGN_FIELDS)(_abs_ratio)
    description: Optional[str] = None
    universe: Optional[List[Literal["KOSPI", "KOSDAQ", "KOSPI200", "ETF"]]] = None
    sector: Optional[Union[str, List[str]]] = Field(
        default=None,
        description=(
            "업종/섹터 제한 변경. '반도체 관련주만', 'IT 업종으로' 등 언급 시 해당 섹터명. "
            "'~도 추가'처럼 기존 업종에 더하는 요청이면 기존 목록+새 업종 전체를 배열로 출력. "
            "지원 섹터: " + ", ".join(_CANONICAL_SECTORS_DOC) + ". 언급 없으면 null"
        ),
    )

    @field_validator("sector")
    @classmethod
    def _normalize_sector_name(cls, v):
        return normalize_sector_value(v)

    fundamental_filters: Optional[List[FundamentalFilter]] = None
    entry_signals: Optional[List[TechnicalSignal]] = None
    exit_signals: Optional[List[TechnicalSignal]] = None
    ranking_metric: Optional[Literal["return"]] = None
    ranking_lookback_days: Optional[int] = None
    max_positions: Optional[int] = Field(default=None, ge=1, le=100)
    hold_period_days: Optional[int] = None
    rebalancing_period: Optional[Literal["none", "daily", "weekly", "monthly", "bimonthly", "quarterly", "yearly"]] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    max_mdd_limit_pct: Optional[float] = None
    backtest_period: Optional[Literal["1y", "3y", "5y", "full"]] = None
    backtest_start_date: Optional[str] = None
    backtest_end_date: Optional[str] = None
    initial_capital: Optional[float] = None
    execution_timing: Optional[Literal["next_open", "current_close"]] = None
    fee_rate: Optional[float] = None
    slippage_rate: Optional[float] = None


_MODEL_TRAILING_TOKENS = (
    "<|im_end|>",
    "<|im_start|>",
    "<|endoftext|>",
    "</s>",
)


MODIFY_PROMPT = """현재 전략 JSON이 주어집니다. 사용자 수정 요청을 적용해 변경된 필드만 JSON으로 출력하세요.
변경하지 않는 필드는 반드시 null로 출력하세요. 수정 요청에 없는 내용은 절대 바꾸지 마세요.
사용자 입력에는 오타·맞춤법 오류가 섞일 수 있습니다. 글자 그대로가 아니라 의도로 해석하세요
(예: 숫자 뒤 '게'는 종목 수 단위 '개'의 오타 — "종목은 5게"="종목 5개"=max_positions 5).
이 JSON이 수정 요청의 최종 의미 판단으로 사용됩니다. 확실히 요청된 변경만 출력하고,
의미가 불확실한 필드는 추측하지 말고 null로 유지하세요.

## 금액 단위 변환 (initial_capital)
- '1억' → 100000000.0
- '5천만원' → 50000000.0
- '2억 5천만' → 250000000.0
- '1000만원' → 10000000.0

## 업종/섹터 (sector)
- '반도체 관련주만', 'IT 업종으로 바꿔줘' 같은 업종·테마 제한 요청 → sector에 업종명
- 지원 업종: """ + sectors_for_llm_prompt() + """. 목록 밖 테마는 속하는 업종으로 매핑(예: '원자로'→'에너지/원자력'), 연결이 어려우면 null
- 업종만 바꾸는 요청에서 universe(시장)는 null로 유지하세요

## ETF 유니버스
- 'ETF로 바꿔줘', 'ETF 대상으로' 같은 요청 → universe=["ETF"] 단독(주식 시장과 혼합 금지)
- ETF는 여러 기업을 묶은 상품이라 기업 재무지표(PER·PBR·ROE 등) 조건을 만들 수 없습니다 —
  ETF 전략에 fundamental_filters를 추가하지 마세요(기술 지표는 사용 가능)

## 예시
현재 전략: {"max_positions": 20, "initial_capital": 10000000.0, ...}
수정 요청: "종목을 10개로 줄여줘"
출력: {"description": null, "universe": null, "sector": null, "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": 10, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "초기자금 1억으로 바꿔줘"
출력: {"description": null, "universe": null, "sector": null, "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": 100000000.0, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "트레일링 스탑 15%로 설정해줘"
출력: {"description": null, "universe": null, "sector": null, "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": 15.0, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "KOSPI200 (기본값, 빠름) 그대로 진행" 또는 "KOSPI200으로 진행"
출력: {"description": null, "universe": ["KOSPI200"], "sector": null, "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "코스닥으로 바꿔줘" 또는 "KOSDAQ (코스닥 ~1,781종목)"
출력: {"description": null, "universe": ["KOSDAQ"], "sector": null, "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "전체 시장 (KOSPI+KOSDAQ ~2,619종목)" 또는 "전체 시장으로"
출력: {"description": null, "universe": ["KOSPI", "KOSDAQ"], "sector": null, "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "반도체 섹터 종목만 테스트 해줘"
출력: {"description": null, "universe": null, "sector": "반도체", "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}
"""


# ─── 시스템 프롬프트 ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 한국 주식 퀀트 투자 전략을 JSON으로 변환하는 전문가입니다.
사용자 입력에는 오타·맞춤법 오류가 섞일 수 있습니다. 글자 그대로가 아니라 의도로 해석하세요
(예: 숫자 뒤 '게'는 종목 수 단위 '개'의 오타 — "5게"="5개").

## 변환 규칙

### 재무 필터 (fundamental_filters)
- PBR 1 이하 → {"metric": "pbr", "operator": "<=", "value": 1.0}
- PER 7 미만 → {"metric": "per", "operator": "<", "value": 7.0}
- ROE 15% 이상 → {"metric": "roe_or_gpa", "operator": ">=", "value": 15.0}
- 부채비율 100% 이하 → {"metric": "debt_ratio", "operator": "<=", "value": 100.0}
- ROA 5% 이상 → {"metric": "roa", "operator": ">=", "value": 5.0}
- PSR 2 이하 → {"metric": "psr", "operator": "<=", "value": 2.0}
- EV/EBITDA 8 이하 → {"metric": "ev_ebitda", "operator": "<=", "value": 8.0}
- 배당수익률 3% 이상 / 고배당주 → {"metric": "dividend_yield", "operator": ">=", "value": 3.0}
- 배당성향 30% 이상 → {"metric": "payout_rate", "operator": ">=", "value": 30.0}
- 배당성장률 10% 이상 / 배당을 꾸준히 늘리는 → {"metric": "dividend_growth", "operator": ">=", "value": 10.0}
- 유동비율 150% 이상 → {"metric": "current_ratio", "operator": ">=", "value": 150.0}
- 매출액증가율 20% 이상 → {"metric": "revenue_growth", "operator": ">=", "value": 20.0}
- 영업이익증가율 10% 이상 → {"metric": "operating_income_growth", "operator": ">=", "value": 10.0}
- 순이익률 10% 이상 → {"metric": "net_margin", "operator": ">=", "value": 10.0}
- 영업이익률 15% 이상 → {"metric": "operating_margin", "operator": ">=", "value": 15.0}
- 시가총액 1000억 이상 → {"metric": "market_cap", "operator": ">=", "value": 1000.0}
- '이하'='<=', '미만'='<', '이상'='>=', '초과'='>'

### 기술적 신호 (entry_signals / exit_signals)
- 골든크로스 → indicator: "ma_crossover", signal_type: "buy", short_period: 5, long_period: 20
- 데드크로스 → indicator: "ma_crossover", signal_type: "sell", short_period: 5, long_period: 20
- RSI 30 이하 → indicator: "rsi", signal_type: "buy", period: 14, operator: "<=", value: 30
- RSI 70 이상 → indicator: "rsi", signal_type: "sell", period: 14, operator: ">=", value: 70
- 'RSI가 30 아래로 내려갔다가 다시 올라오는' / 'RSI 과매도 후 반등' 같은 반등 표현 → RSI 매수에 mode "rebound" 추가: operator "<=", value 30, mode "rebound" (단순 'RSI 30 이하 매수'는 mode 없음)
- 매도 동사는 '매도/청산'뿐 아니라 '팔고/팔아/팔면' 같은 구어체도 동일하게 처리
- MACD 크로스 → indicator: "macd", signal_type: "buy", mode: "crossover"
- 볼린저밴드 하단 → indicator: "bollinger_bands", signal_type: "buy"
- 볼린저밴드 상단 → indicator: "bollinger_bands", signal_type: "sell"
- 스토캐스틱 과매도 매수 → indicator: "stochastic", signal_type: "buy", operator: "<=", value: 20
- CCI -100 이하 매수 → indicator: "cci", signal_type: "buy", period: 14, operator: "<=", value: -100
- Williams %R -80 이하 매수 / -20 이상 매도 → indicator: "williams_r", period: 14 (범위 -100~0, 과매도=-80/과매수=-20)
- MFI(자금흐름지표) 20 이하 매수 / 80 이상 매도 → indicator: "mfi", period: 14 (0~100, RSI와 동형)
- ROC/모멘텀이 플러스(0 초과) 매수 / 마이너스 매도 → indicator: "roc", period: 12, operator ">"/"<", value: 0
- 52주 신고가 돌파 → indicator: "breakout", signal_type: "buy", lookback_period: 252
- '박스권을 위로 돌파' / 'N일 고점 돌파' / '20일 고점을 넘기면 매수' → indicator: "breakout", signal_type: "buy", lookback_period: N (기간 없이 '박스권'만 언급 시 20)
- '다시 박스 안으로 내려오면 매도' / 'N일 저점 이탈 시 매도' → indicator: "breakout", signal_type: "sell"
- AI 상승 예측 매수 / AI 모델 매수 → indicator: "ai_model", signal_type: "buy", threshold: 70
- AI 하락 예측 매도 / AI 모델 매도 → indicator: "ai_drop_model", signal_type: "sell", threshold: 70
- AI 모델이 X% 이상 확률로 상승 예측 → indicator: "ai_model", signal_type: "buy", threshold: X

### 보유기간 / 리밸런싱
- '1년 보유' → hold_period_days: 252, rebalancing_period: "yearly"
- '6개월 보유' → hold_period_days: 126, rebalancing_period: "none"
- '매주/주간 리밸런싱' → rebalancing_period: "weekly"
- '매월 리밸런싱' → rebalancing_period: "monthly"
- '격월/두 달에 한 번/2개월마다 리밸런싱(점검)' → rebalancing_period: "bimonthly"
- 기술적 청산 없이 기간 보유면 exit_signals: []

### 종목 수
- '10개', '10종목', '상위 10개' → max_positions: 10

### 초기자금 (initial_capital, 단위: 원)
- '1억' → 100000000.0
- '5천만원', '5000만' → 50000000.0
- '2억 5천만' → 250000000.0
- '1000만원' → 10000000.0
- 언급 없으면 → 10000000.0 (1천만원)

### 트레일링 스탑 (trailing_stop_pct)
- '최고가 대비 15% 하락 시 청산' → trailing_stop_pct: 15.0
- '트레일링 스탑 10%' → trailing_stop_pct: 10.0
- 언급 없으면 → null

### 포트폴리오 MDD 한도 (max_mdd_limit_pct)
- 'MDD 20% 초과 시 전량 청산' → max_mdd_limit_pct: 20.0
- '낙폭 30% 이상이면 중단' → max_mdd_limit_pct: 30.0
- 언급 없으면 → null

### 체결 시점 (execution_timing)
- '당일 종가 체결', '당일 종가로 매매' → execution_timing: "current_close"
- '다음날 시가', '익일 시가 체결' → execution_timing: "next_open"
- 언급 없으면 → "next_open"

### 수수료/슬리피지
- '수수료 0.1%' → fee_rate: 0.1
- '슬리피지 0.05%' → slippage_rate: 0.05
- 언급 없으면 → fee_rate: 0.015, slippage_rate: 0.05

### 업종/섹터 (sector)
- '반도체 관련주' → sector: "반도체"
- '2차전지 업종' → sector: "이차전지"
- '제약주', '바이오 관련주' → sector: "바이오/제약"
- 여러 업종을 함께 제한하면 배열: '반도체와 자동차 업종' → sector: ["반도체", "자동차"]
- 수정 요청에서 '~도 추가'는 기존 sector 목록에 새 업종을 더한 전체 목록을 배열로 출력
  (예: 현재 sector "반도체" + '로봇 섹터도 추가해줘' → sector: ["반도체", "로봇"])
- 지원 섹터명 예: 반도체, 이차전지, 바이오/제약, 게임, 자동차, 은행/금융지주, 화학, 건설 등
- 섹터 언급이 있고 시장 언급이 없으면 → universe: ["KOSPI", "KOSDAQ"] (업종 전체)
- 언급 없으면 → null

### ETF 유니버스 (universe: ["ETF"])
- 'ETF', 'ETN', '상장지수펀드' 또는 ETF 상품명(KODEX 200, TIGER 미국S&P500 등) 대상 →
  universe: ["ETF"] 단독 (주식 시장과 혼합 금지 — '코스피 ETF'도 ["ETF"])
- ETF는 여러 기업을 묶은 상품이라 기업 재무지표(PER·PBR·ROE·부채비율·배당성향 등)를 쓸 수
  없습니다 → ETF 전략에 fundamental_filters를 만들지 마세요. 기술 지표는 사용 가능
- ETF 전략에서 sector는 null (테마는 시스템이 상품명에서 자동 추출)

## 예시

입력: "AI 모델이 상승 예측한 종목에 매수, AI 하락 예측 시 매도, 최대 15종목, 손절 10%"
출력:
{
  "description": "AI 모델이 상승 예측한 종목에 매수, AI 하락 예측 시 매도, 최대 15종목, 손절 10%",
  "universe": ["KOSPI200"],
  "sector": null,
  "fundamental_filters": [],
  "entry_signals": [{"indicator": "ai_model", "signal_type": "buy", "threshold": 70}],
  "exit_signals": [{"indicator": "ai_drop_model", "signal_type": "sell", "threshold": 70}],
  "max_positions": 15,
  "hold_period_days": null,
  "rebalancing_period": "none",
  "stop_loss_pct": 10.0,
  "take_profit_pct": null,
  "trailing_stop_pct": null,
  "max_mdd_limit_pct": null,
  "backtest_period": "5y",
  "initial_capital": 10000000.0,
  "execution_timing": "next_open",
  "fee_rate": 0.015,
  "slippage_rate": 0.05
}

입력: "pbr 1이하 per 7이하 종목을 10개 사서 1년간 보유하는 전략"
출력:
{
  "description": "pbr 1이하 per 7이하 종목을 10개 사서 1년간 보유하는 전략",
  "universe": ["KOSPI200"],
  "sector": null,
  "fundamental_filters": [
    {"metric": "pbr", "operator": "<=", "value": 1.0},
    {"metric": "per", "operator": "<=", "value": 7.0}
  ],
  "entry_signals": [],
  "exit_signals": [],
  "max_positions": 10,
  "hold_period_days": 252,
  "rebalancing_period": "yearly",
  "stop_loss_pct": null,
  "take_profit_pct": null,
  "trailing_stop_pct": null,
  "max_mdd_limit_pct": null,
  "backtest_period": "5y",
  "initial_capital": 10000000.0,
  "execution_timing": "next_open",
  "fee_rate": 0.015,
  "slippage_rate": 0.05
}

입력: "KOSPI에서 PER 10 이하인 종목 중 RSI가 30 아래로 내려갔다가 다시 올라오는 종목만 매수. 8종목 제한, 수익이 15% 나면 팔고 손절은 -8%"
출력:
{
  "description": "KOSPI에서 PER 10 이하인 종목 중 RSI가 30 아래로 내려갔다가 다시 올라오는 종목만 매수. 8종목 제한, 수익이 15% 나면 팔고 손절은 -8%",
  "universe": ["KOSPI"],
  "fundamental_filters": [
    {"metric": "per", "operator": "<=", "value": 10.0}
  ],
  "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "period": 14, "operator": "<=", "value": 30, "mode": "rebound"}],
  "exit_signals": [],
  "max_positions": 8,
  "hold_period_days": null,
  "rebalancing_period": "none",
  "stop_loss_pct": 8.0,
  "take_profit_pct": 15.0,
  "trailing_stop_pct": null,
  "max_mdd_limit_pct": null,
  "backtest_period": "5y",
  "initial_capital": 10000000.0,
  "execution_timing": "next_open",
  "fee_rate": 0.015,
  "slippage_rate": 0.05
}
"""

COMPACT_SYSTEM_PROMPT = """한국 주식 전략 자연어를 ParsedStrategy JSON으로만 변환하세요.
출력은 JSON 객체 하나만 허용합니다. 설명, markdown, 주석을 쓰지 마세요.
오타·맞춤법 오류는 의도로 해석하세요(예: 숫자 뒤 '게'='개', 종목 수 단위).

기본값:
- universe: ["KOSPI200"], max_positions: 10, backtest_period: "5y"
- initial_capital: 10000000.0, execution_timing: "next_open"
- fee_rate: 0.015, slippage_rate: 0.05
- rebalancing_period: "none", 누락된 optional 필드는 null

매핑:
- '반도체 관련주'/'2차전지 업종'/'2차전지에 투자'처럼 업종·섹터·테마 언급 → sector. 시장 언급이 없으면 universe는 ["KOSPI", "KOSDAQ"]
- sector는 다음 지원 업종명 중 하나만(괄호는 분류 관례 설명 — 업종명만 출력): """ + sectors_for_llm_prompt() + """. 목록 밖 테마는 속하는 업종으로 매핑(예: '원자로'→'에너지/원자력', '전력설비'→'에너지/원자력'), 연결이 어려우면 null
- universe에는 시장 코드(KOSPI/KOSDAQ/KOSPI200)만 넣으세요. 업종·테마명을 universe에 넣으면 안 됩니다(sector 필드에)
- description은 필수입니다. 사용자 원문을 그대로 복사하세요
- PBR/PER/ROE/부채비율/시가총액/거래대금 → fundamental_filters
- 이하/미만/이상/초과 → <=/< />=/ >
- 골든크로스/데드크로스 → ma_crossover buy/sell, 기본 5/20
- RSI 30 이하/70 이상 → rsi buy/sell, 기본 period 14
- 'RSI가 30 아래로 내려갔다가 다시 올라오는' / 'RSI 과매도 반등' → rsi buy + mode "rebound" (operator "<=", value 30)
- 매도 동사: '매도/청산' 외 '팔고/팔아/팔면' 구어체도 동일 처리
- MACD, 볼린저밴드, 신고가 돌파, 거래량 급증, AI 상승/하락 예측을 해당 indicator로 변환
- 박스권/N일 고점 위로 돌파 → breakout buy (기간 없으면 lookback 20), 다시 박스 안/저점 아래로 이탈 시 매도 → breakout sell
- 1년/6개월/3개월/1개월 보유 → 252/126/63/21 거래일
- 매주/매월/격월/분기/매년 리밸런싱 → weekly/monthly/bimonthly/quarterly/yearly
- 손절/익절/트레일링 스탑/MDD 한도를 % 숫자로 변환
- 1억/5천만원/1000만원 등 자본금은 원 단위 숫자로 변환

반드시 ParsedStrategy 전체 필드를 포함하세요."""


# ─── 파서 클래스 ──────────────────────────────────────────────────────────────

class NLStrategyParser:
    """
    자연어 전략을 ParsedStrategy로 변환.

    백엔드 선택:
    - backend="ollama" : instructor + Ollama HTTP API (범용, 설정 쉬움)
    - backend="mlx"    : outlines + mlx-lm (M1/M2/M3 Mac 전용, 2~3x 빠름)

    라우팅 전략:
    - parse()             → 7B (빠름, 단순 파싱에 충분)
    - parse_modification() → 7B (파싱과 동일 모델, 32B는 summarize에서 사용)
    """

    def __init__(
        self,
        backend: Literal["ollama", "mlx"] = "ollama",
        # 모델은 크기에 종속되지 않는다. 환경변수로 다른 모델로 교체해
        # A/B 비교할 수 있다(코드 수정 없이): NL_MLX_MODEL / NL_OLLAMA_MODEL.
        # 환경변수는 import 시점이 아니라 인스턴스 생성 시점에 읽어, 테스트가 격리할 수 있게 한다.
        mlx_model: Optional[str] = None,
        model_32b: str = "mlx-community/Qwen3.5-4B-4bit",
        ollama_model: Optional[str] = None,
        ollama_model_32b: str = "qwen3:8b",
        max_retries: int = 3,
    ):
        self.backend = backend
        self.mlx_model = mlx_model or os.environ.get("NL_MLX_MODEL", "mlx-community/Qwen3.5-4B-4bit")
        self.model_32b = model_32b
        self.ollama_model = ollama_model or os.environ.get("NL_OLLAMA_MODEL", "qwen3:8b")
        self.ollama_model_32b = ollama_model_32b
        self.max_retries = max_retries
        # MLX 단일 추론 게이트. main이 PriorityInferenceLock 컨텍스트 팩토리를 주입하면
        # LLM 구조화 생성(_parse_mlx/_modify_mlx)만 직렬화된다(규칙 기반 경로는 락 불필요).
        # None이면 게이트 없이 동작한다(ollama·테스트). chat/stream_chat은 호출부(코치)가
        # 자체 우선순위로 락을 잡으므로 여기서 감싸지 않는다(이중 획득 데드락 방지).
        self.inference_gate = None
        self._client = None
        # MLX: 기본 모델(parse + modification + coach용, 서버 시작 시 로드), 32B 슬롯(미사용)
        self._generator = None
        self._diff_generator = None
        self._generator_32b = None
        self._diff_generator_32b = None
        self._mlx_model = None
        self._tokenizer = None
        self._mlx_model_32b = None
        self._tokenizer_32b = None

    def _model_log_label(self, model_name: str) -> str:
        """로그에 표시할 사람이 읽기 쉬운 모델 라벨을 만든다."""
        model_id = model_name.split("/")[-1]
        normalized = model_id.replace("-OptiQ-4bit", "").replace("-Instruct-4bit", "").replace("-4bit", "")
        return normalized or model_name

    # ── Lazy init ────────────────────────────────────────────────────────────

    def _init_ollama(self):
        """instructor + Ollama 초기화 (최초 호출 시)"""
        if self._client is not None:
            return
        try:
            import instructor
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("pip install instructor openai 필요")

        self._client = instructor.from_openai(
            OpenAI(
                base_url=f"{OLLAMA_BASE_URL}/v1",
                api_key="ollama",
                default_headers=ollama_auth_headers(),  # Modal proxy-auth (배포 시)
            ),
            mode=instructor.Mode.JSON,
        )

    def _init_mlx(self):
        """기본 MLX 모델 초기화 (4B, parse + modification용, 서버 시작 시 로드)"""
        if self._generator is not None:
            return
        try:
            import outlines
            import outlines.models as models
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install outlines mlx-lm 필요")

        log_label = self._model_log_label(self.mlx_model)
        print(f"[NLParser] {log_label} 모델 로딩: {self.mlx_model} ...", flush=True)
        mlx_model, tokenizer = mlx_lm.load(self.mlx_model)
        self._mlx_model = mlx_model
        self._tokenizer = tokenizer
        self._outlines_model = models.from_mlxlm(mlx_model, tokenizer)
        self._generator = outlines.Generator(self._outlines_model, ParsedStrategy)
        self._diff_generator = outlines.Generator(self._outlines_model, ParsedStrategyDiff)
        print(f"[NLParser] {log_label} 모델 로딩 완료", flush=True)

    def _init_mlx_32b(self):
        """추가 MLX 모델 초기화 (하위 호환용 lazy 로드)"""
        if self._generator_32b is not None:
            return
        try:
            import outlines
            import outlines.models as models
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install outlines mlx-lm 필요")

        log_label = self._model_log_label(self.model_32b)
        print(f"[NLParser] {log_label} 모델 로딩: {self.model_32b} ...", flush=True)
        mlx_model, tokenizer = mlx_lm.load(self.model_32b)
        self._mlx_model_32b = mlx_model
        self._tokenizer_32b = tokenizer
        self._outlines_model_32b = models.from_mlxlm(mlx_model, tokenizer)
        self._generator_32b = outlines.Generator(self._outlines_model_32b, ParsedStrategy)
        self._diff_generator_32b = outlines.Generator(self._outlines_model_32b, ParsedStrategyDiff)
        print(f"[NLParser] {log_label} 모델 로딩 완료", flush=True)

    # ── 파싱 ─────────────────────────────────────────────────────────────────

    def parse_rule_based(self, user_input: str) -> Optional[ParsedStrategy]:
        """LLM 없이 규칙 기반으로만 파싱한다.

        슬롯이 충분하면 ParsedStrategy를, 모호하면 None을 반환한다. 모델·추론 락이
        전혀 필요 없으므로, 호출 측이 코치 LLM 생성과 무관하게 즉시 결과를 받을 수 있다.
        None이면 호출 측이 LLM 폴백(parse)을 결정한다."""
        return _parse_rule_based_strategy(user_input)

    def _consult_rule_parse_guard(self, user_input: str, parsed: ParsedStrategy) -> bool:
        """LLM judge로 룰 파싱 수락 여부를 재확인한다(True=수락, False=LLM 폴백).

        opt-in(NL_RULE_GUARD_LLM)이고, 룰 파스가 원문을 다 설명 못 한 듯한 잔여가 있을
        때만('애매한 경우에만') 호출한다. LLM 오류·비활성 시에는 보수적으로 수락(True)해
        기존 빠른 경로를 깨지 않는다 — 룰 파스는 이미 결정론 게이트(미지원 개념·red-flag·
        완결성)를 통과했기 때문이다."""
        flag = os.environ.get("NL_RULE_GUARD_LLM", "").strip().lower()
        if flag not in ("1", "true", "yes", "on"):
            return True
        if len(_rule_parse_unexplained(user_input)) < _RULE_GUARD_AMBIGUITY_MIN_CHARS:
            return True
        try:
            raw = self.chat(
                RULE_PARSE_GUARD_PROMPT,
                _build_guard_user_message(user_input, parsed),
                max_tokens=256,
                temperature=0.0,
            )
            decision = _extract_guard_decision(raw)
        except Exception as exc:  # noqa: BLE001 — LLM 오류는 빠른 경로를 깨지 않는다
            logger.warning("rule parse guard LLM failed, accepting rule parse | err=%r", exc)
            return True
        logger.info("rule parse guard verdict=%s | input=%r", decision, user_input[:80])
        return decision == "accept_rule"

    def parse(self, user_input: str, on_stage=None, on_validation=None,
              defer_validation: bool = False) -> ParsedStrategy:
        """자연어 입력 → ParsedStrategy (규칙 기반 우선, 모호하면 4B 사용)

        on_stage: LLM 폴백으로 넘어가기 직전 호출되는 콜백(stage 문자열 전달).
        진행 상황 스트리밍에서 'parsing'→'thinking' 전환을 알리는 용도.
        on_validation: 룰 파싱 성공 시 LLM 검증 리포트(dict)를 전달받는 콜백.
        defer_validation: True면 검증 LLM을 여기서 돌리지 않고 즉시 룰 파스를 반환한다.
            호출 측(SSE 스트림)이 결과를 먼저 내보낸 뒤 후행 검증을 직접 실행하는 용도 —
            on_validation에 {"pending": True} 리포트를 전달해 검증 필요를 알린다.
        """
        parsed_by_rules = _parse_rule_based_strategy(user_input)
        if parsed_by_rules is not None and self._consult_rule_parse_guard(user_input, parsed_by_rules):
            # 룰 파싱이 원문의 모든 어휘를 설명한 '확신 파싱'이면 LLM 검증을 건너뛴다(규칙만으로
            # 즉답). 설명 못 한 잔여가 남은 '애매한' 파싱만 LLM으로 검증·교정한다 — 흔한 명확한
            # 입력에서 매번 붙던 수 초~수십 초의 검증 지연을 없앤다.
            unexplained = _rule_parse_unexplained(user_input)
            if not unexplained:
                return parsed_by_rules
            # 검증 발화 원인(잔여 어휘)을 남긴다 — 빈출 무해 토큰을 _RULE_GUARD_KNOWN_VOCAB에
            # 보강해 검증 호출 자체를 줄이는 운영 루프의 입력 데이터.
            logger.info(
                "parse validation triggered | residual=%r | input=%r",
                unexplained, user_input[:120],
            )
            if defer_validation:
                if on_validation is not None:
                    on_validation({"pending": True})
                return parsed_by_rules
            # LLM 미가용 시 graceful degrade(원본 그대로) — 빠른 경로를 막지 않는다.
            if on_stage is not None:
                on_stage("validating")
            from engine.parse_validator import validate_parse
            validated, report = validate_parse(self, user_input, parsed_by_rules)
            if on_validation is not None:
                on_validation(report)
            return validated

        if on_stage is not None:
            on_stage("thinking")
        try:
            if self.backend == "mlx":
                parsed = self._parse_mlx(user_input)
            else:
                parsed = self._parse_ollama(user_input)
        except ValidationError:
            # LLM이 JSON은 냈지만 스키마 위반(필수 필드 누락·잘못된 enum·null 배열 등).
            # 복잡한 서술형 전략에서 흔하다 → 500 대신 결정론 폴백으로 graceful 전환.
            parsed = _build_fallback_strategy(user_input)
        except ValueError as exc:
            if "JSON object" not in str(exc):
                raise
            parsed = _build_fallback_strategy(user_input)
        parsed = _apply_prompt_overrides(parsed, user_input)
        # LLM이 sector는 냈지만 universe를 스키마 기본(KOSPI200)으로 둔 경우, '시장 언급
        # 없는 섹터 전략 기본=양시장' 규칙(FR-STR-066 ③)을 강제한다 — 결정적 큐가 없는
        # 표현("2차전지에 투자")은 _apply_prompt_overrides의 섹터 추출이 못 잡아 여기가
        # 유일한 보정 지점이다. 수정(modify) 경로는 기존 universe 보존을 위해 제외.
        if (parsed.sector is not None and parsed.universe == ["KOSPI200"]
                and _extract_explicit_universe(user_input) is None):
            parsed = parsed.model_copy(update={"universe": ["KOSPI", "KOSDAQ"]})
        return parsed

    def parse_modification(self, user_input: str, previous: dict, on_stage=None) -> ParsedStrategy:
        """수정 요청: 규칙 기반 우선, 못 풀면 LLM으로 diff 추출 후 previous와 병합.

        단순 필드 수정(손절/익절/종목수/유니버스 등)은 결정론 fast-path가 LLM 없이
        즉답한다(초기 parse와 동일한 하이브리드 구조). 복합·모호한 수정만 LLM으로 위임.
        on_stage: LLM diff 추출로 넘어가기 직전 호출되는 콜백(stage 문자열 전달).
        """
        rule_based = _modify_rule_based(user_input, previous)
        if rule_based is not None:
            return rule_based

        if on_stage is not None:
            on_stage("thinking")
        try:
            if self.backend == "mlx":
                diff = self._modify_mlx(user_input, previous)
            else:
                diff = self._modify_ollama(user_input, previous)
        except ValidationError:
            # Reject an invalid model decision without replacing it with a deterministic interpretation.
            return ParsedStrategy.model_validate(previous)

        # diff의 non-null 필드만 previous에 덮어씀
        merged = {**previous}
        for field, val in diff.model_dump().items():
            if val is not None:
                merged[field] = val

        # 삭제 의도 명시 처리: LLM diff는 null="변경없음"으로 표현하므로 별도 감지
        compact = _compact(user_input)
        if any(kw in compact for kw in _DELETE_TERMS):
            if any(kw in compact for kw in ["손절", "stoploss", "스탑로스"]):
                merged["stop_loss_pct"] = None
            if any(kw in compact for kw in ["익절", "takeprofit", "익절률"]):
                merged["take_profit_pct"] = None
            if any(kw in compact for kw in ["트레일링", "trailingstop"]):
                merged["trailing_stop_pct"] = None
            # 리밸런싱은 '끔'을 null이 아니라 enum "none"으로 표현하므로, LLM이 null을
            # 내도(=변경없음으로 해석돼 무시) 삭제 의도를 별도로 none으로 보정한다.
            if any(kw in compact for kw in _MODIFY_REBALANCE_CUES):
                merged["rebalancing_period"] = "none"
            # 보유기간·MDD 한도도 '해제'가 null인데 병합이 null을 무시하므로 동일하게 보정한다.
            if any(kw in compact for kw in _MODIFY_HOLD_CUES):
                merged["hold_period_days"] = None
            if any(kw in compact for kw in _MODIFY_MDD_CUES):
                merged["max_mdd_limit_pct"] = None
        # 필터 병합 보정: LLM diff는 fundamental_filters를 통째로 대체하는데, few-shot
        # 예시가 새 필터만 출력하는 경향이 있어 추가/변경 발화에서 언급 안 된 기존 필터가
        # 소실된다(스크린샷 회귀: '영업이익률 추가' 후 ROE·부채비율 증발). 제거 의도가
        # 없으면 fast-path와 동일한 병합 의미론(_merge_fundamental_filters: 같은 지표
        # 갱신·새 지표 추가·기존 보존)을 적용한다. 제거/해제 발화는 LLM 출력(빠진 항목=
        # 삭제 의도일 수 있는 전체 목록)을 존중한다.
        if diff.fundamental_filters is not None and not _REMOVE_INTENT_RE.search(compact):
            existing_filters = [
                FundamentalFilter(**f) for f in (previous.get("fundamental_filters") or [])
            ]
            merged["fundamental_filters"] = [
                f.model_dump()
                for f in _merge_fundamental_filters(existing_filters, diff.fundamental_filters)
            ]
        # 섹터 변경(추가 합집합/교체/개별 삭제/전체 해제)은 결정적 판정이 LLM diff에 우선한다
        # (FR-STR-066 ⑥/⑦) — LLM이 "~도 추가"를 교체로 오독하거나 삭제 발화를 재추출로
        # 되살리는 사고 방지(_apply_prompt_overrides 보정과 동형). 결정적 판정이 침묵하면
        # LLM diff 값을 존중한다. universe는 수정 경로 원칙대로 보존한다(③ 제외).
        sector_changed, sector_value = _sector_change_from_utterance(
            user_input, previous.get("sector")
        )
        if sector_changed:
            merged["sector"] = sector_value

        # The LLM diff is authoritative; post-processing only enforces schema safety.
        result = ParsedStrategy.model_validate(merged)

        # 성공한 수정 요청을 학습 코퍼스에 기록 (best-effort, 실패해도 무시)
        try:
            from engine.modify_rag import record_example as _record_modify_example
            _record_modify_example(user_input, diff.model_dump())
        except Exception:
            pass

        return result

    def _modify_mlx(self, user_input: str, previous: dict) -> ParsedStrategyDiff:
        self._init_mlx()
        prompt = (
            f"{MODIFY_PROMPT}\n\n"
            f"현재 전략:\n{json.dumps(previous, ensure_ascii=False)}\n\n"
            f"수정 요청: \"{user_input}\"\n출력:"
        )
        with self._inference_gate():
            result = self._diff_generator(prompt, max_tokens=1024)
        if isinstance(result, str):
            return _parse_model_json_response(result, ParsedStrategyDiff)
        return result

    def _structured_ollama(
        self,
        system_prompt: str,
        user_message: str,
        model_cls: type[BaseModel],
    ) -> BaseModel:
        """Ollama 네이티브 /api/chat로 구조화 JSON을 생성한다.

        OpenAI 호환(/v1) 엔드포인트는 options.num_ctx를 무시하므로, 긴 수정 프롬프트
        (MODIFY_PROMPT ~4KB + 현재 전략 JSON)가 기본 num_ctx(4096)를 넘으면
        "exceeds the available context size" 400을 던진다(프로덕션 실측). 네이티브
        엔드포인트는 코치 경로(_chat_ollama)와 동일하게 options.num_ctx를 받으므로
        16384로 올린다. format="json"으로 JSON 출력을 강제하되, JSON 스키마 제약
        디코딩은 이 모델에서 출력을 조기 절단시키므로 쓰지 않는다(format="json"만).
        """
        import urllib.request

        body = json.dumps({
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "think": False,
            "format": "json",
            # greedy/결정론(temperature 0) — MLX(outlines) 경로와 동일.
            "options": {
                "temperature": 0,
                "num_ctx": _OLLAMA_NUM_CTX,
                "num_predict": 1024,
            },
        }).encode()
        # Modal 콜드스타트 프록시가 POST body를 유실시키므로, 본문 없는 GET으로 먼저 깨운다.
        _ollama_ensure_warm()
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json", **ollama_auth_headers()},
            method="POST",
        )
        with _ollama_open_with_retry(req, timeout=120) as resp:
            data = json.loads(resp.read())
        content = (data.get("message") or {}).get("content", "")
        return _parse_model_json_response(content, model_cls)

    def _modify_ollama(self, user_input: str, previous: dict) -> ParsedStrategyDiff:
        from engine.modify_rag import build_dynamic_modify_prompt

        # 사용자 요청과 유사한 예시만 검색해서 프롬프트 생성
        dynamic_prompt = build_dynamic_modify_prompt(user_input, k=2)
        dynamic_prompt += (
            "\n사용자 입력에는 오타·맞춤법 오류가 섞일 수 있으므로 글자 그대로가 아니라 "
            "문맥상 의도로 해석하세요. 이 JSON이 최종 의미 판단으로 사용되므로 확실히 요청된 "
            "변경만 출력하고, 의미가 불확실한 필드는 null로 유지하세요."
        )
        return self._structured_ollama(
            dynamic_prompt,
            f"현재 전략:\n{json.dumps(previous, ensure_ascii=False)}\n\n"
            f"수정 요청: \"{user_input}\"",
            ParsedStrategyDiff,
        )

    @staticmethod
    def _sampler_kwargs(temperature: float, top_p: float) -> dict:
        """temperature>0이면 샘플러를 만들어 generate에 넘길 kwargs를 반환한다.
        temperature<=0이면 빈 dict → 기존 greedy(deterministic) 동작 유지."""
        if temperature <= 0:
            return {}
        from mlx_lm.sample_utils import make_sampler

        return {"sampler": make_sampler(temp=temperature, top_p=top_p)}

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> str:
        """자유형식 텍스트 생성 — 코치/요약 등 비구조화 응답용.
        temperature>0이면 표현이 매번 달라지도록 샘플링한다(코치용).
        MLX를 쓸 수 없는 환경(리눅스 등)에서는 Ollama HTTP API로 폴백한다."""
        if self.backend != "mlx":
            return self._chat_ollama(system_prompt, user_message, max_tokens, temperature, top_p)
        self._init_mlx()
        try:
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install mlx-lm 필요")

        tokenizer = self._tokenizer
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        else:
            prompt = f"{system_prompt}\n\n{user_message}"

        return mlx_lm.generate(
            self._mlx_model,
            tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            verbose=False,
            **self._sampler_kwargs(temperature, top_p),
        ).strip()

    def stream_chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ):
        """토큰 단위 스트리밍 생성 — 각 yield마다 증분 델타를 반환.
        temperature>0이면 표현이 매번 달라지도록 샘플링한다(코치용).
        MLX를 쓸 수 없는 환경(리눅스 등)에서는 Ollama HTTP API로 폴백한다."""
        if self.backend != "mlx":
            yield from self._stream_chat_ollama(system_prompt, user_message, max_tokens, temperature, top_p)
            return
        self._init_mlx()
        try:
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install mlx-lm 필요")

        tokenizer = self._tokenizer
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        else:
            prompt = f"{system_prompt}\n\n{user_message}"

        for resp in mlx_lm.stream_generate(
            self._mlx_model,
            tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            **self._sampler_kwargs(temperature, top_p),
        ):
            # resp.text is the incremental delta for this step
            yield resp.text

    def _chat_ollama(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> str:
        """Ollama /api/chat 동기 호출 — chat()의 비-MLX 폴백."""
        import urllib.request

        # Qwen3 thinking 모델 thinking 우회: `think: false`를 쓴다.
        # (과거엔 assistant prefill `<think>\n\n</think>\n`을 마지막 메시지로 넣었으나, 현재
        #  Modal ollama가 받는 Qwen3.5 chat template이 마지막 메시지가 assistant면
        #  "No user query found in messages" Jinja 예외로 HTTP 400을 던진다. prefill은 폐기.)
        # `think: false`는 thinking 지원 모델(Qwen3.5)+현행 ollama에서 정상 동작한다(실측 2~3s,
        #  정상 content). think 파라미터를 아예 안 보내면 thinking이 토큰을 소진해 빈 응답이 된다.
        body = json.dumps({
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
                "num_ctx": _OLLAMA_NUM_CTX,
            },
        }).encode()
        # Modal 콜드스타트 프록시가 POST body를 유실시키므로, 본문 없는 GET으로 먼저 깨운다.
        _ollama_ensure_warm()
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json", **ollama_auth_headers()},
            method="POST",
        )
        with _ollama_open_with_retry(req, timeout=120) as resp:
            data = json.loads(resp.read())
        return (data.get("message") or {}).get("content", "").strip()

    def _stream_chat_ollama(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ):
        """Ollama /api/chat 스트리밍 호출 — stream_chat()의 비-MLX 폴백.
        각 yield는 증분 델타(MLX 경로와 동일)."""
        import urllib.request

        # 동기 경로와 동일하게 `think: false`로 thinking 우회(assistant prefill은 현행 Qwen3.5
        # chat template과 충돌해 400을 유발하므로 폐기 — _chat_ollama 주석 참고).
        body = json.dumps({
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": True,
            "think": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
                "num_ctx": _OLLAMA_NUM_CTX,
            },
        }).encode()
        # Modal 콜드스타트 프록시가 POST body를 유실시키므로, 본문 없는 GET으로 먼저 깨운다.
        _ollama_ensure_warm()
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json", **ollama_auth_headers()},
            method="POST",
        )
        with _ollama_open_with_retry(req, timeout=120) as resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                delta = (obj.get("message") or {}).get("content", "")
                if delta:
                    yield delta
                if obj.get("done"):
                    break

    def _inference_gate(self):
        """주입된 MLX 추론 게이트 컨텍스트를 반환한다(미주입 시 no-op)."""
        from contextlib import nullcontext

        return self.inference_gate() if self.inference_gate is not None else nullcontext()

    def _parse_mlx(self, user_input: str) -> ParsedStrategy:
        self._init_mlx()
        prompt = f"{COMPACT_SYSTEM_PROMPT}\n\n입력: \"{user_input}\"\n출력:"
        with self._inference_gate():
            result = self._generator(prompt, max_tokens=1024)
        if isinstance(result, str):
            return _parse_model_json_response(result, ParsedStrategy)
        return result

    def _parse_ollama(self, user_input: str) -> ParsedStrategy:
        return self._structured_ollama(COMPACT_SYSTEM_PROMPT, user_input, ParsedStrategy)


# ─── 누락 팩터 검증 ────────────────────────────────────────────────────────────

# 키워드 묶음: 사용자 프롬프트에서 해당 팩터 언급 여부를 판단
_KEYWORDS: dict[str, list[str]] = {
    "stop_loss":    ["손절", "stop loss", "스탑로스", "스탑 로스"],
    "take_profit":  ["익절", "take profit", "목표 수익", "익절률", "수익", "수익률"],
    "trailing_stop":["트레일링", "trailing stop", "최고가 대비"],
    "max_positions":["종목", "개", "포지션", "position"],
    "backtest_period": ["1년", "3년", "5년", "전체", "1y", "3y", "5y", "full", "백테스트 기간", "테스트 기간"],
    "initial_capital":  ["초기자금", "자본금", "원금", "자금", "억", "천만", "만원"],
    "universe": ["코스피", "코스피200", "kospi", "kospi200", "코스닥", "kosdaq", "전체 시장", "코스피+코스닥", "모든 종목", "유니버스", "universe"],
}

def _mentioned(prompt_lower: str, factor: str) -> bool:
    return any(kw in prompt_lower for kw in _KEYWORDS.get(factor, []))


# 사용자 입력의 흔한 오타·맞춤법 오류를 정규형으로 보정하는 표(소문자·공백 제거 후 적용).
# 띄어쓰기 오류는 공백 제거(compact)로 이미 흡수되므로 여기서는 '글자 단위 오타'만 다룬다.
# 보정은 detection을 깨뜨리는(=정규형과 글자가 어긋나 매칭이 안 되는) 오타만 골라 담는다.
# 정상 입력을 망가뜨리지 않도록, 각 오기는 올바른 표현의 부분 문자열이 아니어야 한다.
#   ※ 원문(description)은 절대 바꾸지 않는다 — 매칭용 compact 문자열에만 적용한다.
_TYPO_CORRECTIONS: tuple[tuple[str, str], ...] = (
    # 이동평균 크로스 — 'ㄴ' 누락/자모 오타로 '골든/데드'가 깨지는 경우.
    ("골드크로스", "골든크로스"),
    ("골튼크로스", "골든크로스"),
    ("골은크로스", "골든크로스"),
    ("데트크로스", "데드크로스"),
    ("데드크로쓰", "데드크로스"),
    ("데트크로쓰", "데드크로스"),
    # 지표명
    ("볼린져", "볼린저"),
    ("볼리저", "볼린저"),
    ("스토케스틱", "스토캐스틱"),
    ("스토하스틱", "스토캐스틱"),
    ("스토캐스택", "스토캐스틱"),
    ("스토캐스팀", "스토캐스틱"),
    ("모맨텀", "모멘텀"),
    ("모먼텀", "모멘텀"),
    # 리밸런싱 — 외래어 표기 흔들림.
    ("리벨런싱", "리밸런싱"),
    ("리발란싱", "리밸런싱"),
    ("리발랜싱", "리밸런싱"),
    ("리바란싱", "리밸런싱"),
    ("리벨런스", "리밸런스"),
    ("리발란스", "리밸런스"),
    # 리스크 관리
    ("트레이링", "트레일링"),
    ("트레일닝", "트레일링"),
    ("손졀", "손절"),
    ("익졀", "익절"),
    # 비용
    ("수수로", "수수료"),
    ("슬리패지", "슬리피지"),
    ("슬리피쥐", "슬리피지"),
    # 시장/유니버스
    ("코스탁", "코스닥"),
    ("코스닭", "코스닥"),
    ("코스피지수", "코스피"),
)


def _compact(user_input: str) -> str:
    """매칭용 정규화 문자열: 소문자화 → 공백 제거 → 흔한 오타 보정.

    파서의 모든 결정적 추출기가 공유하는 단일 정규화 지점이다. 띄어쓰기 오류는 공백
    제거로 흡수되고, 글자 단위 오타는 _TYPO_CORRECTIONS로 보정한다. 원문(description)은
    건드리지 않고 '매칭에 쓰는 compact'만 정규화하므로, 보정이 사용자에게 보이지 않는다.
    """
    compact = re.sub(r"\s+", "", user_input.lower())
    for wrong, right in _TYPO_CORRECTIONS:
        if wrong in compact:
            compact = compact.replace(wrong, right)
    # '5게'·'120게'처럼 숫자 뒤 '게'는 종목 수 단위 '개'의 흔한 오타다(게 자체는 단위가 아님).
    # 게로 시작하는 단어(게임·게시 등)는 보정하지 않도록 문장 끝/조사 앞에서만 바꾼다.
    compact = re.sub(r"(\d)게(?=$|[은는이가을를로도만씩요])", r"\1개", compact)
    return compact


def _extract_explicit_universe(user_input: str) -> Optional[List[str]]:
    compact = _compact(user_input)

    # ETF/ETN 등 상장 금융상품 언급은 상품 유니버스가 시장 언급보다 우선한다
    # ("코스피 ETF"도 ETF 유니버스 — 코스피는 상장 시장 서술일 뿐이다). 주식과 혼합하지 않는다.
    if ("etf" in compact or "etn" in compact or "이티에프" in compact
            or "상장지수펀드" in compact or "상장지수증권" in compact):
        return ["ETF"]

    mentions_kospi200 = "kospi200" in compact or "코스피200" in compact
    mentions_kosdaq = "kosdaq" in compact or "코스닥" in compact
    # 유가증권시장(거래소)은 KOSPI의 공식 명칭이므로 KOSPI로 매핑한다.
    mentions_kospi = not mentions_kospi200 and (
        "kospi" in compact or "코스피" in compact
        or "유가증권" in compact or "거래소시장" in compact
    )
    # "대형주"는 시가총액 기준 분류(KRX: 시총 상위 100위권)이므로 표준 대형주 지수인
    # KOSPI200으로 매핑한다. '대형우량주'·'블루칩'도 동일 분류로 본다. 단 코스닥 단독
    # 맥락에서는 적용하지 않는다 — 코스닥 대형주 전용 유니버스가 없어 KOSPI200으로
    # 매핑하면 시장 자체가 바뀌는 오매핑이 된다.
    mentions_large_cap = (
        "대형주" in compact or "대형" in compact
        or "우량대형" in compact or "블루칩" in compact or "bluechip" in compact
    )
    mentions_all_market = (
        "전체시장" in compact or
        "코스피+코스닥" in compact or
        "코스피와코스닥" in compact or
        "코스피코스닥" in compact or
        "kospi+kosdaq" in compact or
        "양시장" in compact or
        "국내전체" in compact or
        ("전종목" in compact and not mentions_kospi200) or
        ("모든시장" in compact and not mentions_kospi200) or
        ("모든종목" in compact and not mentions_kospi200)
    )

    if mentions_all_market or (mentions_kospi and mentions_kosdaq):
        return ["KOSPI", "KOSDAQ"]
    if mentions_kospi200:
        return ["KOSPI200"]
    if mentions_large_cap and not (mentions_kosdaq and not mentions_kospi):
        return ["KOSPI200"]
    if mentions_kospi:
        return ["KOSPI"]
    if mentions_kosdaq:
        return ["KOSDAQ"]
    return None


# ── 섹터/업종 추출 ────────────────────────────────────────────────────────────
# 정본 섹터명(universe_pit.CANONICAL_SECTORS)과 통칭 동의어를, 업종을 가리키는 게 분명한
# 큐('관련/테마/업종/섹터/종목/주식/주')가 바로 뒤따를 때만 결정적으로 잡는다.
# '반도체가 유망하니까' 같은 단독 언급은 잡지 않는다(긴 꼬리는 LLM의 sector 필드에 위임).
# '주(?!가)'는 '반도체주'는 잡되 '반도체 주가'의 '주가'는 배제한다.
# '중심/위주'는 "반도체 중심으로"·"반도체 위주로"처럼 범위를 좁히는 후치 표현(범주 신호).
# '분야'는 "바이오분야 전략"처럼 업종을 가리키는 명시적 후치 큐다 — 누락 시 수정 병합에서
# 이전 대화의 섹터가 그대로 유지되는 사고가 있었다(바이오 요청에 반도체 유지).
# '관련/테마'는 맨 형태로 본다('관련주'만 보면 "반도체 관련 전략"·"2차전지 테마" 어순을 놓침 —
# "로봇주 관련 전략"이 안 잡혀 전체 시장으로 백테스트되던 사고의 동일 계열).
# '섹션'은 '섹터'의 통용 오칭("반도체 섹션 종목만") — 누락 시 LLM 폴백으로 새던 사고.
_SECTOR_CUE = r"(?:관련|테마|업종|섹터|섹션|분야|종목|주식|중심|위주|주(?!가))"


def _sector_terms_longest_first() -> list[str]:
    from engine.universe_pit import _SECTOR_SYNONYMS, _sector_key

    terms = {_sector_key(s) for s in CANONICAL_SECTORS} | set(_SECTOR_SYNONYMS)
    return sorted(terms, key=len, reverse=True)


_SECTOR_TERM_RE = re.compile(
    "(" + "|".join(re.escape(t) for t in _sector_terms_longest_first()) + ")" + _SECTOR_CUE
)


def _extract_sector(user_input: str) -> Optional[str]:
    """'반도체 관련주'·'2차전지 업종' 같은 명시적 섹터 제한을 정본 섹터명으로 추출한다."""
    match = _SECTOR_TERM_RE.search(_compact(user_input))
    return normalize_sector(match.group(1)) if match else None


# 업종/섹터 제한 해제('업종 제한 빼줘', '섹터 필터 지워줘'). '업종/섹터'와 삭제어의 인접을
# 요구해 '업종에서 삼성전자 빼줘'(종목 제외 요청) 같은 오발동을 막는다. compact 기준.
_SECTOR_REMOVE_RE = re.compile(
    r"(?:업종|섹터)(?:제한|필터|조건)?[은는을를도]?(?:빼|제거|삭제|지워|없애)"
)

# ── 다중 섹터 수정 의미론(FR-STR-066 ⑦) ─────────────────────────────────────────
# sector는 정규형 None/str(단일)/list(복수)다. 수정 요청의 네 가지 의도를 결정적으로 판정한다:
#   추가("로봇 섹터도 추가해줘")=기존과 합집합 / 교체("기계 업종으로")=덮어쓰기 /
#   개별 삭제("반도체 업종은 빼줘")=그 항목만 제거 / 전체 해제("업종 제한 빼줘")=None.
# '도' 단독 조사는 짧은 용어(ai 등)의 오발동("ai도입")이 있어, 업종 명사 동반 또는
# 추가 동사 인접일 때만 추가 의도로 본다.
_SECTOR_NOUN = r"(?:섹터|섹션|업종|테마|분야|관련주?|종목|주식)"
_SECTOR_TERMS_ALT = "|".join(re.escape(t) for t in _sector_terms_longest_first())
_SECTOR_ADDITIVE_RE = re.compile(
    rf"(?P<term>{_SECTOR_TERMS_ALT})"
    rf"(?:{_SECTOR_NOUN}도|{_SECTOR_NOUN}?(?:도|[을를은는])?(?:추가|포함|넣|더해|같이|함께))"
)
_SECTOR_TARGET_REMOVE_RE = re.compile(
    rf"(?P<term>{_SECTOR_TERMS_ALT}){_SECTOR_NOUN}?[은는을를도]?(?:빼|제외|제거|삭제|지워|없애)"
)


def _sector_change_from_utterance(user_input: str, previous_sector) -> tuple[bool, object]:
    """수정 발화에서 섹터 변경을 결정적으로 판정한다 → (변경 여부, 새 정규형 값).

    삭제 판정이 추가/교체보다 우선한다 — "반도체 업종은 빼줘"는 _extract_sector도 매칭되므로
    순서를 바꾸면 삭제가 재주입으로 되살아난다(양 경로에 있던 선행 버그). 개별 삭제 대상이
    기존 목록에 없으면 결정적으로 판단하지 않는다(전체 해제로 오폭하지 않고 LLM/안내에 위임).
    """
    compact = _compact(user_input)
    prev = sector_value_as_list(previous_sector)

    target = _SECTOR_TARGET_REMOVE_RE.search(compact)
    if target:
        victim = normalize_sector(target.group("term"))
        if victim is not None and victim in prev:
            return True, normalize_sector_value([s for s in prev if s != victim])
        return False, None
    if _SECTOR_REMOVE_RE.search(compact):
        return True, None

    additive = _SECTOR_ADDITIVE_RE.search(compact)
    if additive:
        added = normalize_sector(additive.group("term"))
        if added is not None:
            return True, normalize_sector_value(prev + [added])

    new = _extract_sector(user_input)
    if new is None:
        return False, None
    return True, new


def _mentions_technical_exit_terms(compact_prompt: str) -> bool:
    technical_terms = [
        "rsi", "cci", "adx", "macd", "stochastic", "bollinger", "breakout",
        "데드크로스", "골든크로스", "볼린저", "스토캐스틱", "브레이크아웃",
        "이평", "이동평균", "기술적", "시그널", "신호",
    ]
    return any(term in compact_prompt for term in technical_terms)


def _trim_model_trailing_tokens(text: str) -> str:
    trimmed = text.strip()
    for token in _MODEL_TRAILING_TOKENS:
        if token in trimmed:
            trimmed = trimmed.split(token, 1)[0].rstrip()
    return trimmed


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")

    in_string = False
    escaped = False
    depth = 0

    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]

    repaired = _repair_incomplete_json_object(text[start:], depth, in_string)
    if repaired is not None:
        return repaired

    raise ValueError("Incomplete JSON object in model output")


def _repair_incomplete_json_object(fragment: str, depth: int, in_string: bool) -> Optional[str]:
    """Best-effort repair for model outputs truncated only at the tail."""
    candidate = fragment.rstrip()
    if not candidate:
        return None

    if in_string:
        candidate += '"'

    while candidate and candidate[-1] in [",", ":"]:
        candidate = candidate[:-1].rstrip()

    candidate += "}" * max(depth, 0)
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        return None


def _parse_model_json_response(raw_text: str, model_cls: type[BaseModel]) -> BaseModel:
    cleaned = _trim_model_trailing_tokens(raw_text)
    json_text = _extract_json_object(cleaned)
    return model_cls.model_validate_json(json_text)


# ─── LLM 환각 신호 검증 ─────────────────────────────────────────────────────

# 지표별 프롬프트 키워드 매핑: 프롬프트에 이 키워드 중 하나라도 있어야 해당 지표를 인정
_INDICATOR_KEYWORDS: dict[str, list[str]] = {
    "ma_crossover": ["골든크로스", "데드크로스", "이동평균", "이평선", "ma크로스", "goldencross", "deadcross", "ma_crossover"],
    "rsi": ["rsi"],
    "ema": ["ema", "지수이동평균"],
    "macd": ["macd"],
    "bollinger_bands": ["볼린저", "bollinger"],
    "breakout": ["브레이크아웃", "breakout", "신고가", "돌파"],
    "volume_spike": ["거래량급증", "거래량폭발", "volumespike"],
    "stochastic": ["스토캐스틱", "stochastic"],
    "cci": ["cci"],
    "adx": ["adx"],
    "ai_model": ["ai", "인공지능"],
    "ai_drop_model": ["ai", "인공지능"],
}

# 패턴/서술형 신호: 표현이 무한히 다양해(박스권 돌파, 이평선 위로 뚫음, 거래량 터짐…)
# 고정 키워드 화이트리스트로 거르면 모델이 맞게 뽑은 신호까지 잘라낸다. 따라서 이들은
# 키워드 검증을 건너뛰고 모델/결정적 추출을 신뢰한다. 반대로 이름이 고정된 지표
# (rsi/macd/cci/adx/stochastic/bollinger/ema/ai)는 사용자가 그 이름을 직접 써야 하므로
# 환각 방지를 위해 키워드 검증을 유지한다.
_DESCRIPTIVE_INDICATORS = {"ma_crossover", "breakout", "volume_spike"}


def _validate_signals(
    signals: list[TechnicalSignal],
    user_input: str,
) -> list[TechnicalSignal]:
    """
    LLM이 생성한 신호 중 환각으로 의심되는 것만 제거한다.

    이름이 고정된 지표(rsi/macd/cci 등)는 사용자가 그 이름을 직접 써야 하므로, 키워드가
    없으면 환각으로 보고 제거한다. 반면 서술형 신호(_DESCRIPTIVE_INDICATORS)는 표현이
    무한히 다양해 키워드로 거르면 오히려 정답을 잘라내므로, 검증 없이 신뢰한다.
    (놓친 표현은 키워드를 늘리는 대신 LLM 프롬프트 예시로 일반화한다.)
    """
    compact = _compact(user_input)
    validated: list[TechnicalSignal] = []
    for sig in signals:
        if sig.indicator in _DESCRIPTIVE_INDICATORS:
            # 서술형 신호는 표현이 다양해 키워드 검증을 건너뛰고 신뢰한다.
            validated.append(sig)
            continue
        keywords = _INDICATOR_KEYWORDS.get(sig.indicator, [])
        if not keywords:
            # 알 수 없는 지표는 일단 유지
            validated.append(sig)
            continue
        if any(kw in compact for kw in keywords):
            validated.append(sig)
    return validated


def _nearest_pct(compact: str, idx: int, window: int = 16) -> Optional[float]:
    """compact 문자열에서 위치 idx 근처(±window)에 있는 가장 가까운 퍼센트 값을 찾는다.

    AI 모델 신뢰도 임계값처럼 '상승/하락' 키워드 주변의 '80% 이상' 류를 결정적으로
    뽑기 위한 헬퍼. 키워드 양쪽 어디에 있어도 거리가 가장 가까운 %를 택한다.
    """
    best: Optional[float] = None
    best_dist = window + 1
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", compact):
        dist = abs(m.start() - idx)
        if dist < best_dist:
            best_dist = dist
            best = float(m.group(1))
    return best


def _extract_ema_periods(compact: str) -> Optional[tuple[int, int]]:
    """EMA 기간 두 개를 어순에 무관하게 추출한다.

    'N일 EMA'(숫자 먼저)와 'EMA N'(EMA 먼저) 표현을 모두 인식한다. 앞에서부터 두 개를
    찾아 (단기, 장기)로 정렬해 돌려준다. 두 개 미만이면 None.
    """
    nums: list[int] = []
    for a, b in re.findall(r"(?:(\d+)일?\s*ema|ema\s*(\d+)일?)", compact):
        nums.append(int(a or b))
    if len(nums) < 2:
        return None
    p1, p2 = nums[0], nums[1]
    return (min(p1, p2), max(p1, p2))


# ── 매수/매도 동사의 활용형·동의어 (품사 변화 일반화) ──────────────────────────
# 표현마다 패턴을 늘리는 대신 동사 활용형/유의어를 한 곳에 모은다(공백 제거 compact 기준).
# 단일 글자(사/담)는 '회사'·'담보' 등과의 오매칭을 피하려 활용 어미를 묶은 형태만 허용한다.
# _BUY_HINT: 오실레이터(rsi/stoch/cci) 과매도 진입/반등 맥락 — '반등/올라' 같은 반등 cue 포함.
_BUY_HINT = r"(?:매수|진입|매입|편입|들어가|담[고아아서는]|사[고서면자들]|산다|반등|올라)"
# _SELL_V: 청산 동사 — '매도/청산' 외 '정리/처분/매각'과 '팔다' 활용형까지.
_SELL_V = r"(?:매도|청산|정리|처분|매각|팔[고아자래면게까]|(?<!돌)파는|판다)"
# 지표명과 숫자 사이 주격·주제·목적격 조사(+보조사 '도'). 품사 변화 전반을 한 토큰으로.
_SUBJ_PARTICLE = r"(?:가|이|은|는|을|를|도)?"


def _extract_technical_signals(user_input: str) -> tuple[list[TechnicalSignal], list[TechnicalSignal]]:
    """
    프롬프트에서 기술적 진입/청산 신호를 deterministic하게 추출한다.
    LLM이 놓칠 수 있는 패턴을 보장하기 위한 후처리 단계.

    Returns:
        (entry_signals, exit_signals)
    """
    compact = _compact(user_input)
    entry: list[TechnicalSignal] = []
    exit_: list[TechnicalSignal] = []

    # ── 골든크로스 / 데드크로스 (MA 크로스오버) ──
    # 기간 추출: "5일/20일", "5일20일", "20일선과 60일선", "5일선이 20일선",
    # "20일 이동평균이 60일 이동평균" 등.
    # 두 'N일' 사이에 조사·'선'·'이동평균(선)' 등이 끼어도(비숫자 8글자 이내) 잡는다.
    # (기간은 MA 크로스가 감지됐을 때만 적용되므로, 이 문맥의 두 'N일'은 사실상 항상 두 MA 기간이다.)
    ma_short, ma_long = None, None
    ma_period_match = re.search(r"(\d+)일선?[^0-9]{0,8}(\d+)일", compact)
    if ma_period_match:
        p1, p2 = int(ma_period_match.group(1)), int(ma_period_match.group(2))
        ma_short, ma_long = min(p1, p2), max(p1, p2)

    # "MACD 골든크로스" / "EMA 데드크로스"처럼 크로스 앞에 지표명이 붙으면 그 지표의
    # 크로스다(MA 크로스오버가 아니라). 해당 지표 블록에서 처리하도록 MA에서는 제외한다.
    golden_macd = bool(re.search(r"macd.{0,3}골든크로스", compact))
    dead_macd = bool(re.search(r"macd.{0,3}데드크로스", compact))
    golden_ema = bool(re.search(r"ema.{0,3}골든크로스", compact))
    dead_ema = bool(re.search(r"ema.{0,3}데드크로스", compact))

    has_golden_raw = any(p in compact for p in ["골든크로스", "goldencross", "golden_cross"])
    has_dead_raw = any(p in compact for p in ["데드크로스", "deadcross", "dead_cross"])
    has_golden = has_golden_raw and not (golden_macd or golden_ema)
    has_dead = has_dead_raw and not (dead_macd or dead_ema)

    # "크로스오버" / "이동평균 크로스" 같은 일반 표현 + 매수/매도 언급
    if not has_golden and not has_dead and not has_golden_raw and not has_dead_raw:
        crossover_terms = [
            "이동평균선을위로뚫", "이동평균크로스", "ma크로스", "이평선크로스",
            "이동평균을뚫고올라", "장기이동평균을뚫고올라", "이동평균을상향돌파",
        ]
        if any(t in compact for t in crossover_terms):
            has_golden = True
            # "반대로" / "아래로" / "매도" 가 함께 있으면 데드크로스(하향 교차)도 포함
            if "반대로" in compact or "아래로뚫" in compact or ("매도" in compact and "매수" in compact) or ("팔" in compact and "사" in compact):
                has_dead = True

    if has_golden:
        entry.append(TechnicalSignal(
            indicator="ma_crossover",
            signal_type="buy",
            short_period=ma_short or 5,
            long_period=ma_long or 20,
        ))
    if has_dead:
        exit_.append(TechnicalSignal(
            indicator="ma_crossover",
            signal_type="sell",
            short_period=ma_short or 5,
            long_period=ma_long or 20,
        ))

    # ── 가격이 이동평균선 위/아래 (추세 필터) ──
    # "종가가 20일선 위에 있으면 매수" → ma_crossover(short=1, long=N) 골든(종가가 MA 상향)
    # "20일선 아래로 내려오면 매도"   → ma_crossover(short=1, long=N) 데드(종가가 MA 하향)
    # short=1은 종가 자체(close_1_sma=close)라 '가격 vs MA' 교차로 표현된다.
    # 골든/데드 크로스가 이미 잡혔으면 ma_crossover 충돌을 피해 건너뛴다.
    # 방향어 앞에 부사가 끼어도("강하게 상향 돌파") 잡도록 .{0,5} 허용.
    ma_token = r"(?:이동평균선|이동평균|이평선|이평|선)"
    if not has_golden:
        above_ma = re.search(rf"(\d+)일{ma_token}(?:을|를)?.{{0,5}}(?:위|상회|넘|돌파|올라|상향)", compact)
        if above_ma:
            entry.append(TechnicalSignal(
                indicator="ma_crossover", signal_type="buy",
                short_period=1, long_period=int(above_ma.group(1)),
            ))
    if not has_dead:
        below_ma = re.search(rf"(\d+)일{ma_token}(?:을|를)?.{{0,5}}(?:아래|밑|하회|이탈|하향|깨)", compact)
        if below_ma:
            exit_.append(TechnicalSignal(
                indicator="ma_crossover", signal_type="sell",
                short_period=1, long_period=int(below_ma.group(1)),
            ))

    # ── EMA 크로스 (단기 EMA가 장기 EMA 위/아래) ──
    # "20일 EMA가 60일 EMA 위에 있고" 와 "EMA 20이 EMA 60 위로" 양쪽 어순을 모두 인식한다
    # (_extract_ema_periods). 진입은 상향(위/돌파/상향)·'ema 골든크로스', 청산은 하향
    # (아래/이탈/하향)·'ema 데드크로스'. 진입만 기간이 적히고 청산은 "다시 아래로 내려오면"
    # 처럼 기간을 생략하는 경우가 많아, 진입이 잡히면 하향+매도 표현을 같은 기간으로 미러링한다.
    ema_periods = _extract_ema_periods(compact)
    if ema_periods:
        ema_s, ema_l = ema_periods
        ema_buy = bool(
            golden_ema
            or re.search(r"ema.{0,14}(?:위|상회|넘|돌파|상향|이상|높|올라)", compact)
        )
        ema_sell_explicit = bool(
            dead_ema
            or re.search(r"ema.{0,14}(?:아래|밑|하회|이탈|하향|내려)", compact)
        )
        # 진입 후 "다시 아래로 내려오면 매도" 같은 미러 청산(기간 생략).
        ema_sell_mirror = bool(
            ema_buy
            and re.search(rf"(?:아래|하향|이탈|내려|데드)[^,]{{0,8}}{_SELL_V}", compact)
        )
        if ema_buy:
            entry.append(TechnicalSignal(
                indicator="ema", signal_type="buy", short_period=ema_s, long_period=ema_l,
            ))
        if ema_sell_explicit or ema_sell_mirror:
            exit_.append(TechnicalSignal(
                indicator="ema", signal_type="sell", short_period=ema_s, long_period=ema_l,
            ))

    # ── RSI 매수/매도 ──
    # 조사("rsi가30") + "이하/미만/아래/밑" + 매수/진입/반등/올라오는(과매도 반등) 표현 허용.
    # 숫자 없이 'RSI가 바닥을 찍고 반등' 같은 구어체 과매도 반등도 기본 30으로 매수 처리.
    # 명시 숫자('RSI 28 이하')를 구어체('바닥 찍고 반등')보다 우선해, 둘이 같은 문장에 섞여도
    # 정확한 임계값을 쓴다. 숫자형이 없을 때만 구어체 과매도 반등(기본 30)으로 매수 처리.
    rsi_buy_numeric = re.search(
        rf"rsi{_SUBJ_PARTICLE}\s*(\d+)\s*(?:을|를)?\s*(?:이하|미만|아래|밑).*?{_BUY_HINT}",
        compact,
    )
    rsi_buy_colloquial = re.search(
        rf"rsi.*?(?:과매도|바닥|저점).*?{_BUY_HINT}", compact
    )
    # 과매도 '반등'(임계선 아래로 갔다가 다시 상향 돌파) vs 단순 '과매도 구간 진입'(RSI<=30) 구분.
    # 임계선 아래/과매도 언급 뒤에 '다시/반등/회복/올라'가 따라오면 반등 → mode='rebound'.
    rsi_buy_rebound = bool(
        re.search(r"rsi[^.]*?(?:이하|미만|아래|밑)[^.]*?(?:다시|반등|반전|회복|올라|튀|튕)", compact)
        or re.search(r"rsi[^.]*?(?:과매도|바닥|저점)[^.]*?(?:다시|반등|반전|회복|올라)", compact)
    )
    if rsi_buy_numeric:
        entry.append(TechnicalSignal(
            indicator="rsi", signal_type="buy", period=14, operator="<=",
            value=float(rsi_buy_numeric.group(1)), mode="rebound" if rsi_buy_rebound else None,
        ))
    elif rsi_buy_colloquial:
        entry.append(TechnicalSignal(
            indicator="rsi", signal_type="buy", period=14, operator="<=", value=30.0,
            mode="rebound" if rsi_buy_rebound else None,
        ))
    # 'rsi 70 이상 ... 매도'(정방향)와 '청산은 ... rsi 70 이상'(역방향=청산 동사가 먼저)을
    # 모두 인식한다. 절(쉼표) 경계를 넘지 않게 [^,]로 막아, 다른 절의 매도 동사를 잘못
    # 끌어오지 않는다. '넘'(넘어서면)도 '이상' 동의어로 처리한다.
    rsi_sell_match = re.search(
        rf"rsi{_SUBJ_PARTICLE}\s*(\d+)\s*(?:을|를)?\s*(?:이상|초과|위|넘)[^,]*?{_SELL_V}"
        rf"|{_SELL_V}[^,]*?rsi{_SUBJ_PARTICLE}\s*(\d+)\s*(?:을|를)?\s*(?:이상|초과|위|넘)"
        rf"|rsi[^,]*?과매수[^,]*?{_SELL_V}",
        compact,
    )
    if rsi_sell_match:
        raw = rsi_sell_match.group(1) or rsi_sell_match.group(2)
        val = int(raw) if raw else 70
        exit_.append(TechnicalSignal(
            indicator="rsi", signal_type="sell", period=14, operator=">=", value=float(val),
        ))
    elif any(s.indicator == "rsi" and s.signal_type == "buy" for s in entry) and re.search(
        rf"(?:과열|충분히올라|많이올라).{{0,8}}{_SELL_V}", compact
    ):
        # 'RSI 과매도 반등 매수 / 과열되면 매도' 구어체 미러 청산(숫자 없으면 기본 70).
        exit_.append(TechnicalSignal(
            indicator="rsi", signal_type="sell", period=14, operator=">=", value=70.0,
        ))

    # ── MACD ──
    # 시그널선 교차/돌파(crossover)와 0선(제로선) 돌파/양수(zero)를 모두 인식한다. macd와
    # '시그널'·'0선' 사이에 조사가 끼어도(예: 'macd가 시그널을') 잡도록 .{0,6} 허용.
    macd_signal_buy = bool(re.search(r"macd.{0,6}시그널.{0,6}(?:상향|위|돌파|교차|크로스|넘)", compact))
    macd_zero_buy = bool(re.search(r"macd.{0,6}(?:0선|영선|제로|제로선|0\s*라인).{0,6}(?:상향|위|돌파|올라|넘)", compact)
                         or re.search(r"macd.{0,4}양수", compact))
    macd_buy_legacy = any(re.search(p, compact) for p in ["macd크로스.{0,6}매수", "macd.{0,4}골든", "macd시그널.{0,6}매수"])
    if golden_macd or macd_signal_buy or macd_zero_buy or macd_buy_legacy:
        mode = "zero" if (macd_zero_buy and not (golden_macd or macd_signal_buy)) else "crossover"
        entry.append(TechnicalSignal(indicator="macd", signal_type="buy", mode=mode))

    macd_signal_sell = bool(re.search(r"macd.{0,6}시그널.{0,6}(?:하향|아래|이탈|데드)", compact))
    macd_zero_sell = bool(re.search(r"macd.{0,6}(?:0선|영선|제로|제로선|0\s*라인).{0,6}(?:하향|아래|이탈|내려)", compact))
    macd_sell_legacy = any(re.search(p, compact) for p in ["macd크로스.{0,6}매도", "macd.{0,4}데드", "macd시그널.{0,6}매도"])
    if dead_macd or macd_signal_sell or macd_zero_sell or macd_sell_legacy:
        mode = "zero" if (macd_zero_sell and not (dead_macd or macd_signal_sell)) else "crossover"
        exit_.append(TechnicalSignal(indicator="macd", signal_type="sell", mode=mode))

    # ── ADX (추세 강도 필터) ──
    # 'ADX가 25 이상' 류를 진입 조건으로 잡는다. ADX는 단독 트리거보다 추세 강도 확인용이지만,
    # 규칙 기반에서 통째로 누락하면 코치가 '없는 조건을 있다'고 오인하므로 명시적으로 포착한다.
    adx_match = re.search(r"adx(?:가|이|은|는|도)?\s*(\d+(?:\.\d+)?)\s*(?:를|을)?\s*(이상|초과|이하|미만)?", compact)
    if adx_match:
        op_word = adx_match.group(2)
        entry.append(TechnicalSignal(
            indicator="adx", signal_type="buy", period=14,
            operator=_OPERATOR_BY_KOREAN.get(op_word or "", ">="),
            value=float(adx_match.group(1)),
        ))

    # ── 스토캐스틱 (과매도 매수 / 과매수 매도) ──
    # RSI와 동형: 'N 이하 ... 매수'(과매도 반등) / 'N 이상 ... 매도'(과매수). 숫자가 없으면
    # 과매도=20 / 과매수=80 기본값. 엔진·컨버터가 이미 stochastic을 지원하므로 추출만 추가한다.
    stoch_term = r"(?:스토캐스틱|stochastic)"
    stoch_buy = re.search(
        rf"{stoch_term}{_SUBJ_PARTICLE}\s*(\d+)\s*(?:을|를)?\s*(?:이하|미만|아래|밑).*?{_BUY_HINT}"
        rf"|{stoch_term}.*?과매도.*?{_BUY_HINT}",
        compact,
    )
    if stoch_buy:
        val = int(stoch_buy.group(1)) if stoch_buy.group(1) else 20
        entry.append(TechnicalSignal(
            indicator="stochastic", signal_type="buy", operator="<=", value=float(val),
        ))
    stoch_sell = re.search(
        rf"{stoch_term}{_SUBJ_PARTICLE}\s*(\d+)\s*(?:을|를)?\s*(?:이상|초과|위|넘)[^,]*?{_SELL_V}"
        rf"|{stoch_term}[^,]*?과매수[^,]*?{_SELL_V}",
        compact,
    )
    if stoch_sell:
        val = int(stoch_sell.group(1)) if stoch_sell.group(1) else 80
        exit_.append(TechnicalSignal(
            indicator="stochastic", signal_type="sell", operator=">=", value=float(val),
        ))

    # ── CCI (과매도 매수 / 과매수 매도) ──
    # 값이 음수일 수 있어 부호를 포함해 추출한다(예: 'CCI -100 이하'). 숫자가 없으면
    # 과매도=-100 / 과매수=100 기본값.
    cci_buy = re.search(
        rf"cci{_SUBJ_PARTICLE}\s*(-?\d+)\s*(?:을|를)?\s*(?:이하|미만|아래|밑).*?{_BUY_HINT}"
        rf"|cci.*?과매도.*?{_BUY_HINT}",
        compact,
    )
    if cci_buy:
        val = int(cci_buy.group(1)) if cci_buy.group(1) else -100
        entry.append(TechnicalSignal(
            indicator="cci", signal_type="buy", period=14, operator="<=", value=float(val),
        ))
    cci_sell = re.search(
        rf"cci{_SUBJ_PARTICLE}\s*(-?\d+)\s*(?:을|를)?\s*(?:이상|초과|위|넘)[^,]*?{_SELL_V}"
        rf"|cci[^,]*?과매수[^,]*?{_SELL_V}",
        compact,
    )
    if cci_sell:
        val = int(cci_sell.group(1)) if cci_sell.group(1) else 100
        exit_.append(TechnicalSignal(
            indicator="cci", signal_type="sell", period=14, operator=">=", value=float(val),
        ))

    # ── Williams %R (범위 -100~0, 과매도 매수 / 과매수 매도) ──
    # 값이 음수라 부호 포함 추출. 숫자 없으면 과매도=-80 / 과매수=-20 기본값.
    wr_term = r"(?:williams%?r|윌리엄스%?r|williamsr|%r)"
    wr_buy = re.search(
        rf"{wr_term}{_SUBJ_PARTICLE}\s*(-?\d+)\s*(?:을|를)?\s*(?:이하|미만|아래|밑).*?{_BUY_HINT}"
        rf"|{wr_term}.*?과매도.*?{_BUY_HINT}",
        compact,
    )
    if wr_buy:
        val = int(wr_buy.group(1)) if wr_buy.group(1) else -80
        entry.append(TechnicalSignal(
            indicator="williams_r", signal_type="buy", period=14, operator="<=", value=float(val),
        ))
    wr_sell = re.search(
        rf"{wr_term}{_SUBJ_PARTICLE}\s*(-?\d+)\s*(?:을|를)?\s*(?:이상|초과|위|넘)[^,]*?{_SELL_V}"
        rf"|{wr_term}[^,]*?과매수[^,]*?{_SELL_V}",
        compact,
    )
    if wr_sell:
        val = int(wr_sell.group(1)) if wr_sell.group(1) else -20
        exit_.append(TechnicalSignal(
            indicator="williams_r", signal_type="sell", period=14, operator=">=", value=float(val),
        ))

    # ── MFI (자금흐름지표, 0~100, 과매도 매수 / 과매수 매도) ──
    # RSI와 동형. 숫자 없으면 과매도=20 / 과매수=80 기본값.
    mfi_term = r"(?:mfi|자금흐름지표|머니플로우)"
    mfi_buy = re.search(
        rf"{mfi_term}{_SUBJ_PARTICLE}\s*(\d+)\s*(?:을|를)?\s*(?:이하|미만|아래|밑).*?{_BUY_HINT}"
        rf"|{mfi_term}.*?과매도.*?{_BUY_HINT}",
        compact,
    )
    if mfi_buy:
        val = int(mfi_buy.group(1)) if mfi_buy.group(1) else 20
        entry.append(TechnicalSignal(
            indicator="mfi", signal_type="buy", period=14, operator="<=", value=float(val),
        ))
    mfi_sell = re.search(
        rf"{mfi_term}{_SUBJ_PARTICLE}\s*(\d+)\s*(?:을|를)?\s*(?:이상|초과|위|넘)[^,]*?{_SELL_V}"
        rf"|{mfi_term}[^,]*?과매수[^,]*?{_SELL_V}",
        compact,
    )
    if mfi_sell:
        val = int(mfi_sell.group(1)) if mfi_sell.group(1) else 80
        exit_.append(TechnicalSignal(
            indicator="mfi", signal_type="sell", period=14, operator=">=", value=float(val),
        ))

    # ── ROC / 모멘텀 (변화율 %, 0 기준 상승/하락) ──
    # 'ROC 5 이상', '모멘텀이 플러스', 'N일 모멘텀' 류. 숫자 없으면 0 기준.
    roc_term = r"(?:roc|모멘텀|momentum|변화율)"
    roc_period_match = re.search(rf"(\d+)일{roc_term}|{roc_term}\D{{0,3}}(\d+)일", compact)
    roc_period = None
    if roc_period_match:
        roc_period = int(roc_period_match.group(1) or roc_period_match.group(2))
    roc_buy = re.search(
        rf"{roc_term}{_SUBJ_PARTICLE}\s*(-?\d+(?:\.\d+)?)?\s*(?:을|를)?\s*(?:이상|초과|위|넘|플러스|양수).*?{_BUY_HINT}",
        compact,
    )
    if roc_buy:
        raw = roc_buy.group(1)
        entry.append(TechnicalSignal(
            indicator="roc", signal_type="buy", period=roc_period or 12,
            operator=">", value=float(raw) if raw else 0.0,
        ))
    roc_sell = re.search(
        rf"{roc_term}{_SUBJ_PARTICLE}\s*(-?\d+(?:\.\d+)?)?\s*(?:을|를)?\s*(?:이하|미만|아래|밑|마이너스|음수).*?{_SELL_V}",
        compact,
    )
    if roc_sell:
        raw = roc_sell.group(1)
        exit_.append(TechnicalSignal(
            indicator="roc", signal_type="sell", period=roc_period or 12,
            operator="<", value=float(raw) if raw else 0.0,
        ))

    # ── 볼린저밴드 ──
    # 하단/중심선 회복 매수(평균회귀)뿐 아니라 상단 돌파 진입(추세)·하단 도달 청산도 포착한다.
    if re.search(rf"볼린저.*?(?:하단|중심선).*?{_BUY_HINT}|볼린저밴드.*?{_BUY_HINT}|볼린저.*?상단.*?돌파", compact):
        entry.append(TechnicalSignal(indicator="bollinger_bands", signal_type="buy"))
    # 청산은 밴드 경계(상단/하단/중심선)가 매도/청산 동사와 같은 절(쉼표 미포함) 안에서 가까이
    # 있을 때만 잡는다. '볼린저'가 청산 절에 다시 안 나와도 되지만('하단에 닿으면 청산'), 청산
    # 절이 밴드와 무관하면(예: "상단 돌파 매수, 데드크로스 청산") 잘못 만들지 않는다.
    if "볼린저" in compact and re.search(rf"(?:상단|하단|중심선)[^,]{{0,10}}(?:{_SELL_V}|닿|도달)", compact):
        exit_.append(TechnicalSignal(indicator="bollinger_bands", signal_type="sell"))

    # ── 브레이크아웃 (신고가 / 박스권 위로 돌파 / N일 고점 돌파) ──
    breakout_lookback = _extract_breakout_lookback(compact)
    has_high_breakout = bool(
        re.search(rf"(?:\d+(?:주|일)?)?신고가.*?(?:돌파|들어가|새로만들|{_BUY_HINT})", compact)
        or "브레이크아웃" in compact
        or re.search(r"박스권?.{0,8}돌파", compact)
        # "박스권에서 횡보하다가 ... 위로 치고 올라가면" 같은 구어체 상방 돌파(박스권과 방향
        # 표현이 떨어져 있어도 인식). breakout은 서술형 신뢰 지표라 다소 넓게 잡아도 안전하다.
        or re.search(r"박스권?.{0,18}위로.{0,8}(?:돌파|치고|올라|뚫)", compact)
        or re.search(r"\d+일고점.{0,6}(?:돌파|넘|상향|위로|매수)", compact)
        or re.search(r"고점.{0,4}돌파", compact)
    )
    if has_high_breakout:
        entry.append(TechnicalSignal(
            indicator="breakout", signal_type="buy", lookback_period=breakout_lookback,
        ))

    # ── 박스권 이탈 매도 (박스 하단/저점 하향 이탈 → breakout sell) ──
    has_box_breakdown = bool(
        re.search(rf"박스권?.{{0,8}}(?:안으로|내려|아래|밑|하단|이탈|빠).{{0,8}}(?:{_SELL_V}|손절)", compact)
        or re.search(rf"\d+일저점.{{0,6}}(?:이탈|깨|하향|무너).{{0,8}}(?:{_SELL_V}|손절)", compact)
    )
    if has_box_breakdown:
        exit_.append(TechnicalSignal(
            indicator="breakout", signal_type="sell", lookback_period=breakout_lookback,
        ))

    # ── 거래량/거래대금 급증 또는 이동평균 대비 증가 ──
    # 문구가 다양해(급증/폭발/터짐/평소보다 늘…) 고정 문자열 대신 패턴으로 일반화한다.
    # '거래대금'도 포함하되, '거래대금 N억 이상'(정적 필터)과 달리 '평균보다 높은' 류는 동적 신호다.
    volume_term = r"(?:거래량|거래대금)"
    volume_rising = bool(
        re.search(rf"{volume_term}.{{0,5}}(?:급증|폭발|터[지진졌짐])", compact)
        # "거래량이 평소보다 크게 터지면서"처럼 급증 동사(터지)가 거래량과 떨어져 있어도 인식.
        or re.search(rf"{volume_term}.{{0,12}}터[지진졌짐]", compact)
        or re.search(rf"{volume_term}.{{0,12}}(?:평균|평소).{{0,6}}(?:늘|증가|많|상회|높|\d+배)", compact)
        # '거래대금이 크게 늘고'처럼 평균 언급 없이 증가만 표현한 경우도 동적 신호로 본다.
        or re.search(rf"{volume_term}.{{0,6}}(?:크게|확|많이|부쩍)?(?:늘|불어|증가)", compact)
        or "volumespike" in compact
    )
    if volume_rising:
        # "30일 평균보다 높은" 처럼 명시된 기간이 있으면 그 기간을, 없으면 20일을 쓴다.
        vol_period_match = re.search(r"(\d+)일.{0,4}평균", compact)
        vol_period = int(vol_period_match.group(1)) if vol_period_match else 20
        entry.append(TechnicalSignal(indicator="volume_spike", signal_type="buy", period=vol_period))

    # ── AI 상승/하락 예측 모델 ──
    # 'AI(인공지능)' 언급 + '상승 ...예측/확률/신호' → ai_model 매수, '하락 ...예측/신호/위험' →
    # ai_drop_model 매도. 신뢰도 임계값은 '상승'/'하락' 키워드 근처의 'N%'를 결정적으로 잡고,
    # 없으면 기본 70. AI 신호는 종목별 신호라 LLM이 자주 누락해 결정적 추출이 특히 중요하다.
    if "ai" in compact or "인공지능" in compact:
        up = re.search(r"상승", compact)
        if up and re.search(
            r"상승.{0,6}(?:예측|예상|확률|신호|전망|기대)|(?:ai|인공지능).{0,4}매수|상승을예측", compact
        ):
            thr = _nearest_pct(compact, up.start())
            entry.append(TechnicalSignal(
                indicator="ai_model", signal_type="buy", threshold=thr if thr is not None else 70.0,
            ))
        down = re.search(r"하락", compact)
        if down and re.search(
            r"하락.{0,6}(?:예측|예상|확률|신호|전망|위험)|(?:ai|인공지능).{0,4}매도|하락을예측|위험.{0,2}신호", compact
        ):
            thr = _nearest_pct(compact, down.start())
            exit_.append(TechnicalSignal(
                indicator="ai_drop_model", signal_type="sell", threshold=thr if thr is not None else 70.0,
            ))

    # ── 오실레이터(rsi/stochastic/cci)의 '맨숫자' 반대편 청산 ──
    # "스토캐스틱 20 이하 매수, 80 이상 매도"처럼 청산 임계값에 지표명을 다시 붙이지 않는
    # 경우가 흔하다. 진입에 오실레이터가 정확히 하나 잡혔고 그 청산이 아직 없으면, 'N 이상/
    # 넘으면 ... 매도/청산'(맨숫자)을 그 지표의 청산으로 귀속한다(한 규칙으로 일반화).
    _osc = {"rsi", "stochastic", "cci"}
    osc_buy_inds = {s.indicator for s in entry if s.indicator in _osc}
    osc_sell_inds = {s.indicator for s in exit_ if s.indicator in _osc}
    _OSC_OVERBOUGHT_DEFAULT = {"rsi": 70.0, "stochastic": 80.0, "cci": 100.0}
    if len(osc_buy_inds) == 1:
        ind = next(iter(osc_buy_inds))
        if ind not in osc_sell_inds:
            m = re.search(rf"(-?\d+)\s*(?:을|를|이|은|는)?\s*(?:이상|초과|위|넘)[^,]{{0,8}}{_SELL_V}", compact)
            if m:
                value = float(m.group(1))
            elif re.search(rf"과매수[^,]{{0,6}}{_SELL_V}", compact):
                # "스토캐스틱 과매도 매수, 과매수에서 매도"처럼 청산이 '과매수'(맨숫자 없음)인 경우.
                value = _OSC_OVERBOUGHT_DEFAULT[ind]
            else:
                value = None
            if value is not None:
                sig = TechnicalSignal(indicator=ind, signal_type="sell", operator=">=", value=value)
                if ind in {"rsi", "cci"}:
                    sig.period = 14
                exit_.append(sig)

    return entry, exit_


def _extract_breakout_lookback(compact: str) -> int:
    """브레이크아웃 기준 기간(거래일)을 추출한다. 신고가/최고가/고점/저점 앞의 숫자를
    사용하고, '주'는 거래일로 환산(52주=252)한다. 숫자가 없으면 박스권 기본값 20일."""
    match = re.search(r"(\d+)(주|일)?(?:신고가|최고가|고점|저점)", compact)
    if not match:
        return 20
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "주":
        return value * 5 if value < 52 else 252
    if unit == "일":
        return value
    return 252 if value == 52 else value


# 연산자 한국어 표현(부등호). '이하/미만/이상/초과' 외에 구어체 '아래/밑'(<), '넘는/보다 높은'
# (>)도 인식한다. 긴 토큰(보다높/보다낮)을 짧은 것보다 먼저 둬 부분매칭을 방지한다.
_OP_ALT = r"(보다높|보다많|보다큰|보다크|보다낮|보다적|보다작|이하|미만|이상|초과|아래|밑|이내|넘는|넘어|넘으|넘기)"

# 지표명과 숫자 사이 조사. 주격(이/가)·주제(은/는)뿐 아니라 목적격(을/를)도 인정한다
# ('roe를 5% 이상으로', 'pbr을 1.2 이하로'처럼 값을 목적어로 표현하는 수정 요청 대응).
_NUM_PARTICLE = r"(?:이|가|은|는|을|를|도)?"

_FUNDAMENTAL_PATTERN_SPECS = [
    ("pbr", [rf"(?:pbr|주가순자산비율|주가장부가치비율){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)\s*(?:배)?\s*{_OP_ALT}?"]),
    ("per", [rf"(?:per|주가수익비율|주가이익비율){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)\s*(?:배)?\s*{_OP_ALT}?"]),
    ("roe_or_gpa", [rf"(?:roe|gpa|자기자본이익률|자기자본수익률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("roa", [rf"(?:roa|총자산이익률|총자본이익률|총자산순이익률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("debt_ratio", [rf"(?:부채비율|부채){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("current_ratio", [rf"유동비율{_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("quick_ratio", [rf"당좌비율{_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("reserve_ratio", [rf"유보율{_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("gross_margin", [rf"(?:매출액총이익률|매출총이익률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("net_margin", [rf"(?:매출액순이익률|순이익률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("operating_margin", [rf"(?:매출액영업이익률|영업이익률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("revenue_growth", [rf"(?:매출액증가율|매출증가율|매출액성장률|매출성장률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("operating_income_growth", [rf"영업이익(?:증가율|성장률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    ("net_income_growth", [rf"(?:순이익|당기순이익)(?:증가율|성장률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    # psr=주가매출비율(낮을수록 저평가), per/pbr과 동일 형식.
    ("psr", [rf"(?:psr|주가매출액비율|주가매출비율){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)\s*(?:배)?\s*{_OP_ALT}?"]),
    # ev/ebitda=기업가치/EBITDA(낮을수록 저평가). 'ev/ebitda', 'ev ebitda', '에비타', '이브이에비타'.
    ("ev_ebitda", [rf"(?:ev[/\s-]?ebitda|이브이에비타|에비타|ev에비타|기업가치[/\s]?ebitda){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)\s*(?:배)?\s*{_OP_ALT}?"]),
    # 배당수익률(높을수록 고배당). '배당수익률', '시가배당률', '배당률'(단 '주식배당률'은 제외).
    ("dividend_yield", [rf"(?:배당수익률|시가배당률|배당률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    # 배당성향(배당금/순이익). '배당성향', '배당지급률'.
    ("payout_rate", [rf"(?:배당성향|배당지급률){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    # 배당성장률(전년 대비 주당배당 증가율). '배당성장률', '배당증가율', '배당성장', '배당증가'.
    ("dividend_growth", [rf"(?:배당성장률|배당증가율|배당성장|배당증가){_NUM_PARTICLE}\s*(\d+(?:\.\d+)?)%?\s*{_OP_ALT}?"]),
    # 금액 지표(억원 단위)는 '조'+'억' 콤보를 결정적으로 합산한다: (조 부분)?(억 부분)?(연산자)?.
    ("market_cap", [rf"(?:시가총액|시총){_NUM_PARTICLE}\s*(?:(\d+(?:\.\d+)?)조)?\s*(?:(\d+(?:\.\d+)?)(?:억원|억))?\s*{_OP_ALT}?"]),
    ("trading_value", [rf"(?:일평균거래대금|거래대금|거래량대금){_NUM_PARTICLE}\s*(?:(\d+(?:\.\d+)?)조)?\s*(?:(\d+(?:\.\d+)?)(?:억원|억))?\s*{_OP_ALT}?"]),
]

# 금액 지표는 값을 (조 부분 × 10000) + (억 부분)으로 합산한다. 그 외는 group(1) 단일 값.
_AMOUNT_METRICS = {"market_cap", "trading_value"}

_OPERATOR_BY_KOREAN = {
    "이하": "<=",
    "미만": "<",
    "이상": ">=",
    "초과": ">",
    # 구어체 동의어
    "아래": "<",
    "밑": "<",
    "이내": "<=",
    "보다낮": "<",
    "보다적": "<",
    "넘는": ">",
    "넘어": ">",
    "넘으": ">",
    "넘기": ">",
    "보다높": ">",
    "보다많": ">",
    "보다큰": ">",
    "보다크": ">",
    "보다작": "<",
}


def _default_operator_for_metric(metric: str) -> str:
    # 낮을수록 우량/저평가인 지표는 '<=', 높을수록 우량인 지표는 '>=' 기본값.
    if metric in {"pbr", "per", "psr", "ev_ebitda", "debt_ratio"}:
        return "<="
    return ">="


def _extract_amount_value(match: "re.Match") -> Optional[float]:
    """금액 지표 매치에서 (조 부분 × 10000) + (억 부분)을 억원 단위로 합산한다.

    group(1)=조 부분, group(2)=억 부분. 둘 다 없으면 숫자 없는 매치이므로 None.
    예: '2조5000억' → 25000, '1.5조' → 15000, '100억원' → 100.
    """
    jo, eok = match.group(1), match.group(2)
    if jo is None and eok is None:
        return None
    return (float(jo) * 10000.0 if jo else 0.0) + (float(eok) if eok else 0.0)


def _extract_fundamental_filters(user_input: str) -> list[FundamentalFilter]:
    compact = _compact(user_input)
    filters: list[FundamentalFilter] = []
    seen: set[tuple[str, str, float]] = set()

    for metric, patterns in _FUNDAMENTAL_PATTERN_SPECS:
        for pattern in patterns:
            for match in re.finditer(pattern, compact):
                if metric in _AMOUNT_METRICS:
                    value = _extract_amount_value(match)
                    if value is None:
                        continue
                else:
                    value = float(match.group(1))
                op_word = next(
                    (group for group in match.groups() if group in _OPERATOR_BY_KOREAN),
                    None,
                )
                operator = _OPERATOR_BY_KOREAN.get(op_word or "", _default_operator_for_metric(metric))
                key = (metric, operator, value)
                if key in seen:
                    continue
                filters.append(FundamentalFilter(metric=metric, operator=operator, value=value))
                seen.add(key)

    return filters


def _extract_ranking(user_input: str) -> tuple[Optional[str], Optional[int]]:
    """상대강도(수익률 순위) 랭킹 의도를 (metric, lookback_days)로 추출한다.

    '최근 60거래일 수익률이 높은 상위 N종목' / '모멘텀 상위' 류를 ('return', 60)로 매핑한다.
    종목 간 횡단면 순위 선정이라 진입 신호 없이 순위 자체가 진입이 된다. 없으면 (None, None).
    """
    compact = _compact(user_input)
    if not _mentions_relative_strength_ranking(compact):
        return (None, None)
    # 기간 추출: "60거래일", "60일 수익률", "최근 3개월" 등 → 거래일로 환산
    lookback: Optional[int] = None
    match = re.search(r"(\d+)거래일", compact)
    if match:
        lookback = int(match.group(1))
    else:
        match = re.search(r"(\d+)일.{0,4}(?:수익률|상승률|등락률|모멘텀)", compact)
        if match:
            lookback = int(match.group(1))
        else:
            match = re.search(r"(\d+)개월.{0,6}(?:수익률|상승률|오른|모멘텀)", compact)
            if match:
                lookback = int(match.group(1)) * 21
    if lookback is None:
        lookback = _korean_duration_to_trading_days(compact)
    return ("return", lookback or 60)


# 한글 숫자 표현 → 개월 수 (예: '한 달'=1, '세 달'=3).
_KOREAN_MONTH_WORDS = {"한": 1, "두": 2, "세": 3, "석": 3, "네": 4, "넉": 4, "다섯": 5, "여섯": 6}


def _korean_duration_to_trading_days(compact: str) -> Optional[int]:
    """'한 달'/'두 달'/'1주일' 같은 한글 기간 표현을 거래일 수로 환산한다. 없으면 None."""
    week_match = re.search(r"(\d+)주(?:일)?", compact)
    if week_match:
        return int(week_match.group(1)) * 5
    if re.search(r"(?:일주일|한주|1주)", compact):
        return 5
    month_match = re.search(r"(한|두|세|석|네|넉|다섯|여섯)달", compact)
    if month_match:
        return _KOREAN_MONTH_WORDS[month_match.group(1)] * 21
    return None


def _extract_cycle_months(compact: str) -> Optional[int]:
    """정기 재선정 주기를 개월 수로 환산한다. 'N개월마다'·'점검/리밸런싱 주기는 N개월'·
    'N개월 주기'를 모두 인식하고, 한글 수사('두 달')도 처리한다. 주기 표현이 없으면 None.
    (입력은 공백을 제거한 compact 문자열)"""
    digit = (
        re.search(r"(\d+)(?:개월|달)마다", compact)
        or re.search(r"주기[는은]?(\d+)(?:개월|달)", compact)
        or re.search(r"(\d+)(?:개월|달)주기", compact)
    )
    if digit:
        return int(digit.group(1))
    kw = "|".join(_KOREAN_MONTH_WORDS)
    korean = (
        re.search(rf"주기[는은]?({kw})달", compact)
        or re.search(rf"({kw})달(?:주기|마다)", compact)
    )
    if korean:
        return _KOREAN_MONTH_WORDS[korean.group(1)]
    return None


# '개' 뒤에 와서 종목 수가 아님을 뜻하는 단위(개월/개 분기) — '3개월'·'4개 분기'의 '3개'·'4개'
# 를 종목 수로 오인하지 않도록 부정 전망으로 막는다.
_NOT_POSITION_COUNT_UNIT = r"(?!월|분기|분)"


def _extract_max_positions(user_input: str) -> Optional[int]:
    compact = _compact(user_input)
    # 유니버스 규모(KOSPI 200 / KOSDAQ 150)의 숫자가 '200종목'처럼 종목 수로 오인되지 않도록 제거.
    compact = re.sub(r"(?:kospi|코스피)\s*200|(?:kosdaq|코스닥)\s*150", " ", compact)
    # 섹터/업종당 보유 제한('동일 업종 최대 2종목')은 포트폴리오 전체 종목 수가 아니므로 제거.
    compact = re.sub(r"(?:동일)?(?:업종|섹터)(?:별|당)?(?:최대)?\d+종목", " ", compact)

    pos = rf"(\d+)(?:개{_NOT_POSITION_COUNT_UNIT}|종목)"
    # 우선순위 1: 포트폴리오 크기를 명시한 표현. '총 N종목'은 '최대 N종목'(섹터 제한일 수 있음)보다 우선.
    priority_patterns = [
        rf"총{pos}",
        rf"(\d+)종목(?:동일|집중|포트폴리오|제한|유지|동일가중|동일비중)",
        r"동시보유(?:는)?(?:최대)?(\d+)종목",
        rf"최대{pos}",
        rf"상위{pos}",
        rf"{pos}(?:정도)?(?:씩)?나눠",
    ]
    for pattern in priority_patterns:
        match = re.search(pattern, compact)
        if match:
            return max(1, min(100, int(match.group(1))))
    # 우선순위 2: 일반 'N종목'/'N개'(개월·분기 제외)
    for pattern in [pos, r"maxpositions?(\d+)"]:
        match = re.search(pattern, compact)
        if match:
            return max(1, min(100, int(match.group(1))))
    return None


def _extract_hold_period_days(user_input: str) -> Optional[int]:
    compact = _compact(user_input)
    # 'N개월마다 점검/리밸런싱'·'점검 주기는 N개월'·'N개월 주기'는 보유기간이 아니라 정기 재선정
    # 주기다. 보유 동사가 없으면 보유기간으로 잡지 않는다.
    periodic = _extract_cycle_months(compact) is not None or re.search(
        r"마다.{0,4}(?:점검|재확인|리밸런)", compact
    )
    # '보유 종목/주식'은 보유 '기간'이 아니라 종목 '수' 맥락이므로 보유 동사로 보지 않는다.
    holding_verb = re.search(r"보유(?!종목|주식)|들고|가지고|가져가|유지|지나면", compact)
    if periodic and not holding_verb:
        return None
    if "1년" in compact or "일년" in compact:
        return 252
    if "6개월" in compact or "반년" in compact:
        return 126
    if "3개월" in compact:
        return 63
    if "1개월" in compact or "한달" in compact:
        return 21
    if "분기보유" in compact or "한분기" in compact:
        return 63
    if "반기보유" in compact:
        return 126

    # 'N년 보유'·'N년간 들고'처럼 보유 동사가 붙은 연 단위 보유기간(1년=252거래일).
    # 동사 없는 'N년'(백테스트 기간/모멘텀 룩백)과 구분하려고 보유 동사를 요구한다.
    match = re.search(r"(\d+)년(?:간|동안)?\s*(?:보유|들고|유지|가지고|가져)", compact)
    if match:
        return int(match.group(1)) * 252
    match = re.search(r"(\d+)개월", compact)
    if match:
        return int(match.group(1)) * 21
    # 'N주 보유'(주=5거래일). 보유 동사가 붙은 경우만(주간 리밸런싱과 혼동 방지).
    match = re.search(r"(\d+)주(?:일|간)?\s*(?:보유|들고|유지)", compact)
    if match:
        return int(match.group(1)) * 5
    match = re.search(r"(\d+)일(?:간)?보유", compact)
    if match:
        return int(match.group(1))
    match = re.search(rf"(\d+)일(?:정도|이|을|를)?지나면(?:무조건|바로|전량)?{_SELL_V}", compact)
    if match:
        return int(match.group(1))
    return None


def _has_explicit_day_holding(user_input: str) -> bool:
    """일(日) 단위로 명시된 보유기간 표현이 있는지 본다('20일 보유'·'30일 지나면 매도').

    개월/년 키워드(3개월·1년)는 모멘텀 룩백('최근 3개월 오른')과 구분이 안 되지만,
    'N일 보유'/'N일 지나면 정리'는 명백한 고정 보유기간이다. 랭킹 전략에서 보유기간을
    비울 때 이 명시적 표현은 보존하기 위한 판별자다.
    """
    compact = _compact(user_input)
    return bool(
        re.search(r"(\d+)일(?:간)?보유", compact)
        or re.search(rf"(\d+)일(?:정도)?지나면{_SELL_V}", compact)
    )


def _extract_rebalancing_period(user_input: str, hold_period_days: Optional[int]) -> str:
    compact = _compact(user_input)
    if re.search(r"매일|일간리밸런싱|날마다|하루에한번|데일리", compact):
        return "daily"
    if re.search(r"매주|주간리밸런싱|일주일에한번|한주에한번|주1회|주에한번|위클리|매주말", compact):
        return "weekly"
    # 격월은 반드시 monthly보다 먼저 — monthly의 '달에한번'이 '두달에한번'을 삼키기 때문.
    if re.search(r"격월|두달에한번|2개월에한번|2달에한번|두달마다|2개월마다|2달마다|두달걸러|2달걸러", compact):
        return "bimonthly"
    if "매월" in compact or "월간리밸런싱" in compact or re.search(r"한달에한번|달에한번|월1회|매달|먼슬리|다달이|월말마다|월초마다", compact):
        return "monthly"
    if "분기" in compact or "쿼터" in compact:
        return "quarterly"
    if "매년" in compact or "연간리밸런싱" in compact or re.search(r"해마다|연1회|연마다|1년마다|연단위|연례|1년에한번", compact):
        return "yearly"
    if hold_period_days == 252 and "보유" in compact:
        return "yearly"
    # 'N개월마다 (점검/재확인/리밸런싱)'·'점검 주기는 N개월'·'N개월 주기'(한글 수사 포함)
    # → 정기 재선정 주기. 보유기간이 아니라 주기적 회전 의도.
    cycle = _extract_cycle_months(compact)
    if cycle is not None:
        return {1: "monthly", 2: "bimonthly", 3: "quarterly", 12: "yearly"}.get(
            cycle, "monthly"
        )
    return "none"


def _extract_backtest_period(user_input: str) -> Optional[str]:
    """백테스트 기간을 결정적으로 추출한다. 언급이 없으면 None(기본값은 호출부에서 결정)."""
    compact = _compact(user_input)
    if "전체기간" in compact or "full" in compact:
        return "full"
    if "1y" in compact:
        return "1y"
    if "3y" in compact:
        return "3y"
    if "5y" in compact:
        return "5y"
    # '백테스트 기간은 3년만', '3년간 백테스트', '5년 백테스트' 처럼 백테스트 근처의 'N년'.
    # 보유기간('1년 보유')이 잡히지 않도록 '백테스트'와 'N년'이 인접(비숫자 몇 글자)할 때만.
    years = _extract_backtest_relative_years(user_input)
    if years is not None:
        # 1/3/5년은 상대 기간 버킷으로, 그 외(2/4/6…)는 _extract_backtest_dates가
        # 오늘 기준 명시적 날짜 범위로 결정적 처리한다.
        return {1: "1y", 3: "3y", 5: "5y"}.get(years)
    return None


# 백테스트 맥락에 인접한 'N년'·'N개월'을 추출하는 정규식(공백 제거 입력 기준).
# 연/월은 백테스트 창을 직접 표현하는 유한 시간 단위라 결정적으로 처리한다(주/일은 백테스트
# 창으로는 비현실적 phrasing이라 의도적으로 제외 — 긴 꼬리는 LLM/되묻기에 위임).
_BACKTEST_YEARS_RE = re.compile(r"백테스트\D{0,8}(\d+)년|(\d+)년(?:간|동안)?\D{0,6}백테스트")
_BACKTEST_MONTHS_RE = re.compile(
    r"백테스트\D{0,8}(\d+)(?:개월|달)|(\d+)(?:개월|달)(?:간|동안)?\D{0,6}백테스트"
)


def _extract_backtest_relative_years(user_input: str) -> Optional[int]:
    """백테스트 맥락에 인접한 'N년' 상대 기간의 연수를 추출한다(없으면 None)."""
    compact = _compact(user_input)
    m = _BACKTEST_YEARS_RE.search(compact)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def _extract_backtest_relative_months(user_input: str) -> Optional[int]:
    """백테스트 맥락에 인접한 'N개월'·'N달' 상대 기간의 개월수를 추출한다(없으면 None)."""
    compact = _compact(user_input)
    m = _BACKTEST_MONTHS_RE.search(compact)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def _subtract_months(d: date, months: int) -> date:
    """기준일에서 months개월을 뺀 날짜(말일 클램프)."""
    total = d.year * 12 + (d.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


# 한국어 기간 표현(일반 인식 — phrasing마다 추가하는 게 아니라 시간 단위의 유한 집합).
# 공백 제거(compact) 입력 기준.
_DURATION_COMPACT = (
    r"(?:일주일|반년|며칠"
    r"|\d+(?:년|개월|달|주일|주|일|거래일)"
    r"|(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|열한|열두)(?:년|개월|달|주))"
)
# 백테스트 기간 의도 맥락.
_BACKTEST_CONTEXT = r"(?:백테스트|백테스팅|테스트기간|검증기간)"


def _backtest_period_state(user_input: str) -> str:
    """백테스트 기간 추출의 3-상태: 'not_mentioned' | 'parsed' | 'unresolved'.

    'unresolved' = 백테스트 맥락에 인접한 시간 표현(기간 의도)은 있는데, 실제 리졸버
    (_extract_backtest_period / _extract_backtest_dates)가 유효 버킷(1y/3y/5y/full)이나
    명시적 연도 범위로 매핑하지 못한 경우. 즉 룰이 '봤지만 못 푼' 상태다 → 호출부가 LLM/
    되묻기로 위임한다.

    어떤 기간이 '너무 짧은지'를 열거하지 않는다(예: 1주일/6개월/2년 모두 리졸버가 못 풀면
    자동으로 unresolved). 룰의 커버리지 실패를 정직하게 신고하는 게 목적이다.
    """
    if _extract_backtest_period(user_input) is not None:
        return "parsed"
    start, end = _extract_backtest_dates(user_input)
    if start is not None or end is not None:
        return "parsed"
    compact = _compact(user_input)
    if not re.search(_BACKTEST_CONTEXT, compact):
        return "not_mentioned"
    # 백테스트 맥락 바로 뒤(조사·'기간'·'최근'만 사이)에 시간 표현이 오면 기간 의도로 본다.
    # '일선/평균/봉'은 지표 표현이므로 제외. 보유기간·지표기간이 백테스트와 멀리 떨어진
    # 경우는 인접 제약으로 자연히 배제된다.
    near = re.search(
        _BACKTEST_CONTEXT + r"(?:기간)?[은는을를이가로으]{0,2}(?:최근)?(" + _DURATION_COMPACT + r")(?!선|평균|봉)",
        compact,
    )
    return "unresolved" if near else "not_mentioned"


# 리밸런싱 의도 맥락(주기 단어). '주기/마다/점검'은 너무 일반적이라 제외하고 명시 cue만.
_REBALANCE_CONTEXT = r"(?:리밸런[싱스]|리밸|재조정|재선정|재산정)"

# 리밸런싱을 명시적으로 하지 않겠다는 표현("리밸런싱 없이", "리밸런싱은 하지 않고").
# compact(공백 제거) 기준. '언급 없음'과 '명시적 거부'를 구분해, 스크리닝 전략의
# 기본 월간 리밸런싱 주입이 사용자의 명시 의도를 덮어쓰지 않게 한다.
_REBALANCE_NEGATION_RE = re.compile(
    _REBALANCE_CONTEXT + r"[은는도]?(?:없이|안하|안함|안해|하지않|하지말|불필요|필요없|말고)"
)


def _mentions_rebalancing_negation(compact: str) -> bool:
    return bool(_REBALANCE_NEGATION_RE.search(compact))


def _rebalancing_period_state(user_input: str) -> str:
    """리밸런싱 주기 추출의 3-상태: 'not_mentioned' | 'parsed' | 'unresolved'.

    'unresolved' = 리밸런싱 의도는 있는데 주기 표현이 유효 enum(daily/weekly/monthly/
    bimonthly/quarterly/yearly)으로 안 풀린 경우(예: '10일마다'·'2주마다 리밸런싱'). 즉 룰이
    '봤지만 못 푼' 케이던스 → 호출부가 LLM에 위임한다. _backtest_period_state와 동형.
    """
    if _extract_rebalancing_period(user_input, None) != "none":
        return "parsed"
    compact = _compact(user_input)
    if not re.search(_REBALANCE_CONTEXT, compact):
        return "not_mentioned"
    # 리밸런싱 cue가 있는데 위에서 enum 매핑에 실패했고, 주기성 케이던스 표현(N일/N주 + 마다/
    # 에한번 등)이 있으면 매핑 불가 주기다 → unresolved.
    cadence = re.search(r"(?:" + _DURATION_COMPACT + r")(?:마다|에한번|주기|간격|에1회)", compact)
    return "unresolved" if cadence else "not_mentioned"


_YEAR = r"((?:19|20)\d{2})"
# 연도(+선택적 월·일). '2020년 1월'·'2020년 1월 15일'처럼 월/일이 붙은 명시 시점도
# 연도와 같은 유한 시간 단위이므로 결정적으로 처리한다(compact 입력 기준, 그룹 3개).
_YMD = rf"{_YEAR}년?(?:(\d{{1,2}})월)?(?:(\d{{1,2}})일)?"


def _ymd_to_iso(y: str, m: Optional[str], d: Optional[str], *, is_end: bool) -> Optional[str]:
    """(연, 월?, 일?) 캡처를 ISO 날짜로. 월/일 생략 시 시작=연초·1일, 종료=연말·말일.

    달력상 불가능한 월·일(13월, 2월 30일)은 추측하지 않고 None을 반환한다(Fail Fast —
    호출부가 미인식으로 처리해 LLM/되묻기에 위임).
    """
    year = int(y)
    month = int(m) if m else (12 if is_end else 1)
    if not 1 <= month <= 12:
        return None
    last_day = calendar.monthrange(year, month)[1]
    day = int(d) if d else (last_day if is_end else 1)
    if not 1 <= day <= last_day:
        return None
    return date(year, month, day).isoformat()


def _extract_backtest_dates(user_input: str) -> tuple[Optional[str], Optional[str]]:
    """'2002년부터 2005년까지'·'2020년 1월부터 2025년 12월까지' 같은 명시적 날짜 범위를
    (시작일, 종료일) ISO로 추출한다.

    상대 기간(1y/3y/5y)과 달리 명시적 연·월·일 범위는 결정적으로 처리한다(LLM 비의존).
    없으면 (None, None). 시작만/종료만 언급되면 한쪽만 채운다.
    """
    compact = re.sub(r"\s+", "", user_input)

    # YMD (부터|~|-|에서) YMD (까지)?  — 양끝 모두 명시
    span = re.search(rf"{_YMD}(?:부터|에서|~|-|–|—){_YMD}(?:까지)?", compact)
    if span:
        start = _ymd_to_iso(span.group(1), span.group(2), span.group(3), is_end=False)
        end = _ymd_to_iso(span.group(4), span.group(5), span.group(6), is_end=True)
        if start is not None and end is not None:
            if start > end:  # '2005년부터 2002년까지' — 이른 쪽을 시작으로
                start = _ymd_to_iso(span.group(4), span.group(5), span.group(6), is_end=False)
                end = _ymd_to_iso(span.group(1), span.group(2), span.group(3), is_end=True)
            return start, end

    # 'YYYY년만'·'YYYY년 M월만' — 단일 연도/월
    only = re.search(rf"{_YMD}만", compact)
    if only:
        start = _ymd_to_iso(only.group(1), only.group(2), only.group(3), is_end=False)
        end = _ymd_to_iso(only.group(1), only.group(2), only.group(3), is_end=True)
        if start is not None and end is not None:
            return start, end

    start_match = re.search(rf"{_YMD}부터", compact)
    end_match = re.search(rf"{_YMD}까지", compact)
    start = (
        _ymd_to_iso(start_match.group(1), start_match.group(2), start_match.group(3), is_end=False)
        if start_match else None
    )
    end = (
        _ymd_to_iso(end_match.group(1), end_match.group(2), end_match.group(3), is_end=True)
        if end_match else None
    )
    if start is not None or end is not None:
        return start, end

    # '백테스트 2년' 같은 상대 기간 중 버킷(1y/3y/5y)이 아닌 연수는 오늘 기준 명시적
    # 날짜 범위(오늘-N년 ~ 오늘)로 결정적으로 변환한다. 버킷 연수(1/3/5)는 상대 기간
    # 경로를 유지하도록 여기서 제외한다.
    years = _extract_backtest_relative_years(user_input)
    if years is not None and years not in (1, 3, 5) and 1 <= years <= 30:
        today = date.today()
        try:
            start_dt = today.replace(year=today.year - years)
        except ValueError:  # 2월 29일 보정
            start_dt = today.replace(year=today.year - years, day=28)
        return start_dt.isoformat(), today.isoformat()

    # '백테스트 24개월'처럼 개월 단위로 표현된 창도 동일하게 처리한다. 단 12개월 미만은
    # 백테스트 최소 기간(1년) 미달이므로 변환하지 않는다(→ unresolved로 남아 되묻기/안내).
    months = _extract_backtest_relative_months(user_input)
    if months is not None and 12 <= months <= 360:
        today = date.today()
        return _subtract_months(today, months).isoformat(), today.isoformat()
    return None, None


def _strip_amount_filter_phrases(compact: str) -> str:
    """거래대금/시가총액처럼 '억' 단위 펀더멘털 필터 표현을 비운다.

    초기자금 추출 정규식이 '거래대금 50억' 같은 필터 수치를 자본금으로 오인하지 않도록,
    금액 지표(market_cap/trading_value) 매치 구간을 공백으로 치환한 텍스트를 돌려준다.
    """
    for metric, patterns in _FUNDAMENTAL_PATTERN_SPECS:
        if metric not in _AMOUNT_METRICS:
            continue
        for pattern in patterns:
            compact = re.sub(pattern, " ", compact)
    return compact


# 자본금 cue에 바로 붙은 단위 없는 숫자(예: "초기자금 300", "자금은 300으로")를 잡는다.
# 한국 소매 투자 관례상 이런 맨숫자는 '만원'으로 읽는다("초기자금 300"=300만원).
# cue에 직접 붙은 숫자만 잡아 손절 10% 같은 다른 필드 수치를 자본금으로 오인하지 않는다.
_CAPITAL_BARE_RE = re.compile(
    r"(?:초기자금|자본금?|투자금|초기투자|시드|seed|자금)[은는이가을를도]?(\d+(?:\.\d+)?)(?![억천백만원\d])"
)


def _extract_capital_amount(user_input: str, *, allow_bare: bool = False) -> Optional[float]:
    """초기자금 금액(원)을 추출한다. 인식 못 하면 None(기본값은 호출자가 정한다).

    allow_bare=True면 자본금 cue에 바로 붙은 단위 없는 숫자를 만원으로 해석한다
    ('초기자금 300'=300만원). 일반 파싱에서는 RSI·임계값 같은 다른 수치를 자본금으로
    오인하지 않도록 단위가 명시된 표현만 인정한다(allow_bare=False).
    """
    compact = _compact(user_input)
    # 거래대금/시가총액 필터의 '억' 수치를 초기자금으로 오인하지 않도록 먼저 제거한다.
    compact = _strip_amount_filter_phrases(compact)
    match = re.search(r"(\d+(?:\.\d+)?)억(?:(\d+(?:\.\d+)?)천?만)?", compact)
    if match:
        capital = float(match.group(1)) * 100_000_000
        if match.group(2):
            capital += float(match.group(2)) * 10_000_000
        return capital

    match = re.search(r"(\d+(?:\.\d+)?)천만원?", compact)
    if match:
        return float(match.group(1)) * 10_000_000

    match = re.search(r"(\d+(?:\.\d+)?)백만원", compact)
    if match:
        return float(match.group(1)) * 1_000_000

    # '만원'뿐 아니라 '300만'처럼 원이 생략된 표현도 인식한다.
    match = re.search(r"(\d+(?:\.\d+)?)만원?", compact)
    if match:
        return float(match.group(1)) * 10_000

    if allow_bare:
        match = _CAPITAL_BARE_RE.search(compact)
        if match:
            return float(match.group(1)) * 10_000

    return None


def _extract_initial_capital(user_input: str) -> float:
    return _extract_capital_amount(user_input) or 10_000_000.0


# 초기자금 하한선(100만원). 300원 같은 비현실적 입력으로 백테스트가 무의미해지는 것을 막는
# 안전 가드. 다른 필드(종목 수 ge=1, 백테스트 기간 enum 최소 1y)는 이미 하한이 있어 자본금만 보강.
MIN_INITIAL_CAPITAL = 1_000_000.0
MIN_INITIAL_CAPITAL_NOTICE = "최소 초기자금은 100만원입니다. 입력하신 금액이 작아 100만원으로 설정했어요."


def enforce_initial_capital_minimum(parsed: ParsedStrategy) -> Optional[str]:
    """초기자금이 하한선 미만이면 하한선으로 보정하고 사용자 안내 문구를 반환한다(보정 없으면 None)."""
    if parsed.initial_capital < MIN_INITIAL_CAPITAL:
        parsed.initial_capital = MIN_INITIAL_CAPITAL
        return MIN_INITIAL_CAPITAL_NOTICE
    return None


# 그 외 설정값 하한선. max_positions는 추출기(0종목→1)와 스키마(ge=1)가 이미 1로 바닥을 깔아
# 별도 보정이 필요 없다. 비율(%) 필드는 자연스러운 양수 하한이 없어 0 이하면 제거(드롭)한다.
MIN_HOLD_PERIOD_DAYS = 1
MIN_RANKING_LOOKBACK_DAYS = 10  # 모멘텀/랭킹 기준 기간 하한(너무 짧으면 노이즈)
_RATIO_FIELD_LABELS = {
    "stop_loss_pct": "손절",
    "take_profit_pct": "익절",
    "trailing_stop_pct": "트레일링 스탑",
    "max_mdd_limit_pct": "MDD 한도",
}


def enforce_strategy_minimums(parsed: ParsedStrategy) -> list[str]:
    """파싱 결과의 설정값 하한선을 강제하고 보정 안내 문구 목록을 반환한다(없으면 빈 리스트).

    비현실적 입력(초기자금 300원, 0일 보유, 3일 모멘텀, 0% 손절 등)을 자동 보정/제거해
    백테스트가 무의미해지는 것을 막는다. 모든 파싱 경로(규칙/LLM/수정) 뒤에서 호출한다.
    """
    notices: list[str] = []

    capital_notice = enforce_initial_capital_minimum(parsed)
    if capital_notice:
        notices.append(capital_notice)

    if parsed.hold_period_days is not None and parsed.hold_period_days < MIN_HOLD_PERIOD_DAYS:
        parsed.hold_period_days = MIN_HOLD_PERIOD_DAYS
        notices.append("보유기간은 최소 1일입니다. 1일로 설정했어요.")

    if (
        parsed.ranking_lookback_days is not None
        and parsed.ranking_lookback_days < MIN_RANKING_LOOKBACK_DAYS
    ):
        parsed.ranking_lookback_days = MIN_RANKING_LOOKBACK_DAYS
        notices.append("모멘텀/랭킹 기준 기간은 최소 10일입니다. 10일로 설정했어요.")

    for field, label in _RATIO_FIELD_LABELS.items():
        value = getattr(parsed, field)
        if value is not None and value <= 0:
            setattr(parsed, field, None)
            notices.append(f"{label} 비율은 0%보다 커야 해서 적용하지 않았어요.")

    return notices


def _extract_execution_timing(user_input: str) -> str:
    compact = _compact(user_input)
    # 당일 종가 체결을 뜻하는 다양한 표현. '종가' 단독은 추세 필터('종가가 20일선 위')와
    # 혼동되므로, 체결/매매 동사와 결합한 형태만 current_close로 본다.
    current_close_cues = (
        "당일종가", "현재종가", "종가체결", "종가매매", "종가에체결",
        "종가에매수", "종가에매도", "종가로체결", "당일체결", "종가매수",
    )
    if any(cue in compact for cue in current_close_cues):
        return "current_close"
    return "next_open"


def _extract_rate(user_input: str, label: str, default: float) -> float:
    compact = _compact(user_input)
    match = re.search(rf"{label}(\d+(?:\.\d+)?)%", compact)
    return float(match.group(1)) if match else default


def _extract_trailing_stop_pct(user_input: str) -> Optional[float]:
    compact = _compact(user_input)
    patterns = [
        r"트레일링(?:스탑|스톱)?(\d+(?:\.\d+)?)%",
        # '최고가/고점/최고점/고가 대비 N% 하락/빠지면/떨어지면/밀리면' 모두 인식.
        r"(?:최고가|최고점|고점|고가)대비(\d+(?:\.\d+)?)%(?:하락|빠지|떨어|밀)",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return float(match.group(1))
    return None


def _extract_max_mdd_limit_pct(user_input: str) -> Optional[float]:
    compact = _compact(user_input)
    # 'MDD 30% 넘으면'·'낙폭 20% 이상'·'드로우다운 25% 도달'·'MDD 30% 한도'를 모두 인식한다.
    # 지표어(mdd/낙폭/드로우다운)와 숫자 사이 조사가 끼어도 잡고('mdd가30%'), 절 경계는 넘지
    # 않는다([^,]). 트리거 동사도 초과/이상/넘/한도뿐 아니라 도달/찍/발생까지 인정한다.
    trigger = r"(?:초과|이상|넘|한도|중단|도달|찍|발생|에서)"
    patterns = [
        rf"mdd(?:가|이|은|는)?\s*(\d+(?:\.\d+)?)%[^,]*?{trigger}",
        rf"(?:최대낙폭|낙폭)(?:이|은|는)?\s*(\d+(?:\.\d+)?)%[^,]*?{trigger}",
        rf"드로[우]?다운(?:이|은|는)?\s*(\d+(?:\.\d+)?)%[^,]*?{trigger}",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return float(match.group(1))
    return None


# ── 규칙 기반/스키마가 표현할 수 없는 '미지원 개념' ─────────────────────────────
# 결정적 추출기는 자신이 아는 슬롯만 채우고 나머지는 조용히 버리므로, 부분적으로만
# 파싱하고도 '성공'으로 착각해 잘못된 결과를 사용자에게 보여줄 수 있다(침묵 누락).
# 이를 막기 위해, 우리가 아직 구현하지 않은 '유한한 개념 목록'을 언급하면 규칙 기반은
# 자신을 신뢰하지 않고 None을 반환해 LLM 폴백/되묻기에 위임한다.
#   - 필러(연결어)를 끝없이 나열하는 잔여차감 방식과 반대로, '지원 안 하는 개념'만
#     열거하므로 목록이 유한하고 유지보수 가능하다('핵심만 결정적, 긴 꼬리는 LLM' 원칙).
#   - 패턴은 공백 제거·소문자화한 compact 입력 기준. 지원되는 개념(상대강도 랭킹 등)은
#     절대 포함하지 않는다(오폴백 방지).
_UNSUPPORTED_CONCEPT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("volatility", r"변동성"),
    ("cash_flow", r"현금흐름|영업활동현금|잉여현금|fcf|pcf"),
    ("cash_weight", r"현금[^,]{0,4}(?:비중|유지)"),
    ("dividend", r"배당"),
    # 흔한 퀀트 팩터지만 데이터 파이프라인이 없어 표현 불가 — 조용히 누락/유사 해석되는
    # 대신 안내한다. 지원 지표(영업이익률·순이익률·ROA·EV/EBITDA 등)는 절대 포함 금지(오폴백 방지).
    ("roic", r"roic|투하자본(?:이익|수익)률"),
    ("beta", r"베타"),
    ("interest_coverage", r"이자보상배[율률]"),
    ("quality_score", r"피오트로스키|알트만|[fz]-?score"),
    ("turnover_ratio", r"회전율"),
    ("buyback", r"자사주"),
    # ETF는 2026-07-19 정식 유니버스로 승격(universe=["ETF"], data/etf-master.json)되어
    # 미지원 목록에서 제거됐다 — 개념 구현 시 목록 제거 원칙. ETF×재무지표 충돌은
    # detect_etf_factor_conflict가 설명+대안 제안으로 담당한다.
    # 섹터/업종은 이제 지원 개념이지만, '지원 목록에 없는 업종'(예: '로봇 관련주')은 여전히
    # 표현 불가다. _mentioned_unsupported_concepts가 섹터 추출 성공 시 이 항목을 제외한다.
    # 맨 '관련/테마'까지 본다 — '로봇주 관련'·'로봇 테마'처럼 '관련주' 어순이 아니면 안내
    # 없이 전체 시장으로 백테스트되던 사고(업종 무관 표현은 아래 _SECTOR_AGNOSTIC_RE가 제외).
    ("sector", r"섹터|업종|관련|테마"),
    ("valuation_exit", r"밸류에이션"),
    ("relative_to_market", r"시장(?:보다|평균|대비)"),
    ("earnings", r"실적|어닝|컨센서스|목표주가"),
    # 뉴스/공시 등 재료(이벤트) 데이터 — 요청 전체가 뉴스 기반이면 intent.classifier가
    # UNSUPPORTED_FEATURE로 먼저 안내하고, 지원 지표와 섞인 혼합 요청만 여기로 온다.
    # 뉴스가 '조건'으로 쓰일 때만 잡는다 — "뉴스에 자주 나오는 강한 종목을 …" 같은 서두
    # flavor 언급(구체 규칙 동반)은 결정적 파싱을 유지한다(오폴백 방지).
    ("news", r"호재|악재|(?:뉴스|공시|루머|풍문|기사)[^,.]{0,6}(?:좋|나쁘|긍정|부정|기반|보고|분석|따라|필터)"),
    ("supply_demand", r"수급|외국인|기관(?:이|투자|순매)|공매도|신용잔고|유상증자|증자"),
    ("profitability_sign", r"흑자|적자"),
    ("ema_alignment", r"정배열|역배열"),
    ("partial_exit", r"분할매[도수]|절반[^,]{0,3}(?:익절|매도|청산)|일부[^,]{0,3}(?:익절|청산)"),
    ("new_low", r"신저가"),
    # 거래량 배수 임계값("평소보다 3배") — volume_spike는 OBV 크로스오버라 배수를 표현할 수
    # 없다(TechnicalSignal에 해당 필드 없음). 배수 없는 '거래량 급증'은 지원 개념이므로 제외.
    # 절 경계(쉼표/마침표)를 넘는 매칭 금지 — "거래량 급증, 3배 수익"의 '3배'는 배수 조건이 아니다.
    ("volume_multiple", r"(?:거래량|거래대금)[^,.]{0,10}\d+(?:\.\d+)?배|\d+(?:\.\d+)?배[^,.]{0,4}(?:거래량|거래대금)"),
)
_UNSUPPORTED_CONCEPT_RE = tuple(
    (name, re.compile(pattern)) for name, pattern in _UNSUPPORTED_CONCEPT_PATTERNS
)

# 사용자 안내용 개념 라벨. LLM 폴백으로 위임해도 ParsedStrategy 스키마 자체가 이 개념들을
# 표현할 수 없으므로, 조용히 누락/유사 해석되는 대신 notices 채널로 명시적으로 알린다.
_UNSUPPORTED_CONCEPT_LABELS: dict[str, str] = {
    "volatility": "변동성 조건",
    "cash_flow": "현금흐름(FCF/PCF 등) 조건",
    "cash_weight": "현금 비중 조건",
    "dividend": "배당 조건",
    "roic": "ROIC(투하자본이익률) 조건",
    "beta": "베타(시장 민감도) 조건",
    "interest_coverage": "이자보상배율 조건",
    "quality_score": "피오트로스키/알트만 점수 조건",
    "turnover_ratio": "회전율(재고·매출채권 등) 조건",
    "buyback": "자사주 매입 조건",
    "sector": "지원 목록에 없는 섹터/업종 조건",
    "valuation_exit": "밸류에이션 기반 청산",
    "relative_to_market": "시장 대비 상대 조건",
    "earnings": "실적/컨센서스 조건",
    "news": "뉴스/공시 등 재료 조건",
    "supply_demand": "수급(외국인·기관·공매도 등) 조건",
    "profitability_sign": "흑자/적자 조건",
    "ema_alignment": "정배열/역배열 조건",
    "partial_exit": "분할 매도/부분 청산",
    "new_low": "신저가 조건",
    "volume_multiple": "거래량 배수 조건(평소 대비 N배)",
}


# '업종 상관없이/모든 업종' 같은 무관 표현은 섹터 제한 언급이 아니다 — 미지원 안내 오탐 방지.
_SECTOR_AGNOSTIC_RE = re.compile(
    r"(?:업종|섹터|테마|분야)[은는이가]?(?:상관|구분|제한|관계)?없|(?:모든|전체?)(?:업종|섹터)|업종불문"
)


def _mentioned_unsupported_concepts(user_input: str) -> list[str]:
    """입력에 언급된 미지원 개념 이름들을 패턴 정의 순서대로 반환한다(없으면 빈 리스트).

    섹터/업종 언급은 지원 섹터로 결정적 추출에 성공하거나 업종 무관 표현이면 미지원으로
    치지 않는다('반도체 관련주'=지원, '로봇 관련주'=목록 밖 → LLM 위임 + 안내)."""
    compact = _compact(user_input)
    names = [name for name, rx in _UNSUPPORTED_CONCEPT_RE if rx.search(compact)]
    if "sector" in names and (
        _extract_sector(user_input) is not None or _SECTOR_AGNOSTIC_RE.search(compact)
    ):
        names.remove("sector")
    # 배당수익률/배당성향은 이제 지원 지표다 — 값이 추출되면 '배당' 미지원 안내를 뺀다
    # (섹터와 동형). '배당 성장/증가' 등 미추출 배당 개념은 그대로 안내 대상으로 남는다.
    if "dividend" in names and any(
        f.metric in ("dividend_yield", "payout_rate", "dividend_growth")
        for f in _extract_fundamental_filters(user_input)
    ):
        names.remove("dividend")
    return names


def _mentions_unsupported_concept(user_input: str) -> Optional[str]:
    """규칙 기반/스키마가 표현할 수 없는 개념을 언급하면 그 개념 이름을, 없으면 None."""
    names = _mentioned_unsupported_concepts(user_input)
    return names[0] if names else None


def build_unsupported_concept_notice(user_input: str) -> Optional[str]:
    """미지원 개념 언급 시 사용자에게 보여줄 안내 문구를 만든다(없으면 None).

    LLM 폴백조차 스키마 제약으로 이 개념들을 정확히 표현할 수 없으므로, '반영되지 않았거나
    다르게 해석됐을 수 있다'고 정직하게 알리고 전략 요약 확인을 유도한다(침묵 왜곡 방지).
    """
    names = _mentioned_unsupported_concepts(user_input)
    if not names:
        return None
    labels = ", ".join(_UNSUPPORTED_CONCEPT_LABELS.get(name, name) for name in names)
    return (
        f"'{labels}'은(는) 아직 직접 지원되지 않아요. "
        "전략에 반영되지 않았거나 다르게 해석됐을 수 있으니 전략 요약을 확인해 주세요."
    )


# ── Rule Parse Guard: 룰 파싱을 그대로 수락해도 되는지 판정 ──────────────────────
# REGEX가 매칭됐다는 사실은 올바른 파싱의 증거가 아니다. 룰 파서는 자신이 아는 슬롯만
# 채우므로, 질문·비교·정정·추천처럼 '실행 가능한 전략 서술'이 아닌 발화를 슬롯 일부가
# 매칭됐다는 이유로 전략으로 둔갑시킬 수 있다. 가드는 두 단계다.
#   1) 결정론 red-flag(아래): 전략 서술엔 거의 절대 등장하지 않는 고정밀 마커만 본다.
#      구어체 부정('말고')·트레일링('대비')처럼 정상 전략에 흔한 표현은 절대 넣지 않는다
#      (오폴백 방지 — feedback_nl_parser_hybrid 원칙). 미지원 개념 감지와 동형으로 None을
#      반환해 LLM 폴백/되묻기에 위임한다.
#   2) LLM judge(opt-in, NLStrategyParser._consult_rule_parse_guard): red-flag는 없지만
#      룰 파스가 원문을 다 설명 못 한 듯한 잔여가 남을 때만 호출해 accept/fallback을
#      semantic하게 판정한다('애매한 경우에만').
_RULE_GUARD_RED_FLAG_PATTERNS: tuple[tuple[str, str], ...] = (
    # 탐색/질문 — 선언형 전략 서술엔 물음표·질문 어미가 없다.
    ("question", r"\?|가능해|가능한가|가능할까|되나요|될까요|어때요|어떨까"),
    # 비교 요청 — 전략·종목 우열 비교는 추천에 준한다('대비'는 트레일링이라 제외).
    ("comparison", r"비교|뭐가더|어느쪽|어느게|versus|vs\."),
    # 정정 — 앞선 발화 취소/번복('아니라'는 'X가 아니라 Y' 설명형이라 단독 제외).
    ("correction", r"그게아니라|아니그게|정정|다시말하면|아까말한|취소할게"),
    # 추천/조언 요청 — 규제상 생성 금지(상류 intent도 처리하나 방어선으로 둔다).
    ("recommendation", r"추천|뭘사면|무엇을사|뭐사면"),
)
_RULE_GUARD_RED_FLAG_RE = tuple(
    (name, re.compile(pattern)) for name, pattern in _RULE_GUARD_RED_FLAG_PATTERNS
)


def _rule_parse_red_flag(user_input: str) -> Optional[str]:
    """룰 파싱이 잘못 해석했을 가능성이 매우 높은 고정밀 마커를 감지한다.

    질문/비교/정정/추천처럼 '실행 가능한 전략 서술'이 아닌 발화면 그 범주 이름을, 없으면
    None. 정상 전략에 흔한 구어체 부정('말고')·트레일링('대비')은 의도적으로 제외한다."""
    compact = _compact(user_input)
    for name, rx in _RULE_GUARD_RED_FLAG_RE:
        if rx.search(compact):
            return name
    return None


def _parse_rule_based_strategy(user_input: str) -> Optional[ParsedStrategy]:
    """
    Fast path for explicit, common strategies.

    This keeps the model unchanged, but avoids model inference when the prompt
    contains enough deterministic slots to build the same ParsedStrategy shape.
    Ambiguous prompts still fall through to the LLM.
    """
    # 표현할 수 없는 개념(변동성·현금흐름·섹터 분산 등)이 섞여 있으면, 지원되는 슬롯만
    # 채운 부분 파싱 결과를 조용히 내놓지 않고 None으로 LLM 폴백에 위임한다.
    if _mentions_unsupported_concept(user_input):
        return None

    # 질문·비교·정정·추천처럼 실행 가능한 전략이 아닌 발화는 슬롯이 일부 매칭돼도 수락하지
    # 않고 LLM 폴백/되묻기에 위임한다(REGEX 매칭 ≠ 올바른 파싱).
    if _rule_parse_red_flag(user_input):
        return None

    # 백테스트 기간·리밸런싱 주기 의도는 있는데 유효 값으로 못 푼 경우(예: '백테스트 1주일',
    # '10일마다 리밸런싱')도 조용히 기본값으로 떼우지 않고 위임한다(3-state UNRESOLVED).
    if _backtest_period_state(user_input) == "unresolved":
        return None
    if _rebalancing_period_state(user_input) == "unresolved":
        return None

    fundamental_filters = _extract_fundamental_filters(user_input)
    entry_signals, exit_signals = _extract_technical_signals(user_input)
    hold_period_days = _extract_hold_period_days(user_input)
    ranking_metric, ranking_lookback_days = _extract_ranking(user_input)

    has_entry = bool(fundamental_filters or entry_signals or ranking_metric)
    has_exit = bool(exit_signals or hold_period_days)
    has_risk_exit = bool(
        re.search(
            r"손절|익절|트레일링|최고가대비|mdd|낙폭|수익실현|수익확정|목표수익",
            _compact(user_input),
        )
    )
    # 펀더멘털 스크리닝·랭킹 전략은 정기 리밸런싱으로 회전하므로(명시적 청산/보유기간이 없어도)
    # 청산 요건을 충족한 것으로 본다. 'PBR<1 종목에 투자'처럼 가치주 스크리닝은 그 자체로 완결된
    # 전략인데, 청산을 따로 안 적었다는 이유로 LLM 폴백(콜드스타트 시 수십 초)으로 새지 않게 한다.
    # (기술적 진입 신호만 있고 청산이 없는 경우는 의도적으로 LLM에 위임한다 —
    #  test_technical_entry_without_exit_still_falls_back 참고.)
    periodic_rebalance = bool(ranking_metric or fundamental_filters)
    if not has_entry or not (has_exit or has_risk_exit or periodic_rebalance):
        return None

    rebalancing_period = _extract_rebalancing_period(user_input, hold_period_days)
    # 회전 수단이 없는 스크리닝 전략은 주기적 재선정이 필요하므로 주기 언급이 없으면 월간을
    # 기본값으로 둔다. 단, 사용자가 보유기간·청산 신호·리스크 청산(손절/익절/트레일링)을 직접
    # 지정했거나 리밸런싱을 명시적으로 거부("리밸런싱 없이 계속 보유")했다면 요청하지 않은
    # 리밸런싱을 임의로 주입하지 않는다(스크리닝은 매수 후 계속 보유로 해석).
    # (랭킹 전략의 회전은 리밸런싱이 구동해야 하므로 명시 거부여도 유지 — 엔진의 랭킹 재선정은
    # 달력 리밸런싱으로만 동작한다.)
    if (
        periodic_rebalance
        and rebalancing_period == "none"
        and (
            ranking_metric
            or not (has_exit or has_risk_exit or _mentions_rebalancing_negation(_compact(user_input)))
        )
    ):
        rebalancing_period = "monthly"
    # 랭킹 전략의 회전은 리밸런싱 주기로 구동한다. 모멘텀 설명에 섞인 'N개월'(예: '최근 3개월
    # 동안 오른')이 보유기간으로 오인되지 않도록, 리밸런싱이 있으면 보유기간을 비운다.
    # 단, '20일 보유'처럼 일 단위로 명시한 고정 보유기간은 모멘텀 룩백과 혼동될 수 없으므로
    # 그대로 보존한다(사용자가 명시한 보유기간 배지가 사라지지 않게).
    if ranking_metric and rebalancing_period != "none" and not _has_explicit_day_holding(user_input):
        hold_period_days = None

    parsed = ParsedStrategy(
        description=user_input,
        universe=_extract_explicit_universe(user_input) or ["KOSPI200"],
        sector=_extract_sector(user_input),
        fundamental_filters=fundamental_filters,
        entry_signals=entry_signals,
        exit_signals=exit_signals,
        ranking_metric=ranking_metric,
        ranking_lookback_days=ranking_lookback_days,
        max_positions=_extract_max_positions(user_input) or 10,
        hold_period_days=hold_period_days,
        rebalancing_period=rebalancing_period,
        stop_loss_pct=None,
        take_profit_pct=None,
        trailing_stop_pct=_extract_trailing_stop_pct(user_input),
        max_mdd_limit_pct=_extract_max_mdd_limit_pct(user_input),
        backtest_period=_extract_backtest_period(user_input) or "5y",
        initial_capital=_extract_initial_capital(user_input),
        execution_timing=_extract_execution_timing(user_input),
        fee_rate=_extract_rate(user_input, "수수료", 0.015),
        slippage_rate=_extract_rate(user_input, "슬리피지", 0.05),
    )
    return _apply_prompt_overrides(parsed, user_input)


# ── 수정 요청 fast-path: 인식 cue/필러/단위 ──────────────────────────────────
# 변경된 필드의 cue만 잔여 판정에서 차감한다(필드별, 표현별 정규식 증식 방지).
_MODIFY_FIELD_CUES: dict[str, list[str]] = {
    "stop_loss_pct": ["손절선", "손절라인", "손절", "스탑로스", "stoploss", "손실", "하락", "매도"],
    "take_profit_pct": ["목표수익률", "목표수익", "수익실현", "수익확정", "익절률", "익절", "takeprofit", "수익"],
    "trailing_stop_pct": ["트레일링스탑", "트레일링", "최고가대비", "trailingstop"],
    "max_mdd_limit_pct": ["최대낙폭", "낙폭", "드로우다운", "드로다운", "mdd"],
    "max_positions": ["동시보유", "maxpositions", "종목", "포지션", "최대", "총", "상위", "나눠"],
    "hold_period_days": ["보유기간", "보유", "들고", "홀딩", "가지고", "가져가", "지나면", "유지"],
    "rebalancing_period": ["리밸런싱", "리밸런스", "리밸", "재조정", "재선정", "rebalanc", "주기", "마다", "점검", "분기"],
    "initial_capital": ["초기자금", "투자금", "자본", "자금", "초기투자", "초기", "시드", "seed", "시작"],
    "universe": ["코스피200", "코스피", "코스닥", "kospi200", "kospi", "kosdaq", "대형주", "전체시장", "전체", "유니버스", "시장"],
    "entry_signals": [
        "진입신호", "진입조건", "진입기준", "매수신호", "매수조건", "매수기준",
        "진입", "매수", "이동평균", "이평", "골든크로스", "rsi", "macd",
        "신고가", "돌파", "반등", "이하",
    ],
    # 섹터/업종: 정본 섹터명+동의어(compact 형태, universe_pit 정본에서 동적 생성)와
    # 업종 지시 cue(_SECTOR_CUE와 동일 집합). sector가 changes에 있을 때만 차감된다.
    "sector": _sector_terms_longest_first()
    + ["관련", "테마", "업종", "섹터", "섹션", "분야", "종목", "주식", "중심", "위주", "주"],
    "backtest_period": ["백테스트", "기간", "최근", "테스트", "전체기간", "동안"],
    "backtest_start_date": ["백테스트", "테스트", "기간", "최근", "부터", "년", "월", "일"],
    "backtest_end_date": ["까지", "년", "월", "일"],
    # 펀더멘털 지표명·연산자·통상 수식어. 숫자/단위/필러는 공통 차감 규칙이 처리한다.
    "fundamental_filters": [
        "주가순자산비율", "주가수익비율", "주가순자산", "주가수익", "자기자본이익률",
        "주가매출액비율", "주가매출비율", "총자산이익률", "총자본이익률",
        "일평균거래대금", "거래대금", "시가총액", "시총", "부채비율", "부채",
        "유동비율", "당좌비율", "유보율", "순이익률", "매출총이익률", "영업이익률",
        "매출액증가율", "매출증가율", "영업이익증가율", "순이익증가율",
        # 마진/성장률 변형 철자(_FUNDAMENTAL_PATTERN_SPECS와 동기화 — 추출은 되는데 잔여로
        # 오판돼 fast-path가 LLM으로 새던 것 보정).
        "매출액총이익률", "매출액순이익률", "매출액영업이익률",
        "매출액성장률", "매출성장률", "영업이익성장률", "순이익성장률",
        "당기순이익증가율", "당기순이익성장률", "당기순이익",
        # 배당 계열·EV/EBITDA — 추출 지원 지표인데 cue 목록에서 누락돼 있었다.
        "배당수익률", "시가배당률", "배당률", "배당성향", "배당지급률",
        "배당성장률", "배당증가율", "배당성장", "배당증가",
        "이브이에비타", "기업가치", "ebitda", "에비타", "ev",
        "pbr", "per", "roe", "gpa", "psr", "roa",
        "이하", "미만", "이상", "초과", "이내",
        "저평가", "고평가", "우량", "가치주", "성장주", "종목", "주식", "조건", "필터",
    ],
}
# 필드 무관 일반 동사·조사·단위(항상 차감).
_MODIFY_FILLER = [
    "설정해줘", "설정해", "설정", "변경해줘", "변경", "바꿔줘", "바꿔주세요", "바꿔", "바꾸",
    "해주세요", "해줘", "주세요", "넣어줘", "넣어", "추가해줘", "추가", "포함해줘", "포함",
    "같이", "함께", "더해줘", "더해", "진행", "그대로", "대상",
    # '~만 테스트 해줘'류 실행 요청 동사. '백테스트'는 필드 cue(backtest_period)라 여기 아님
    # — 기간 변경이 아닌 문장에 '백테스트'가 남으면 '백'이 잔여로 남아 LLM으로 위임된다(보수적).
    "테스트",
    "빼줘", "빼주세요", "빼", "삭제", "없애줘", "없애", "제거해줘", "제거", "지워줘", "지워",
    "제한", "한도", "끄기", "끄고", "중단",
    # 값을 키우거나 줄이는 일반 조정 동사(필드 의미 없음, '바꿔/설정'과 동급으로 차감).
    # 예: "종목을 10개로 늘려줘", "손절을 5%로 줄여줘" → 값 변경은 필드 추출이 처리한다.
    "늘려주세요", "늘려줘", "늘려", "늘리", "줄여주세요", "줄여줘", "줄여", "줄이",
    "높여주세요", "높여줘", "높여", "높이", "낮춰주세요", "낮춰줘", "낮춰", "낮추",
    "올려주세요", "올려줘", "올려", "내려주세요", "내려줘", "내려", "조정해줘", "조정",
    "으로", "로", "만", "좀", "정도", "약", "더", "하고", "해",
    "을", "를", "은", "는", "이", "가", "의", "에", "도", "와", "과", "랑", "에서", "간", "동안",
]
_MODIFY_UNIT_FILLER = [
    "억", "천만원", "천만", "백만원", "만원", "만", "원", "개월", "달", "개", "일", "주", "년",
    "종목", "퍼센트", "프로", "배",
]
_MODIFY_CAPITAL_CUES = ["초기자금", "자금", "자본", "투자금", "초기투자", "시드", "seed"]
_MODIFY_REBALANCE_CUES = ["리밸런싱", "리밸런스", "리밸", "재조정", "재선정", "rebalanc"]
# 제거/해제 의도. '빼/제거/삭제/지워'(_DELETE_TERMS)에 더해 '없이/안 함/끄/중단'도 포함.
_REMOVE_INTENT_RE = re.compile(r"없|안하|안함|끄|중단|빼|제거|삭제|지워")
# 해제 시 null로 비워야 하는 Optional 필드의 cue(쉼표·공백 제거된 compact 기준).
_MODIFY_HOLD_CUES = ["보유기간", "보유일", "홀딩기간"]
_MODIFY_MDD_CUES = ["mdd", "최대낙폭", "낙폭", "드로우다운", "드로다운"]

# Only explicit replacement wording may discard the previous entry definition.
# Additive wording remains on the LLM path so it cannot be mistaken for replacement.
_ENTRY_SIGNAL_REPLACE_RE = re.compile(
    r"(?:진입|매수)(?:신호|조건|기준)[^,.]{0,48}(?:변경|바꾸|교체)"
)


def _modify_residual_is_clean(user_input: str, changed_fields) -> bool:
    """변경된 필드의 cue·숫자·필러·단위를 모두 차감한 뒤 남는 콘텐츠가 없으면 True.

    인식하지 못한 내용(예: '변동성 큰 종목 빼줘')이 남으면 False → LLM에 위임한다.
    표현별 정규식을 늘리는 대신 'cue/필러/단위 차감 후 잔여 콘텐츠' 한 규칙으로 일반화한다.
    """
    residual = _compact(user_input)
    residual = residual.replace("%", "")
    cues: list[str] = []
    for field in changed_fields:
        cues.extend(_MODIFY_FIELD_CUES.get(field, []))
    # 긴 키워드부터 제거(짧은 키워드가 긴 표현을 부분 절단하는 것 방지).
    # 숫자 제거보다 먼저다 — '2차전지' 같은 숫자 포함 cue가 조각나면 fast-path를 놓쳐
    # 단순 수정이 LLM 경로(수십 초)로 새어 나간다.
    for kw in sorted(set(cues) | set(_MODIFY_FILLER) | set(_MODIFY_UNIT_FILLER), key=len, reverse=True):
        residual = residual.replace(kw, "")
    residual = re.sub(r"-?\d+(?:\.\d+)?", "", residual)  # 숫자 제거
    return not re.search(r"[가-힣a-z0-9]", residual)


# ── Rule Parse Guard: LLM judge 호출용 잔여 커버리지 게이트 + 프롬프트 ──────────
# 룰 파싱이 원문 전체를 설명했는지 가늠하는 결정론 신호. 우리가 '아는 어휘'(슬롯 cue·
# 지표명·필러·단위·공통 동사)를 모두 차감하고도 의미 있는 잔여가 남으면, 룰 파스가 일부만
# 설명했을 수 있다 → LLM judge에게 accept/fallback을 물을 만큼 '애매'하다고 본다.
# 차감 어휘는 일부러 과하게(over-subtract) 잡아 잔여를 적게 만든다 — judge 과호출(지연)을
# 줄이는 보수적 방향. (이 게이트는 opt-in judge 경로에서만 쓰이므로 정밀도보다 안전이 우선.)
_RULE_GUARD_KNOWN_VOCAB: frozenset[str] = (
    frozenset(kw for cues in _MODIFY_FIELD_CUES.values() for kw in cues)
    | frozenset(_MODIFY_FILLER)
    | frozenset(_MODIFY_UNIT_FILLER)
    | frozenset({
        # 기술 지표/신호 어휘
        "골든크로스", "데드크로스", "골든", "데드", "크로스", "이동평균", "이평선", "이평",
        "rsi", "macd", "볼린저", "볼린저밴드", "스토캐스틱", "cci", "adx", "ema", "지수이동평균",
        "신고가", "52주", "박스권", "거래량", "급증", "폭발", "ai", "인공지능", "모델",
        "상승예측", "하락예측", "예측", "확률", "과매도", "과매수", "반등", "신호", "조건",
        # 랭킹/모멘텀
        "수익률", "상위", "상대강도", "모멘텀", "랭킹", "순위", "최근", "거래일",
        # 공통 동사/구조
        "전략", "주식", "매수", "매도", "진입", "청산", "사서", "사고", "사면", "팔고", "팔아",
        "팔면", "골라", "골라서", "편입", "들어가", "정리", "나오면", "발생", "돌파", "이탈",
        "이면", "이고", "이며", "그리고", "또는", "반대로", "다시", "기준", "정도", "이내",
        "중에서", "중", "에서", "으로", "하는", "하면", "한", "넣어", "써보", "해보", "싶어", "싶습니다",
    })
)
# 잔여가 이 글자 수 이상이면 '애매'로 보고 judge에 위임한다(한글 ~2-3단어 분량).
_RULE_GUARD_AMBIGUITY_MIN_CHARS = 6


def _rule_parse_unexplained(user_input: str) -> str:
    """룰 파싱이 설명하지 못한 잔여 텍스트(숫자·단위·알려진 어휘 차감 후 한글/영숫자)를 반환."""
    residual = _compact(user_input).replace("%", "")
    # 어휘 차감이 숫자 제거보다 먼저다 — '2차전지'·'52주'처럼 숫자를 품은 어휘가
    # 숫자 제거로 조각나('차전지') 잔여로 남으면 불필요한 LLM 검증(수 초~수십 초)이 발화된다.
    for kw in sorted(_RULE_GUARD_KNOWN_VOCAB, key=len, reverse=True):
        if kw:
            residual = residual.replace(kw, "")
    residual = re.sub(r"-?\d+(?:\.\d+)?", "", residual)
    return re.sub(r"[^가-힣a-z0-9]", "", residual)


RULE_PARSE_GUARD_PROMPT = """당신은 하이브리드 자연어 전략 파서의 Rule Parse Guard입니다.
REGEX/룰 기반 파서 결과를 그대로 수락해도 안전한지, 아니면 LLM 파서로 다시 해석해야 하는지
판단합니다. REGEX가 매칭됐다는 사실은 올바른 파싱의 증거가 아닙니다. 룰 파싱 결과가
사용자 발화 '전체의 핵심 의도'를 높은 정밀도로 설명할 때만 수락하세요.

입력으로 user_utterance와 selected_rule_parse(JSON)가 주어집니다. 최종 스키마는 한국 주식
백테스트 전략(ParsedStrategy)이며, 이 플랫폼은 투자 연구/시뮬레이션 전용입니다.

다음 중 하나라도 있으면 'fallback_llm_parse'를 선택하세요:
- 발화 일부만 매칭됨 / 의미 있는 문구가 설명되지 않은 채 남음
- 의도가 애매하거나 복수 의도가 동시에 가능함
- 부정·제외('아닌','빼고','제외','말고','대신'), 비교('비교','대비','어느 쪽'),
  탐색('가능해?','만약','왜','어때'), 정정('아니','정정','그게 아니라') 표현
- 추천·개인 맞춤형 조언·시장 전망·매수/매도 타이밍 요청
- selected_rule_parse가 사용자가 의도하지 않은 실행 액션을 유발할 수 있음
룰 파싱이 명확·완전·애매하지 않게 전체 의도를 설명할 때만 'accept_rule'.

반드시 아래 JSON만 반환하세요(다른 텍스트 금지):
{"decision": "accept_rule" | "fallback_llm_parse", "confidence": number, "reason": string}"""


def _build_guard_user_message(user_input: str, parsed: ParsedStrategy) -> str:
    return (
        f"user_utterance:\n{user_input}\n\n"
        f"selected_rule_parse:\n{json.dumps(parsed.model_dump(), ensure_ascii=False)}"
    )


def _extract_guard_decision(raw_text: str) -> str:
    """judge 응답에서 decision을 뽑는다. 파싱 실패/누락 시 보수적으로 'accept_rule'.

    (룰 파스는 이미 결정론 게이트를 통과했으므로, judge를 못 읽었다고 멀쩡한 빠른 경로를
    깨지 않는다 — judge는 추가 검증일 뿐 정확성의 baseline이 아니다.)"""
    try:
        data = json.loads(_extract_json_object(_trim_model_trailing_tokens(raw_text)))
    except (ValueError, json.JSONDecodeError):
        return "accept_rule"
    decision = str(data.get("decision", "")).strip()
    return "fallback_llm_parse" if decision == "fallback_llm_parse" else "accept_rule"


def _merge_fundamental_filters(
    existing: list[FundamentalFilter],
    extracted: list[FundamentalFilter],
) -> list[FundamentalFilter]:
    """같은 지표는 새 값으로 덮어쓰고, 새 지표는 추가한다(_merge_signals와 동형).

    "PBR 1 이하, PER 10 이하"처럼 새 펀더멘털 조건을 줄 때, 기존 다른 지표 조건은 보존하고
    같은 지표 조건만 갱신한다(예: 기존 PBR<2 → PBR<1로 교체).
    """
    merged = list(existing)
    index_by_metric = {f.metric: idx for idx, f in enumerate(merged)}
    for f in extracted:
        idx = index_by_metric.get(f.metric)
        if idx is None:
            merged.append(f)
            index_by_metric[f.metric] = len(merged) - 1
        elif merged[idx] != f:
            merged[idx] = f
    return merged


def _modify_rule_based(user_input: str, previous: dict) -> Optional[ParsedStrategy]:
    """수정 요청의 결정론 fast-path.

    단순 필드(손절/익절/트레일링/유니버스/종목수/보유기간/리밸런싱/초기자금/MDD/백테스트
    기간·날짜), 명시적인 진입 신호 교체와 숫자가 명시된 펀더멘털 조건(PBR/PER/ROE/
    부채비율/시총/거래대금)을 LLM 없이 처리한다. 인식 못 한 잔여 콘텐츠가 있으면 None을
    반환해 LLM 경로로 위임한다(핵심만 결정적, 긴 꼬리는 LLM). 기술적 신호 추가 같은 복합
    수정은 의도적으로 LLM에 맡긴다.
    """
    compact = _compact(user_input)
    changes: dict[str, object] = {}

    # 백테스트 기간·리밸런싱 주기 의도는 있는데 유효 값으로 못 푼 수정 요청(예: '백테스트
    # 1주일로 바꿔줘', '10일마다 리밸런싱으로')은 조용히 무시하지 않고 LLM에 위임한다(3-state).
    if _backtest_period_state(user_input) == "unresolved":
        return None
    if _rebalancing_period_state(user_input) == "unresolved":
        return None

    # 리스크 필드(손절/익절/트레일링) — 단일 진실 소스, 삭제 의도는 None으로 인코딩.
    changes.update(extract_risk_field_overrides(user_input))

    # 숫자가 명시된 펀더멘털 조건은 결정적 추출이 신뢰할 수 있으므로 LLM을 거치지 않는다.
    # ('PBR 낮은' 같은 정성 표현은 숫자가 없어 추출되지 않으므로 자연히 LLM/되묻기로 빠진다.)
    extracted_filters = _extract_fundamental_filters(user_input)
    if extracted_filters:
        existing_filters = [
            FundamentalFilter(**f) for f in (previous.get("fundamental_filters") or [])
        ]
        merged_filters = _merge_fundamental_filters(existing_filters, extracted_filters)
        changes["fundamental_filters"] = [f.model_dump() for f in merged_filters]

    extracted_entry, _ = _extract_technical_signals(user_input)
    if extracted_entry and _ENTRY_SIGNAL_REPLACE_RE.search(compact):
        changes["entry_signals"] = [signal.model_dump() for signal in extracted_entry]
        # Ranking is also rendered and executed as an entry definition. Leaving it in place
        # would keep the previous "N-day return leaders" entry beside the requested signal.
        changes["ranking_metric"] = None
        changes["ranking_lookback_days"] = None

    universe = _extract_explicit_universe(user_input)
    if universe is not None:
        changes["universe"] = universe

    # 섹터/업종 제한('반도체 섹터 종목만'/'로봇 섹터도 추가'/'반도체 업종은 빼줘').
    # 추가=합집합·개별 삭제·전체 해제까지 통합 판정(FR-STR-066 ⑦). universe는 수정 경로
    # 원칙대로 보존한다(양시장 기본 확장은 최초 파싱에만 — preserve_universe).
    sector_changed, sector_value = _sector_change_from_utterance(user_input, previous.get("sector"))
    if sector_changed:
        changes["sector"] = sector_value

    max_positions = _extract_max_positions(user_input)
    if max_positions is not None:
        changes["max_positions"] = max_positions

    removing = bool(_REMOVE_INTENT_RE.search(compact))

    max_mdd = _extract_max_mdd_limit_pct(user_input)
    if max_mdd is not None:
        changes["max_mdd_limit_pct"] = max_mdd
    elif removing and any(cue in compact for cue in _MODIFY_MDD_CUES):
        changes["max_mdd_limit_pct"] = None  # 해제: null로 비움(Optional)

    hold = _extract_hold_period_days(user_input)
    if hold is not None:
        changes["hold_period_days"] = hold
    elif removing and any(cue in compact for cue in _MODIFY_HOLD_CUES):
        changes["hold_period_days"] = None  # 해제: null로 비움(Optional)

    if any(cue in compact for cue in _MODIFY_CAPITAL_CUES):
        # 자본금 cue가 있을 때만 단위 없는 맨숫자도 만원으로 해석한다("초기자금 300으로"=300만원).
        # 못 풀면(금액 미언급) None → 자본금을 건드리지 않고, 잔여가 남으면 LLM으로 위임된다.
        amount = _extract_capital_amount(user_input, allow_bare=True)
        if amount is not None:
            changes["initial_capital"] = amount

    if any(cue in compact for cue in _MODIFY_REBALANCE_CUES):
        rebalancing = _extract_rebalancing_period(user_input, hold)
        if rebalancing != "none":
            changes["rebalancing_period"] = rebalancing
        elif removing:
            changes["rebalancing_period"] = "none"

    period = _extract_backtest_period(user_input)
    if period is not None:
        changes["backtest_period"] = period

    start_date, end_date = _extract_backtest_dates(user_input)
    if start_date is not None:
        changes["backtest_start_date"] = start_date
    if end_date is not None:
        changes["backtest_end_date"] = end_date

    if not changes:
        return None
    if not _modify_residual_is_clean(user_input, changes.keys()):
        return None

    merged = {**previous}
    for field, value in changes.items():
        merged[field] = value  # 리스크 삭제는 None으로 인코딩됨(의도적)
    # 수정 모드이므로 신호 재검증을 건너뛴다(LLM 수정 경로와 동일). 짧은 수정 프롬프트
    # ("종목 20개로")로 재검증하면 언급 안 된 기존 진입/청산 신호(RSI 등)를 잘못 떨군다.
    # preserve_universe: 섹터 언급이 기존 universe를 양시장으로 넓히지 않게 한다(수정 경로 원칙).
    return _apply_prompt_overrides(
        ParsedStrategy.model_validate(merged), user_input,
        skip_signal_validation=True, preserve_universe=True,
    )


def _build_fallback_strategy(user_input: str) -> ParsedStrategy:
    """Safe non-LLM fallback when structured model output is incomplete."""
    entry_signals, exit_signals = _extract_technical_signals(user_input)
    hold_period_days = _extract_hold_period_days(user_input)
    ranking_metric, ranking_lookback_days = _extract_ranking(user_input)
    parsed = ParsedStrategy(
        description=user_input,
        universe=_extract_explicit_universe(user_input) or ["KOSPI200"],
        fundamental_filters=_extract_fundamental_filters(user_input),
        entry_signals=entry_signals,
        exit_signals=exit_signals,
        ranking_metric=ranking_metric,
        ranking_lookback_days=ranking_lookback_days,
        max_positions=_extract_max_positions(user_input) or 10,
        hold_period_days=hold_period_days,
        rebalancing_period=_extract_rebalancing_period(user_input, hold_period_days),
        stop_loss_pct=None,
        take_profit_pct=None,
        trailing_stop_pct=_extract_trailing_stop_pct(user_input),
        max_mdd_limit_pct=_extract_max_mdd_limit_pct(user_input),
        backtest_period=_extract_backtest_period(user_input) or "5y",
        initial_capital=_extract_initial_capital(user_input),
        execution_timing=_extract_execution_timing(user_input),
        fee_rate=_extract_rate(user_input, "수수료", 0.015),
        slippage_rate=_extract_rate(user_input, "슬리피지", 0.05),
    )
    return _apply_prompt_overrides(parsed, user_input)


def _merge_signals(
    existing: list[TechnicalSignal],
    extracted: list[TechnicalSignal],
) -> list[TechnicalSignal]:
    """Deterministic extraction takes precedence over same-kind existing signals."""
    merged = list(existing)
    index_by_key = {
        (signal.indicator, signal.signal_type): idx
        for idx, signal in enumerate(merged)
    }

    for sig in extracted:
        key = (sig.indicator, sig.signal_type)
        existing_idx = index_by_key.get(key)
        if existing_idx is None:
            merged.append(sig)
            index_by_key[key] = len(merged) - 1
            continue

        if merged[existing_idx] != sig:
            merged[existing_idx] = sig

    return merged


_DELETE_TERMS = ["삭제", "없애", "제거", "지워", "빼줘", "빼"]

# 리스크 % 값을 표현별 정규식 없이 '필드 키워드 + 퍼센트' 한 규칙으로 추출하기 위한 cue.
# 키워드와 숫자가 인접하지 않아도("익절 비율을 30%로"), 같은 절(다른 % 미포함) 안이면 연결한다.
_TAKE_PROFIT_CUE = r"(?:익절|수익실현|수익확정|목표수익)"
_STOP_LOSS_CUE = r"손절"
_TRAILING_CUE = r"(?:트레일링(?:스탑|스톱)?|(?:최고가|최고점|고점|고가)대비)"
# 다른 리스크 필드 키워드를 사이에 두고는 연결하지 않아 오인식("손절 없이 익절 10%")을 막는다.
_STOP_LOSS_BLOCK = r"익절|수익실현|수익확정|목표수익|트레일링"
_TAKE_PROFIT_BLOCK = r"손절|손실|트레일링"
_TRAILING_BLOCK = r"손절|익절"


# "매도/청산" 외에 구어체 "팔고/팔아/팔자/팔래/팔면/팔게/팔까"와 "정리/처분/매각"도 매도
# 동사로 인정한다(_SELL_V로 일원화 — 품사 변화/유의어를 한 곳에서 관리).
_SELL_VERB = _SELL_V

# 필드 키워드가 없는 동사형 표현(주로 최초 입력) 폴백 패턴.
_TAKE_PROFIT_VERB_PATTERNS = (
    rf"수익이?(\d+(?:\.\d+)?)%이상.*?{_SELL_VERB}",
    rf"(\d+(?:\.\d+)?)%이상수익.*?{_SELL_VERB}",
    rf"(\d+(?:\.\d+)?)%수익.*?{_SELL_VERB}",
    rf"수익이?(\d+(?:\.\d+)?)%.*?{_SELL_VERB}",
)
_STOP_LOSS_VERB_PATTERNS = (
    rf"손실이?(\d+(?:\.\d+)?)%이상.*?{_SELL_V}",
    rf"(\d+(?:\.\d+)?)%이상하락.*?{_SELL_V}",
    rf"(\d+(?:\.\d+)?)%하락.*?{_SELL_V}",
    rf"-(\d+(?:\.\d+)?)%.*?{_SELL_V}",
)


def _match_risk_pct(compact: str, cue: str, blocker: str = "") -> Optional[float]:
    """필드 키워드(cue)와 퍼센트가 떨어져 있어도 같은 절 안이면 값을 추출한다.

    표현별 패턴을 늘리는 대신 '키워드 ~ %' / '% ~ 키워드' 두 방향 한 규칙으로 일반화한다.
    두 방향이 모두 매치되면 키워드와 %가 가장 가까운(사이 글자 수가 적은) 쪽을 택한다.
    "-15%에 손절하고 30%에 익절"처럼 한 절에 두 % 값이 있을 때, 손절이 더 먼 30%를
    끌어오지 않고 바로 앞의 -15%를 잡게 하기 위함이다.
    blocker(다른 리스크 필드 키워드)가 사이에 끼면 연결하지 않아 오인식을 막는다.
    compact는 공백 제거·소문자화된 입력이다."""
    # 절(쉼표) 경계를 넘지 않게 ','도 제외 — "수익이 30% 나면 익절, 15% 빠지면 손절"에서
    # 익절이 다른 절의 15%를 끌어오지 않도록 한다. 사이 글자(gap)를 캡처해 거리를 잰다.
    gap = rf"((?:(?!{blocker})[^%,])*?)" if blocker else r"([^%,]*?)"
    best_value: Optional[float] = None
    best_gap: Optional[int] = None
    candidates = (
        (rf"{cue}{gap}-?(\d+(?:\.\d+)?)%", 2, 1),   # 키워드 ~ %  (num=g2, gap=g1)
        (rf"-?(\d+(?:\.\d+)?)%{gap}{cue}", 1, 2),   # % ~ 키워드  (num=g1, gap=g2)
    )
    for pattern, num_grp, gap_grp in candidates:
        for match in re.finditer(pattern, compact):
            gap_len = len(match.group(gap_grp))
            if best_gap is None or gap_len < best_gap:
                best_value, best_gap = float(match.group(num_grp)), gap_len
    return best_value


def _first_pct_match(compact: str, patterns: tuple[str, ...]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return float(match.group(1))
    return None


# 값과 키워드 사이가 조사(에·에서·로·으로)뿐이면 '바로 붙었다'(gap 0)고 본다.
# "15%에 손절"·"30%로 익절"에서 조사 1글자 때문에 더 먼 값으로 밀리지 않게 한다.
_RISK_CONNECTOR_RE = re.compile(r"^(?:에서?|으?로)?$")


def _risk_pct_candidates(compact: str, cue: str, blocker: str) -> list[tuple[float, int, int]]:
    """cue 키워드와 연결된 모든 (값, %위치, gap) 후보를 반환한다. gap은 조사만 낀 경우 0."""
    gap = rf"((?:(?!{blocker})[^%,])*?)" if blocker else r"([^%,]*?)"
    cands: list[tuple[float, int, int]] = []
    for pattern, num_grp, gap_grp in (
        (rf"{cue}{gap}-?(\d+(?:\.\d+)?)%", 2, 1),   # 키워드 ~ %
        (rf"-?(\d+(?:\.\d+)?)%{gap}{cue}", 1, 2),   # % ~ 키워드
    ):
        for m in re.finditer(pattern, compact):
            seg = m.group(gap_grp)
            gap_len = 0 if _RISK_CONNECTOR_RE.match(seg) else len(seg)
            cands.append((float(m.group(num_grp)), m.start(num_grp), gap_len))
    return cands


def _assign_sl_tp(compact: str) -> dict[str, float]:
    """손절·익절 %값을 함께 1:1로 귀속한다. 값이 키워드 앞·뒤 어디 와도 되며, 두 필드가 같은 %를
    다툴 때 '최대한 많이 배정 + 총 gap 최소'가 되는 조합을 고른다(그리디가 아니라 전역 최적).
    → "10% 손절 20% 익절"·"익절 30% 손절 15%"에서 한 필드가 상대의 %를 훔쳐 다른 필드가
      비는 오귀속을 막는다."""
    sl_opts: list[Optional[tuple[float, int, int]]] = list(
        _risk_pct_candidates(compact, _STOP_LOSS_CUE, _STOP_LOSS_BLOCK)) + [None]
    tp_opts: list[Optional[tuple[float, int, int]]] = list(
        _risk_pct_candidates(compact, _TAKE_PROFIT_CUE, _TAKE_PROFIT_BLOCK)) + [None]
    best_score: Optional[tuple[int, int]] = None
    best: tuple = (None, None)
    for a in sl_opts:
        for b in tp_opts:
            if a and b and a[1] == b[1]:
                continue  # 같은 % 위치를 두 필드가 동시에 못 가진다
            assigned = (1 if a else 0) + (1 if b else 0)
            total_gap = (a[2] if a else 0) + (b[2] if b else 0)
            score = (assigned, -total_gap)  # 많이 배정 우선, 그다음 gap 최소
            if best_score is None or score > best_score:
                best_score, best = score, (a, b)
    out: dict[str, float] = {}
    if best[0] is not None:
        out["stop_loss_pct"] = best[0][0]
    if best[1] is not None:
        out["take_profit_pct"] = best[1][0]
    return out


def extract_risk_field_overrides(user_input: str) -> dict[str, Optional[float]]:
    """프롬프트에서 '규칙 기반으로 결정적으로' 바뀐 리스크 필드만 추출한다.

    이것이 리스크 필드(손절/익절/트레일링)의 **단일 진실 소스**다. 값이 잡히면
    {field: value}, 삭제 의도면 {field: None}, 못 찾으면 키 없음.
    파서(_apply_prompt_overrides)와 API가 공유하여, 프론트가 자체 정규식으로
    리스크 변경을 다시 추측하지 않고 이 결과를 그대로 신뢰하게 한다.
    """
    compact = _compact(user_input)
    is_deleting = any(kw in compact for kw in _DELETE_TERMS)
    out: dict[str, Optional[float]] = {}

    # ── 손절·익절: 키워드+% 는 두 필드를 함께 1:1 귀속(중간 % 오귀속 방지), 없으면 동사형 폴백 ──
    joint = _assign_sl_tp(compact)

    # 익절(take_profit)
    if is_deleting and any(kw in compact for kw in ["익절", "takeprofit", "익절률"]):
        out["take_profit_pct"] = None
    else:
        value = joint.get("take_profit_pct")
        if value is None:
            value = _first_pct_match(compact, _TAKE_PROFIT_VERB_PATTERNS)
        if value is not None:
            out["take_profit_pct"] = value

    # 손절(stop_loss): 키워드 → "손실·하락+매도", "-N% 매도" 폴백
    if is_deleting and any(kw in compact for kw in ["손절", "stoploss", "스탑로스"]):
        out["stop_loss_pct"] = None
    else:
        value = joint.get("stop_loss_pct")
        if value is None:
            value = _first_pct_match(compact, _STOP_LOSS_VERB_PATTERNS)
        if value is not None:
            out["stop_loss_pct"] = value

    # ── 트레일링 스탑: "트레일링/최고가대비" 키워드 + % ──
    if is_deleting and any(kw in compact for kw in ["트레일링", "trailingstop", "최고가대비", "고점대비", "최고점대비", "고가대비"]):
        out["trailing_stop_pct"] = None
    else:
        value = _match_risk_pct(compact, _TRAILING_CUE, blocker=_TRAILING_BLOCK)
        if value is not None:
            out["trailing_stop_pct"] = value

    return out


_RISK_OVERRIDE_FIELDS = ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct")


def synthesize_risk_overrides(
    user_input: str,
    parsed: "ParsedStrategy",
    previous_parsed: Optional[dict] = None,
) -> Optional[dict[str, Optional[float]]]:
    """프론트가 신뢰할 '바뀐 리스크 필드' 단일 진실 소스를 합성한다.

    1차로 결정적 추출(extract_risk_field_overrides)을 쓰고, 그것이 놓친 구어체
    ("10% 이익 나면 팔아줘")는 파서(LLM 포함)가 previous 대비 실제로 바꾼 값으로
    보완한다. 그렇지 않으면 LLM이 올바로 해석한 risk 값이 프론트의 결정적 게이트에
    막혀 사라진다. 결정적 추출이 이미 처리한 필드(삭제 None 포함)는 그대로 둔다.
    """
    overrides = extract_risk_field_overrides(user_input)
    baseline = previous_parsed or {}
    for field in _RISK_OVERRIDE_FIELDS:
        if field in overrides:
            continue
        new_val = getattr(parsed, field, baseline.get(field))
        if new_val != baseline.get(field):
            overrides[field] = new_val
    return overrides or None


# ── 코치 맥락 리스크 해석 (프론트 inferPendingRiskChange 이관) ────────────────────────
# [FR-STR-019e] 코치가 특정 리스크 필드 설정을 권한 뒤("익절 설정을 추천드립니다"),
# 사용자가 "10%"처럼 필드를 안 밝히고 답하면 그 값을 코치가 물은 필드로 귀속한다. 예전엔
# 프론트가 코치 텍스트를 정규식으로 재판정해 백엔드 파스 결과에 얹었으나(프론트가 백엔드
# 판단에 관여), 코치 맥락은 백엔드가 previous_coach_text로 받아 백엔드가 판단하도록 이관했다.
_COACH_RISK_FIELD_PATTERNS: dict[str, "re.Pattern[str]"] = {
    "stop_loss_pct": re.compile(r"손절|손실|stop\s*loss", re.IGNORECASE),
    "take_profit_pct": re.compile(
        r"익절|목표\s*(?:수익|이익)|수익\s*실현|수익\s*확정|take\s*profit", re.IGNORECASE),
    "trailing_stop_pct": re.compile(r"트레일링|최고가\s*대비|trailing", re.IGNORECASE),
    "max_mdd_limit_pct": re.compile(r"\bmdd\b|낙폭|드로우다운", re.IGNORECASE),
}
_RISK_ANSWER_RE = re.compile(
    r"정해|설정|해줘|해주세요|조정|로\s*(?:해|바꿔|설정|조정)|으로\s*(?:해|바꿔|설정|조정)|추가|적용",
    re.IGNORECASE)
_RISK_BARE_PCT_RE = re.compile(r"^\s*\d+(?:\.\d+)?\s*%\s*$")
_RISK_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _extract_answer_percentage(text: str) -> Optional[float]:
    m = _RISK_PCT_RE.search(text or "")
    if not m:
        return None
    v = float(m.group(1))
    return v if 0 < v <= 100 else None


def _infer_risk_field_from_coach(coach_text: str, previous_parsed: Optional[dict]) -> Optional[str]:
    """코치 문장이 지목한 리스크 필드를 고른다. 하나만 언급되면 그 필드, 여러 개면 아직
    설정 안 된(미설정) 필드가 하나일 때 그것(예: 손절은 재확인·익절은 신규 권유)."""
    mentioned = [f for f, p in _COACH_RISK_FIELD_PATTERNS.items() if p.search(coach_text)]
    if len(mentioned) == 1:
        return mentioned[0]
    prev = previous_parsed or {}
    unset = [f for f in mentioned if not isinstance(prev.get(f), (int, float))]
    return unset[0] if len(unset) == 1 else None


def resolve_coach_context_risk(
    user_input: str, coach_text: Optional[str], previous_parsed: Optional[dict],
) -> Optional[tuple[str, float]]:
    """코치 맥락으로 필드 없는 퍼센트 답변을 리스크 필드에 귀속한다. (필드, 값) 또는 None.

    프롬프트가 이미 리스크 필드를 명시했으면(결정적 추출이 잡음) 일반 파서가 처리하므로 None."""
    if not coach_text:
        return None
    if extract_risk_field_overrides(user_input):  # 프롬프트가 필드를 명시함 → 추론 불필요
        return None
    pct = _extract_answer_percentage(user_input)
    if pct is None:
        return None
    if not (_RISK_ANSWER_RE.search(user_input) or _RISK_BARE_PCT_RE.match(user_input)):
        return None
    field = _infer_risk_field_from_coach(coach_text, previous_parsed)
    return (field, pct) if field else None


def _apply_prompt_overrides(
    parsed: ParsedStrategy, user_input: str, *,
    skip_signal_validation: bool = False, preserve_universe: bool = False,
) -> ParsedStrategy:
    updates: dict[str, object] = {}
    # LLM이 description을 빼먹어 스키마 복구(_repair_llm_schema_drift)가 빈 문자열로
    # 채운 경우, 원문을 그대로 넣는다(필드 정의: "사용자가 입력한 원문 전략 설명").
    if not parsed.description.strip():
        updates["description"] = user_input
    explicit_universe = _extract_explicit_universe(user_input)
    if explicit_universe is not None:
        updates["universe"] = explicit_universe

    # 섹터/업종 제한도 결정적으로 판정해 LLM이 놓쳐도 보장한다. 시장 언급 없는 섹터 전략은
    # 특정 시장이 아니라 '그 업종 전체'가 자연스러운 해석이므로 양시장을 기본으로 한다
    # (KOSPI200 기본값이면 시총 상위 200 ∩ 섹터로 과도하게 좁아진다). 언급 없으면 기존 값 유지.
    # preserve_universe(수정 경로): 기존 universe를 보존하고 섹터만 얹는다(FR-STR-066 ③ 제외).
    # 통합 판정(_sector_change_from_utterance)이라 삭제 발화("반도체 업종은 빼줘")를
    # _extract_sector 재추출로 되살리지 않는다(FR-STR-066 ⑦ — 선행 재주입 버그 수정).
    sector_changed, sector_value = _sector_change_from_utterance(user_input, parsed.sector)
    if sector_changed:
        updates["sector"] = sector_value
        if sector_value is not None and explicit_universe is None and not preserve_universe:
            updates["universe"] = ["KOSPI", "KOSDAQ"]

    # ── ETF 유니버스 정규화 ──
    # model_copy(update=...)는 검증기를 다시 돌리지 않으므로 _normalize_etf_universe와
    # 동일한 계약(ETF 단독·sector 비움)을 여기서도 결정적으로 강제한다. 테마/상품명
    # ("반도체 ETF"·"KODEX 200")은 ETF 마스터 이름과의 자기검증 매칭으로 추출한다.
    effective_universe = updates.get("universe", parsed.universe)
    if "ETF" in (effective_universe or []):
        from engine.universe_pit import extract_etf_theme
        updates["universe"] = ["ETF"]
        updates["sector"] = None
        theme = extract_etf_theme(user_input)
        if theme is not None:
            updates["etf_theme"] = theme

    # 리스크 필드(손절/익절/트레일링)는 단일 진실 소스에서 가져온다.
    updates.update(extract_risk_field_overrides(user_input))

    # 상대강도(수익률 순위) 랭킹도 프롬프트에서 결정적으로 추출(LLM이 놓쳐도 보장).
    # 언급이 없으면 기존 값을 덮어쓰지 않는다(수정 모드 보호).
    ranking_metric, ranking_lookback_days = _extract_ranking(user_input)
    if ranking_metric is not None:
        updates["ranking_metric"] = ranking_metric
        updates["ranking_lookback_days"] = ranking_lookback_days

    # 명시적 백테스트 연도 범위('2002년부터 2005년까지')를 결정적으로 추출.
    # 언급이 없으면 기존 값을 덮어쓰지 않는다(수정 모드 보호).
    start_date, end_date = _extract_backtest_dates(user_input)
    if start_date is not None:
        updates["backtest_start_date"] = start_date
    if end_date is not None:
        updates["backtest_end_date"] = end_date

    # 백테스트 기간('3년만 하자')도 결정적으로 추출해 LLM 값을 덮어쓴다.
    # 언급이 없으면 기존 값을 유지한다(수정 모드 보호).
    backtest_period = _extract_backtest_period(user_input)
    if backtest_period is not None:
        updates["backtest_period"] = backtest_period

    # ── 포트폴리오/리스크 한도 필드 결정적 보정 ──
    # 규칙 기반 fast-path가 처리하지 못해 LLM 폴백으로 새는 복잡한 프롬프트의 경우, LLM이
    # 이 필드들(종목수/보유기간/리밸런싱/MDD/자본금/체결시점/수수료)을 자주 틀린다. 프롬프트에
    # '명시적으로' 값이 있을 때만 결정적 추출로 덮어써, LLM 오류를 보정한다(기본값 클로버 방지).
    max_positions = _extract_max_positions(user_input)
    if max_positions is not None:
        updates["max_positions"] = max_positions

    max_mdd = _extract_max_mdd_limit_pct(user_input)
    if max_mdd is not None:
        updates["max_mdd_limit_pct"] = max_mdd

    # 보유기간: 랭킹 전략에서는 모멘텀 룩백('최근 3개월')이 보유기간으로 오인되므로,
    # 일(日) 단위로 명시한 경우에만 덮어쓴다(규칙 기반과 동일한 가드).
    hold = _extract_hold_period_days(user_input)
    if hold is not None and (ranking_metric is None or _has_explicit_day_holding(user_input)):
        updates["hold_period_days"] = hold

    rebalancing = _extract_rebalancing_period(user_input, hold)
    if rebalancing != "none":
        updates["rebalancing_period"] = rebalancing

    compact_in = _compact(user_input)
    capital_cue = any(cue in compact_in for cue in _MODIFY_CAPITAL_CUES)
    # cue가 있으면 단위 없는 맨숫자도 만원으로 해석한다(allow_bare). 금액을 못 풀면(None)
    # 자본금을 건드리지 않는다 — 기본값(10M)과 충돌하던 '!= 10_000_000' 가드를 None 체크로 대체.
    capital = _extract_capital_amount(user_input, allow_bare=capital_cue)
    if capital is not None:
        updates["initial_capital"] = capital

    if _extract_execution_timing(user_input) == "current_close":
        updates["execution_timing"] = "current_close"

    if "수수료" in compact_in:
        updates["fee_rate"] = _extract_rate(user_input, "수수료", 0.015)
    if "슬리피지" in compact_in:
        updates["slippage_rate"] = _extract_rate(user_input, "슬리피지", 0.05)

    # ── Step 1: LLM 환각 신호 제거 (프롬프트에 언급되지 않은 지표 제거) ──
    # Skip signal revalidation for deterministic modifications because short prompts would drop
    # previously validated signals that are intentionally not repeated by the user.
    if not skip_signal_validation:
        validated_entry = _validate_signals(list(parsed.entry_signals), user_input)
        validated_exit = _validate_signals(list(parsed.exit_signals), user_input)
        if len(validated_entry) != len(parsed.entry_signals):
            updates["entry_signals"] = validated_entry
        if len(validated_exit) != len(parsed.exit_signals):
            updates["exit_signals"] = validated_exit

        # A qualitative metric has no executable threshold. Keep only filters that can be
        # grounded in explicit values so an LLM cannot silently substitute another metric.
        qualitative_metrics = _detect_qualitative_metrics(compact_in)
        if qualitative_metrics:
            explicit_filters = _extract_fundamental_filters(user_input)
            explicit_metric_names = {item.metric for item in explicit_filters}
            qualitative_metric_names = {
                _QUALITATIVE_KEY_TO_METRIC[key]
                for _, _, _, key in qualitative_metrics
            }
            if qualitative_metric_names - explicit_metric_names:
                updates["fundamental_filters"] = explicit_filters

    # ── Step 2: deterministic 추출 & 병합 ──
    extracted_entry, extracted_exit = _extract_technical_signals(user_input)
    current_entry = updates.get("entry_signals", list(parsed.entry_signals))
    current_exit = updates.get("exit_signals", list(parsed.exit_signals))
    if extracted_entry:
        updates["entry_signals"] = _merge_signals(current_entry, extracted_entry)
    if extracted_exit:
        updates["exit_signals"] = _merge_signals(current_exit, extracted_exit)

    if not updates:
        return parsed
    return parsed.model_copy(update=updates)


# 상대강도(수익률 순위) 랭킹 의도 감지용 cue — "수익률 높은 상위 N종목" 류.
# 이 선정 방식은 종목 간 횡단면 순위라 현재 엔진(종목별 신호/필터)으로 표현 불가하다.
_RELATIVE_STRENGTH_RANKING_CUES = (
    r"수익률.{0,6}(?:상위|높은|좋은|top|랭킹|순)",
    r"(?:상위|높은|좋은).{0,6}수익률",
    r"등락률.{0,6}(?:상위|높은|순)",
    r"수익률.{0,4}(?:순위|랭킹)",
    r"상대강도",
    r"모멘텀.{0,5}(?:상위|순위|랭킹|상위권|강한)",
    r"(?:상승률|많이오른|꾸준히오른|강하게오른|강하게상승|가장오른|강세).{0,8}(?:상위|상위권|순|랭킹)",
    # "가장 강하게 오른 종목 N개" 처럼 '상위'가 떨어져 있어도 강한 상승 표현은 모멘텀 랭킹으로 본다.
    r"(?:가장|제일).{0,4}(?:강하게|많이).{0,2}(?:오른|상승)",
)


def _mentions_relative_strength_ranking(compact: str) -> bool:
    return any(re.search(pattern, compact) for pattern in _RELATIVE_STRENGTH_RANKING_CUES)


# 진입 규칙을 하나도 구조화하지 못했을 때 쓰는 일반 안내(재무 필터/기술 신호 미언급).
_MISSING_ENTRY_QUESTION = (
    "어떤 조건으로 종목을 선택할까요? 진입 조건을 알려주세요.\n\n"
    "예시:\n"
    "• **재무 필터**: \"PBR 1 이하\", \"ROE 15% 이상\", \"PER 10 이하\"\n"
    "• **기술적 신호**: \"골든크로스 발생 시 매수\", \"RSI 30 이하에서 매수\""
)
_MISSING_ENTRY_SUGGESTIONS = [
    "PBR 1 이하, PER 10 이하 저평가 종목",
    "골든크로스(5일/20일) 발생 시 매수",
    "RSI 30 이하 과매도 구간에서 매수",
    "거래대금 100억 이상 종목 중 60일 신고가 돌파 매수",
]

# 지표는 말했지만 숫자(임계값)를 안 준 정성 표현("PER이 낮은", "부채비율이 낮은")을 감지해
# 그 지표별로 구체적 숫자를 예시와 함께 되묻기 위한 표.
# (키, 키워드 패턴들, 되묻기 문구, 느슨한 예시 칩, 엄격한 예시 칩)
_QUALITATIVE_METRIC_SPECS: tuple[tuple[str, tuple[str, ...], str, str, str], ...] = (
    ("per", (r"per", r"주가수익비율"),
     "PER은 몇 이하로 할까요? (예: 10 이하)", "PER 10 이하", "PER 7 이하"),
    ("pbr", (r"pbr", r"주가순자산"),
     "PBR은 몇 이하로 할까요? (예: 1 이하)", "PBR 1 이하", "PBR 0.8 이하"),
    ("roe", (r"roe", r"자기자본이익"),
     "ROE는 몇 % 이상으로 할까요? (예: 15% 이상)", "ROE 15% 이상", "ROE 20% 이상"),
    ("operating_margin", (r"영업이익률", r"매출액영업이익률"),
     "영업이익률 몇 % 이상으로 설정할까요?", "영업이익률 10% 이상", "영업이익률 15% 이상"),
    ("debt_ratio", (r"부채",),
     "부채비율은 몇 % 이하로 할까요? (예: 100% 이하)", "부채비율 100% 이하", "부채비율 50% 이하"),
    ("market_cap", (r"시가총액", r"시총"),
     "시가총액은 몇 억 이상으로 할까요? (예: 1000억 이상)", "시가총액 1000억 이상", "시가총액 5000억 이상"),
    ("trading_value", (r"거래대금",),
     "거래대금은 몇 억 이상으로 할까요? (예: 100억 이상)", "거래대금 100억 이상", "거래대금 300억 이상"),
)

_QUALITATIVE_KEY_TO_METRIC = {
    "per": "per",
    "pbr": "pbr",
    "roe": "roe_or_gpa",
    "operating_margin": "operating_margin",
    "debt_ratio": "debt_ratio",
    "market_cap": "market_cap",
    "trading_value": "trading_value",
}


def _detect_qualitative_metrics(compact: str) -> list[tuple[str, str, str, str]]:
    """언급된 재무 지표 spec들을 입력 순서대로 반환한다.

    실제 임계값의 구조화 여부는 호출부가 결정적 추출 결과나 parsed 필터와 비교해 판정한다.
    반환 튜플: (되묻기 문구, 느슨한 칩, 엄격한 칩, 키).
    """
    found: list[tuple[int, tuple[str, str, str, str]]] = []
    for key, patterns, ask, loose, strict in _QUALITATIVE_METRIC_SPECS:
        pos = min(
            (m.start() for p in patterns if (m := re.search(p, compact))),
            default=-1,
        )
        if pos >= 0:
            found.append((pos, (ask, loose, strict, key)))
    found.sort(key=lambda x: x[0])
    return [spec for _, spec in found]


# 상대강도 랭킹을 말했지만 표현이 불가능할 때: 가까운 추세추종으로 바꾸도록 안내.
_RELATIVE_STRENGTH_QUESTION = (
    "'수익률이 높은 종목을 골라 담는' **상대강도(모멘텀) 랭킹** 방식을 말씀하신 것 같아요.\n\n"
    "이 선정 방식은 아직 직접 지원되지 않아요. 대신 비슷하게 '꾸준히 오르는 추세'를 "
    "**추세추종 신호**로 바꿔서 만들 수 있어요. 아래에서 가까운 방식을 골라 다시 말씀해 주세요."
)
_RELATIVE_STRENGTH_SUGGESTIONS = [
    "20일선이 60일선을 상향 돌파하면 매수, 데드크로스 시 매도",
    "60일 신고가를 돌파하면 매수",
    "골든크로스(5일/20일) 매수, 데드크로스 매도",
]


# ETF/ETN 등 상장 금융상품 언급: ETF는 정식 유니버스(universe=["ETF"])로 지원되지만,
# 개별 기업 재무지표(PER·PBR·ROE)가 없어 일반 예시(재무 필터 칩)를 그대로 보여주면
# 오답이다. ETF에 통용되는 가격·추세 기반 방식으로 진입 조건을 안내한다.
_ETF_PRODUCT_RE = re.compile(r"etf|etn|이티에프|상장지수(?:펀드|증권)|kodex")

_ETF_PRODUCT_QUESTION = (
    "ETF 전략이군요! 어떤 조건으로 매매할까요?\n\n"
    "ETF는 여러 종목을 묶은 상품이라 개별 기업 재무지표(PER·PBR·ROE)는 조건으로 쓸 수 "
    "없고, **가격·추세 기반 규칙**으로 전략을 만들어요 — 이동평균 추세추종, 모멘텀"
    "(신고가 돌파), RSI 평균회귀, 볼린저밴드, MACD, 정기 리밸런싱 같은 방식이에요.\n\n"
    "예시에서 고르거나 직접 말씀해 주세요."
)
_ETF_PRODUCT_SUGGESTIONS = [
    "20일선이 60일선을 상향 돌파하면 매수, 데드크로스 시 매도",
    "60일 신고가 돌파 시 매수, 트레일링 스탑 10%",
    "RSI 30 이하에서 매수, RSI 70 이상에서 매도",
    "MACD 골든크로스 매수, 데드크로스 매도, 손절 10%",
]


# ETF 유니버스 × 기업 재무지표 충돌: 조용히 무시하지 않고 이유를 설명한 뒤 ETF에서
# 가능한 대안(기술적 지표)으로 변경을 제안한다(universe_capabilities 레지스트리 판정).
_ETF_FACTOR_CONFLICT_QUESTION = (
    "ETF는 개별 기업이 아니라 여러 종목을 묶은 상품이므로 {metrics} 같은 기업 재무지표를 "
    "조건으로 사용할 수 없습니다.\n\n"
    "대신 이동평균, RSI, MACD, 모멘텀 등 가격·기술 지표를 이용한 ETF 전략으로 "
    "변경할까요? 아래에서 고르거나 직접 말씀해 주세요."
)

# 재무 지표 → 사용자 표시 라벨(충돌 안내용).
_FUNDAMENTAL_METRIC_LABELS: dict[str, str] = {
    "per": "PER", "pbr": "PBR", "psr": "PSR", "ev_ebitda": "EV/EBITDA",
    "roe_or_gpa": "ROE", "roa": "ROA", "debt_ratio": "부채비율",
    "current_ratio": "유동비율", "quick_ratio": "당좌비율", "reserve_ratio": "유보율",
    "net_margin": "순이익률", "gross_margin": "매출총이익률", "operating_margin": "영업이익률",
    "revenue_growth": "매출액증가율", "operating_income_growth": "영업이익증가율",
    "net_income_growth": "순이익증가율", "market_cap": "시가총액",
    "dividend_yield": "배당수익률", "payout_rate": "배당성향", "dividend_growth": "배당성장률",
}


def detect_etf_factor_conflict(
    parsed: ParsedStrategy, user_prompt: str = "",
) -> tuple[Optional[str], Optional[List[str]]]:
    """ETF 유니버스 전략에 기업 재무지표가 섞이면 설명+대안 제안으로 되묻는다.

    조용히 무시(드롭)하거나 그대로 실행(0커버리지 조건)하지 않는다 — 왜 쓸 수 없는지
    설명하고 ETF에서 가능한 조건으로 대체를 제안한다. 충돌 없으면 (None, None).
    재무 지표를 정성적으로만 언급한 경우("PER 낮은 ETF")도 같은 안내를 한다.
    """
    from engine.universe_capabilities import is_etf_strategy, unsupported_fundamental_metrics

    # getattr 방어 — 레거시 저장 DSL·테스트 스텁 등 universe 없는 객체는 주식 취급.
    universe = getattr(parsed, "universe", None)
    if not is_etf_strategy(universe):
        return (None, None)
    offending = unsupported_fundamental_metrics(
        universe, (f.metric for f in getattr(parsed, "fundamental_filters", []) or [])
    )
    if not offending:
        # 구조화된 필터는 없지만 재무 지표를 정성적으로 언급한 경우("PER이 낮은 ETF").
        compact = re.sub(r"\s+", "", user_prompt.lower())
        offending = unsupported_fundamental_metrics(
            parsed.universe,
            (_QUALITATIVE_KEY_TO_METRIC[key]
             for _, _, _, key in _detect_qualitative_metrics(compact)),
        )
    if not offending:
        return (None, None)
    labels = ", ".join(_FUNDAMENTAL_METRIC_LABELS.get(m, m.upper()) for m in offending)
    return (
        _ETF_FACTOR_CONFLICT_QUESTION.format(metrics=labels),
        list(_ETF_PRODUCT_SUGGESTIONS),
    )


def detect_missing_entry_clarification(
    parsed: ParsedStrategy,
    user_prompt: str = "",
) -> tuple[Optional[str], Optional[List[str]]]:
    """요청한 진입(종목 선정) 규칙이나 임계값을 구조화하지 못했을 때 되묻는다.

    파서가 사용자의 진입 의도를 표현하지 못하면 — 미지원 전략 유형이라 못 잡은 경우 포함 —
    조용히 버리지 않고 명시적으로 확인한다. 상대강도(수익률 순위) 랭킹처럼 아직 지원 안 되는
    유형은 가까운 추세추종으로 바꿀 수 있게 안내한다. 요청한 진입 규칙이 모두 있으면
    (None, None).

    유니버스·초기자금 등 다른 누락은 일부러 묻지 않는다(기본값이 있어 노이즈만 됨).
    여기서는 '진입을 통째로 잃는' 침묵 누락만 막는다.
    """
    compact = re.sub(r"\s+", "", user_prompt.lower())
    # ETF 유니버스: 재무 필터는 상품에 적용되지 않으므로 임계값 되묻기("PER은 몇 이하로
    # 할까요?")나 재무 예시 칩 대신 가격·추세 기반 예시로 진입 조건을 묻는다. 기술 신호나
    # 랭킹이 이미 있으면 되묻지 않는다(그대로 실행 가능 — ETF는 정식 지원 유니버스).
    # 재무지표가 실제로 섞인 경우는 detect_etf_factor_conflict가 먼저 가로챈다.
    if ("ETF" in (getattr(parsed, "universe", None) or [])
            or _ETF_PRODUCT_RE.search(compact)) and not (
        parsed.entry_signals or parsed.ranking_metric
    ):
        return (_ETF_PRODUCT_QUESTION, list(_ETF_PRODUCT_SUGGESTIONS))
    resolved_metrics = {item.metric for item in parsed.fundamental_filters}
    # Ask for every named metric that still lacks an executable threshold, even when an
    # unrelated entry signal exists. This prevents a model substitution from hiding the omission.
    metrics = [
        metric
        for metric in _detect_qualitative_metrics(compact)
        if _QUALITATIVE_KEY_TO_METRIC[metric[3]] not in resolved_metrics
    ]
    if metrics:
        asks = "\n".join(f"• {ask}" for ask, _, _, _ in metrics)
        question = (
            "말씀하신 조건을 숫자로 구체화해 주세요. 어느 정도를 기준으로 할까요?\n\n"
            f"{asks}"
        )
        loose = ", ".join(loose for _, loose, _, _ in metrics)
        strict = ", ".join(strict for _, _, strict, _ in metrics)
        suggestions = [loose, strict] if loose != strict else [loose]
        return (question, suggestions)
    if parsed.fundamental_filters or parsed.entry_signals or parsed.ranking_metric:
        return (None, None)
    if _mentions_relative_strength_ranking(compact):
        return (_RELATIVE_STRENGTH_QUESTION, list(_RELATIVE_STRENGTH_SUGGESTIONS))
    return (_MISSING_ENTRY_QUESTION, list(_MISSING_ENTRY_SUGGESTIONS))


def validate_parsed_strategy(
    parsed: ParsedStrategy,
    user_prompt: str = "",
) -> tuple[Optional[str], Optional[List[str]]]:
    """
    필수·권장 팩터 누락 여부를 검사하고, 누락 시 친절한 질문과 빠른 선택지를 반환.
    디폴트값이 있어도 사용자가 언급하지 않은 팩터는 물어본다.
    문제 없으면 (None, None) 반환.

    우선순위:
      1. 진입/청산 조건 (전략의 뼈대)
      2. 리스크 관리 (손절/익절/트레일링)
      3. 포트폴리오 설정 (최대 종목 수)
      4. 백테스트 설정 (기간, 초기자금)

    Returns:
        (question, suggestions) — 둘 다 None이면 전략 완성.
    """
    p = user_prompt.lower()

    has_entry = bool(parsed.fundamental_filters or parsed.entry_signals)
    has_exit  = bool(
        parsed.exit_signals or
        parsed.hold_period_days or
        parsed.stop_loss_pct is not None or
        parsed.take_profit_pct is not None or
        parsed.trailing_stop_pct is not None or
        parsed.max_mdd_limit_pct is not None
    )

    # ── 1순위: 진입 / 청산 조건 ──────────────────────────────────────────────
    if not has_entry and not has_exit:
        return (
            "전략을 완성하려면 두 가지가 더 필요해요!\n\n"
            "**① 진입 조건** - 어떤 종목을 살까요?\n"
            "재무 필터(PBR, PER, ROE 등)나 기술적 신호(골든크로스, RSI 등)를 알려주세요.\n\n"
            "**② 청산 조건** - 언제 팔까요?\n"
            "보유 기간(예: 3개월 보유)이나 매도 신호(예: RSI 70 이상에서 매도)를 알려주세요.",
            [
                "PBR 1 이하 종목을 6개월 보유",
                "골든크로스 매수, 데드크로스 매도, 손절 10%",
                "ROE 15% 이상 종목 1년 보유 후 연간 리밸런싱",
                "RSI 30 이하에서 매수, RSI 70 이상에서 매도",
            ],
        )

    if not has_entry:
        return (
            "어떤 조건으로 종목을 선택할까요? 진입 조건을 알려주세요.\n\n"
            "예시:\n"
            "• **재무 필터**: \"PBR 1 이하\", \"ROE 15% 이상\", \"PER 10 이하\"\n"
            "• **기술적 신호**: \"골든크로스 발생 시 매수\", \"RSI 30 이하에서 매수\"\n"
            "• **돌파 신호**: \"60일 신고가 돌파 시 매수\"",
            [
                "PBR 1 이하, PER 10 이하 저평가 종목",
                "골든크로스(5일/20일) 발생 시 매수",
                "RSI 30 이하 과매도 구간에서 매수",
                "거래대금 100억 이상 종목 중 60일 신고가 돌파 매수",
            ],
        )

    if not has_exit:
        return (
            "청산 조건이 없으면 언제 팔아야 할지 알 수 없어요. 어떻게 하실 건가요?\n\n"
            "• **기간 보유**: \"3개월 보유\", \"1년 보유 후 연간 리밸런싱\"\n"
            "• **기술적 청산**: \"RSI 70 이상에서 매도\", \"데드크로스 시 매도\"\n"
            "• **리스크 관리**: \"손절 10%\", \"익절 20%\", \"트레일링 스탑 15%\"",
            [
                "3개월 보유 후 청산",
                "1년 보유 후 연간 리밸런싱",
                "RSI 70 이상에서 매도, 손절 10%",
                "손절 10%, 익절 25%",
            ],
        )

    # ── 1.5순위: 유니버스 (명시 언급 없으면 확인)
    if not _mentioned(p, "universe"):
        universe_label = {
            ("KOSPI200",): "KOSPI200 (200종목, 빠름)",
            ("KOSPI",): "KOSPI 전체 (~838종목)",
            ("KOSDAQ",): "KOSDAQ 전체 (~1,781종목)",
            ("KOSPI", "KOSDAQ"): "전체 시장 (~2,619종목, 느림)",
            ("KOSDAQ", "KOSPI"): "전체 시장 (~2,619종목, 느림)",
            ("ETF",): "ETF 전체 (~1,140종목)",
        }.get(tuple(sorted(parsed.universe)), str(parsed.universe))
        return (
            f"어느 시장에서 종목을 찾을까요?\n\n"
            f"현재 기본값은 **{universe_label}**입니다.\n\n"
            f"• **KOSPI200** (권장): KRX KOSPI200 구성 200종목 — 대형 우량주, 백테스트 속도 빠름\n"
            f"• **KOSPI**: 코스피 전체 ~838종목 — 대형·중형주 포함\n"
            f"• **KOSDAQ**: 코스닥 ~1,781종목 — 중소형 성장주 위주\n"
            f"• **전체 시장**: KOSPI + KOSDAQ ~2,619종목 — 가장 넓지만 느림",
            [
                "KOSPI200 (기본값, 빠름) 그대로 진행",
                "KOSPI200 (KRX 구성 200종목)",
                "KOSPI (코스피 전체 ~838종목)",
                "KOSDAQ (코스닥 ~1,781종목)",
                "전체 시장 (KOSPI+KOSDAQ ~2,619종목)",
            ],
        )

    # ── 2순위: 리스크 관리 (손절/익절만 필수 — 트레일링 스탑은 선택 사항)
    missing_risk: list[str] = []
    if not _mentioned(p, "stop_loss") and parsed.stop_loss_pct is None:
        missing_risk.append("stop_loss")
    if not _mentioned(p, "take_profit") and parsed.take_profit_pct is None:
        missing_risk.append("take_profit")

    if missing_risk:
        lines = ["리스크 관리 조건도 설정해 두시겠어요?\n"]
        if "stop_loss" in missing_risk:
            lines.append("• **손절**: 매수가 대비 몇 % 하락 시 청산? (현재 미설정, 권장 8~15%)")
        if "take_profit" in missing_risk:
            lines.append("• **익절**: 몇 % 수익 시 청산? (현재 미설정, 권장 15~30%)")
        lines.append("\n설정하지 않으면 해당 리스크 관리 없이 진행됩니다.")
        return (
            "\n".join(lines),
            [
                "리스크 관리 없이 진행",
                "손절 10%만 설정",
                "손절 10%, 익절 20%",
                "손절 8%, 익절 25%",
            ],
        )

    # ── 3순위: 최대 종목 수 ────────────────────────────────────────────────────
    if not _mentioned(p, "max_positions"):
        return (
            f"동시에 몇 개 종목을 보유할까요?\n\n"
            f"현재 기본값은 **{parsed.max_positions}개**입니다. "
            f"종목 수가 많을수록 분산 효과는 크지만 관리가 복잡해집니다.",
            [
                f"{parsed.max_positions}개 그대로 진행",
                "5개 종목 (집중 투자)",
                "10개 종목",
                "20개 종목 (분산 투자)",
            ],
        )

    # ── 4순위: 백테스트 기간 ─────────────────────────────────────────────────
    if not _mentioned(p, "backtest_period"):
        period_label = {"1y": "1년", "3y": "3년", "5y": "5년", "full": "전체"}.get(parsed.backtest_period, parsed.backtest_period)
        return (
            f"백테스트 기간을 얼마로 할까요?\n\n"
            f"현재 기본값은 **{period_label}**입니다. "
            f"기간이 길수록 다양한 시장 환경에서의 성과를 확인할 수 있습니다.",
            [
                f"{period_label} 그대로 진행",
                "1년 (최근 추세 확인)",
                "3년",
                "5년 (권장)",
                "전체 데이터",
            ],
        )

    # ── 5순위: 초기자금 ──────────────────────────────────────────────────────
    if not _mentioned(p, "initial_capital"):
        capital_label = f"{int(parsed.initial_capital):,}원"
        return (
            f"초기 투자금은 얼마로 설정할까요?\n\n"
            f"현재 기본값은 **{capital_label}**입니다.",
            [
                f"{capital_label} 그대로 진행",
                "1,000만원",
                "5,000만원",
                "1억원",
            ],
        )

    return None, None
