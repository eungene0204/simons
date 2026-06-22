"""
자연어 전략 파서 (NL Strategy Parser)

사용자가 한국어로 입력한 전략 설명을 구조화된 ParsedStrategy로 변환한다.
LLM 백엔드: Ollama (instructor) 또는 MLX (outlines)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

from llm_backend import OLLAMA_BASE_URL, ollama_auth_headers

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
#   - URLError(연결거부 등) → 재시도
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


# ─── 스키마 정의 ──────────────────────────────────────────────────────────────

class FundamentalFilter(BaseModel):
    """재무 지표 필터 조건"""
    metric: Literal["per", "pbr", "roe_or_gpa", "debt_ratio", "market_cap", "trading_value"] = Field(
        description=(
            "재무 지표 종류. "
            "per=주가수익비율, pbr=주가순자산비율, roe_or_gpa=자기자본이익률(%), "
            "debt_ratio=부채비율(%), market_cap=시가총액(억원), trading_value=일평균거래대금(억원)"
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
        "stochastic", "cci", "adx",
        "ai_model", "ai_drop_model"
    ] = Field(description="지표 종류. ai_model=AI 상승 예측 매수, ai_drop_model=AI 하락 예측 매도")
    signal_type: Literal["buy", "sell"] = Field(default="buy", description="매수=buy, 매도=sell")

    # MA / EMA 크로스오버
    short_period: Optional[int] = Field(default=None, description="단기 이동평균 기간 (ma_crossover, ema)")
    long_period: Optional[int] = Field(default=None, description="장기 이동평균 기간 (ma_crossover, ema)")

    # RSI / CCI / ADX
    period: Optional[int] = Field(default=None, description="지표 계산 기간 (rsi, cci, adx, volume_spike)")
    operator: Optional[Literal["<", ">", "<=", ">="]] = Field(default=None, description="비교 연산자 (rsi, cci, adx)")
    value: Optional[float] = Field(default=None, description="비교 기준값 (rsi, cci, adx)")

    # MACD
    mode: Optional[Literal["crossover", "zero"]] = Field(default=None, description="MACD 모드: crossover=시그널 크로스, zero=제로선 돌파")

    # 브레이크아웃
    lookback_period: Optional[int] = Field(default=None, description="브레이크아웃 기준 기간 (breakout)")

    # AI 모델
    threshold: Optional[float] = Field(default=None, description="AI 모델 신뢰도 임계값 (ai_model, ai_drop_model). 예: 70 = 70% 이상 확률")


class ParsedStrategy(BaseModel):
    """자연어 전략 → 구조화된 전략 스키마"""

    description: str = Field(description="사용자가 입력한 원문 전략 설명 (그대로 복사)")

    # ── 유니버스
    universe: List[Literal["KOSPI", "KOSDAQ", "KOSPI200"]] = Field(
        default=["KOSPI200"],
        description="투자 대상 시장. 언급 없으면 ['KOSPI200'] (KOSPI 전체 종목, 유동성 우선). '코스닥'/'KOSDAQ' 언급 시 ['KOSDAQ'], '전체'/'코스피+코스닥' 언급 시 ['KOSPI', 'KOSDAQ']"
    )

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
    description: Optional[str] = None
    universe: Optional[List[Literal["KOSPI", "KOSDAQ", "KOSPI200"]]] = None
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

## 금액 단위 변환 (initial_capital)
- '1억' → 100000000.0
- '5천만원' → 50000000.0
- '2억 5천만' → 250000000.0
- '1000만원' → 10000000.0

## 예시
현재 전략: {"max_positions": 20, "initial_capital": 10000000.0, ...}
수정 요청: "종목을 10개로 줄여줘"
출력: {"description": null, "universe": null, "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": 10, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "초기자금 1억으로 바꿔줘"
출력: {"description": null, "universe": null, "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": 100000000.0, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "트레일링 스탑 15%로 설정해줘"
출력: {"description": null, "universe": null, "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": 15.0, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "KOSPI200 (기본값, 빠름) 그대로 진행" 또는 "KOSPI200으로 진행"
출력: {"description": null, "universe": ["KOSPI200"], "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "코스닥으로 바꿔줘" 또는 "KOSDAQ (코스닥 ~1,781종목)"
출력: {"description": null, "universe": ["KOSDAQ"], "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}

수정 요청: "전체 시장 (KOSPI+KOSDAQ ~2,619종목)" 또는 "전체 시장으로"
출력: {"description": null, "universe": ["KOSPI", "KOSDAQ"], "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": null, "hold_period_days": null, "rebalancing_period": null, "stop_loss_pct": null, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}
"""


# ─── 시스템 프롬프트 ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 한국 주식 퀀트 투자 전략을 JSON으로 변환하는 전문가입니다.

## 변환 규칙

### 재무 필터 (fundamental_filters)
- PBR 1 이하 → {"metric": "pbr", "operator": "<=", "value": 1.0}
- PER 7 미만 → {"metric": "per", "operator": "<", "value": 7.0}
- ROE 15% 이상 → {"metric": "roe_or_gpa", "operator": ">=", "value": 15.0}
- 부채비율 100% 이하 → {"metric": "debt_ratio", "operator": "<=", "value": 100.0}
- 시가총액 1000억 이상 → {"metric": "market_cap", "operator": ">=", "value": 1000.0}
- '이하'='<=', '미만'='<', '이상'='>=', '초과'='>'

### 기술적 신호 (entry_signals / exit_signals)
- 골든크로스 → indicator: "ma_crossover", signal_type: "buy", short_period: 5, long_period: 20
- 데드크로스 → indicator: "ma_crossover", signal_type: "sell", short_period: 5, long_period: 20
- RSI 30 이하 → indicator: "rsi", signal_type: "buy", period: 14, operator: "<=", value: 30
- RSI 70 이상 → indicator: "rsi", signal_type: "sell", period: 14, operator: ">=", value: 70
- 'RSI가 30 아래로 내려갔다가 다시 올라오는' / 'RSI 과매도 후 반등' 같은 구어체 반등 표현도 RSI 매수로 처리: operator "<=", value 30
- 매도 동사는 '매도/청산'뿐 아니라 '팔고/팔아/팔면' 같은 구어체도 동일하게 처리
- MACD 크로스 → indicator: "macd", signal_type: "buy", mode: "crossover"
- 볼린저밴드 하단 → indicator: "bollinger_bands", signal_type: "buy"
- 볼린저밴드 상단 → indicator: "bollinger_bands", signal_type: "sell"
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

## 예시

입력: "AI 모델이 상승 예측한 종목에 매수, AI 하락 예측 시 매도, 최대 15종목, 손절 10%"
출력:
{
  "description": "AI 모델이 상승 예측한 종목에 매수, AI 하락 예측 시 매도, 최대 15종목, 손절 10%",
  "universe": ["KOSPI200"],
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
  "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "period": 14, "operator": "<=", "value": 30}],
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

기본값:
- universe: ["KOSPI200"], max_positions: 10, backtest_period: "5y"
- initial_capital: 10000000.0, execution_timing: "next_open"
- fee_rate: 0.015, slippage_rate: 0.05
- rebalancing_period: "none", 누락된 optional 필드는 null

매핑:
- PBR/PER/ROE/부채비율/시가총액/거래대금 → fundamental_filters
- 이하/미만/이상/초과 → <=/< />=/ >
- 골든크로스/데드크로스 → ma_crossover buy/sell, 기본 5/20
- RSI 30 이하/70 이상 → rsi buy/sell, 기본 period 14
- 'RSI가 30 아래로 내려갔다가 다시 올라오는' / 'RSI 과매도 반등' 구어체도 rsi buy (operator "<=", value 30)
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

    def parse(self, user_input: str) -> ParsedStrategy:
        """자연어 입력 → ParsedStrategy (규칙 기반 우선, 모호하면 4B 사용)"""
        parsed_by_rules = _parse_rule_based_strategy(user_input)
        if parsed_by_rules is not None:
            return parsed_by_rules

        try:
            if self.backend == "mlx":
                parsed = self._parse_mlx(user_input)
            else:
                parsed = self._parse_ollama(user_input)
        except ValueError as exc:
            if "JSON object" not in str(exc):
                raise
            parsed = _build_fallback_strategy(user_input)
        return _apply_prompt_overrides(parsed, user_input)

    def parse_modification(self, user_input: str, previous: dict) -> ParsedStrategy:
        """수정 요청: diff만 LLM으로 추출 후 previous와 병합 (32B 사용)"""
        if self.backend == "mlx":
            diff = self._modify_mlx(user_input, previous)
        else:
            diff = self._modify_ollama(user_input, previous)

        explicit_universe = _extract_explicit_universe(user_input)

        # diff의 non-null 필드만 previous에 덮어씀
        merged = {**previous}
        for field, val in diff.model_dump().items():
            if field == "universe" and explicit_universe is None:
                continue
            if val is not None:
                merged[field] = val

        # 삭제 의도 명시 처리: LLM diff는 null="변경없음"으로 표현하므로 별도 감지
        compact = re.sub(r"\s+", "", user_input.lower())
        if any(kw in compact for kw in _DELETE_TERMS):
            if any(kw in compact for kw in ["손절", "stoploss", "스탑로스"]):
                merged["stop_loss_pct"] = None
            if any(kw in compact for kw in ["익절", "takeprofit", "익절률"]):
                merged["take_profit_pct"] = None
            if any(kw in compact for kw in ["트레일링", "trailingstop"]):
                merged["trailing_stop_pct"] = None

        return _apply_prompt_overrides(ParsedStrategy.model_validate(merged), user_input)

    def _modify_mlx(self, user_input: str, previous: dict) -> ParsedStrategyDiff:
        self._init_mlx()
        prompt = (
            f"{MODIFY_PROMPT}\n\n"
            f"현재 전략:\n{json.dumps(previous, ensure_ascii=False)}\n\n"
            f"수정 요청: \"{user_input}\"\n출력:"
        )
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

    def _parse_mlx(self, user_input: str) -> ParsedStrategy:
        self._init_mlx()
        prompt = f"{COMPACT_SYSTEM_PROMPT}\n\n입력: \"{user_input}\"\n출력:"
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


def _extract_explicit_universe(user_input: str) -> Optional[List[str]]:
    prompt = user_input.lower()
    compact = re.sub(r"\s+", "", prompt)

    mentions_kospi200 = "kospi200" in compact or "코스피200" in compact
    mentions_kosdaq = "kosdaq" in compact or "코스닥" in compact
    mentions_kospi = not mentions_kospi200 and ("kospi" in compact or "코스피" in compact)
    # "대형주"는 시가총액 기준 분류(KRX: 시총 상위 100위권)이므로 표준 대형주 지수인
    # KOSPI200으로 매핑한다. 단 코스닥 단독 맥락에서는 적용하지 않는다 — 코스닥 대형주
    # 전용 유니버스가 없어 KOSPI200으로 매핑하면 시장 자체가 바뀌는 오매핑이 된다.
    mentions_large_cap = "대형주" in compact or "대형" in compact
    mentions_all_market = (
        "전체시장" in compact or
        "코스피+코스닥" in compact or
        "코스피와코스닥" in compact or
        "kospi+kosdaq" in compact or
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
    compact = re.sub(r"\s+", "", user_input.lower())
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


def _extract_technical_signals(user_input: str) -> tuple[list[TechnicalSignal], list[TechnicalSignal]]:
    """
    프롬프트에서 기술적 진입/청산 신호를 deterministic하게 추출한다.
    LLM이 놓칠 수 있는 패턴을 보장하기 위한 후처리 단계.

    Returns:
        (entry_signals, exit_signals)
    """
    compact = re.sub(r"\s+", "", user_input.lower())
    entry: list[TechnicalSignal] = []
    exit_: list[TechnicalSignal] = []

    # ── 골든크로스 / 데드크로스 (MA 크로스오버) ──
    # 기간 추출: "5일/20일", "5일20일", "단기5장기20" 등
    ma_short, ma_long = None, None
    ma_period_match = re.search(r"(\d+)일[/,]?(\d+)일", compact)
    if ma_period_match:
        p1, p2 = int(ma_period_match.group(1)), int(ma_period_match.group(2))
        ma_short, ma_long = min(p1, p2), max(p1, p2)

    golden_patterns = ["골든크로스", "goldencross", "golden_cross"]
    dead_patterns = ["데드크로스", "deadcross", "dead_cross"]

    has_golden = any(p in compact for p in golden_patterns)
    has_dead = any(p in compact for p in dead_patterns)

    # "크로스오버" / "이동평균 크로스" 같은 일반 표현 + 매수/매도 언급
    if not has_golden and not has_dead:
        crossover_terms = ["이동평균선을위로뚫", "이동평균크로스", "ma크로스", "이평선크로스"]
        if any(t in compact for t in crossover_terms):
            has_golden = True
            # "반대로" / "매도" 가 함께 있으면 데드크로스도 포함
            if "반대로" in compact or ("매도" in compact and "매수" in compact):
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
    ma_token = r"(?:이동평균선|이동평균|이평선|이평|선)"
    if not has_golden:
        above_ma = re.search(rf"(\d+)일{ma_token}(?:을|를)?(?:위|상회|넘|돌파|올라)", compact)
        if above_ma:
            entry.append(TechnicalSignal(
                indicator="ma_crossover", signal_type="buy",
                short_period=1, long_period=int(above_ma.group(1)),
            ))
    if not has_dead:
        below_ma = re.search(rf"(\d+)일{ma_token}(?:을|를)?(?:아래|밑|하회|이탈)", compact)
        if below_ma:
            exit_.append(TechnicalSignal(
                indicator="ma_crossover", signal_type="sell",
                short_period=1, long_period=int(below_ma.group(1)),
            ))

    # ── EMA 크로스 (단기 EMA가 장기 EMA 위/아래) ──
    # "20일 EMA가 60일 EMA 위에 있고" → ema 골든(단기>장기, 진입).
    # "20일 EMA가 60일 EMA 아래로" → ema 데드(청산). 두 기간은 min/max로 단기/장기를 정한다.
    # 기간 사이 공백 구간은 숫자를 포함하지 않게 [^0-9]로 막아 '60'이 '6'+'0'으로 쪼개지지 않도록 한다.
    ema_above = re.search(
        r"(\d+)일?ema[^0-9]{0,6}(\d+)일?ema[^0-9]{0,6}(?:위|상회|넘|돌파|상향|이상|높)", compact
    )
    if ema_above:
        p1, p2 = int(ema_above.group(1)), int(ema_above.group(2))
        entry.append(TechnicalSignal(
            indicator="ema", signal_type="buy",
            short_period=min(p1, p2), long_period=max(p1, p2),
        ))
    ema_below = re.search(
        r"(\d+)일?ema[^0-9]{0,6}(\d+)일?ema[^0-9]{0,6}(?:아래|밑|하회|이탈|하향)", compact
    )
    if ema_below:
        p1, p2 = int(ema_below.group(1)), int(ema_below.group(2))
        exit_.append(TechnicalSignal(
            indicator="ema", signal_type="sell",
            short_period=min(p1, p2), long_period=max(p1, p2),
        ))

    # ── RSI 매수/매도 ──
    # 조사("rsi가30") + "이하/미만/아래/밑" + 매수/진입/반등/올라오는(과매도 반등) 표현 허용
    rsi_buy_match = re.search(
        r"rsi(?:가|이|은|는|을|를)?\s*(\d+)\s*(?:이하|미만|아래|밑).*?(?:매수|진입|반등|올라)"
        r"|rsi.*?과매도.*?(?:매수|반등|올라)",
        compact,
    )
    if rsi_buy_match:
        val = int(rsi_buy_match.group(1)) if rsi_buy_match.group(1) else 30
        entry.append(TechnicalSignal(
            indicator="rsi", signal_type="buy", period=14, operator="<=", value=float(val),
        ))
    rsi_sell_match = re.search(
        r"rsi(?:가|이|은|는|을|를)?\s*(\d+)\s*(?:이상|초과|위).*?(?:매도|청산)"
        r"|rsi.*?과매수.*?(?:매도|청산)",
        compact,
    )
    if rsi_sell_match:
        val = int(rsi_sell_match.group(1)) if rsi_sell_match.group(1) else 70
        exit_.append(TechnicalSignal(
            indicator="rsi", signal_type="sell", period=14, operator=">=", value=float(val),
        ))

    # ── MACD ──
    macd_buy_patterns = ["macd크로스.*?매수", "macd.*?골든", "macd시그널.*?매수"]
    if any(re.search(p, compact) for p in macd_buy_patterns):
        entry.append(TechnicalSignal(indicator="macd", signal_type="buy", mode="crossover"))
    macd_sell_patterns = ["macd크로스.*?매도", "macd.*?데드", "macd시그널.*?매도"]
    if any(re.search(p, compact) for p in macd_sell_patterns):
        exit_.append(TechnicalSignal(indicator="macd", signal_type="sell", mode="crossover"))

    # ── ADX (추세 강도 필터) ──
    # 'ADX가 25 이상' 류를 진입 조건으로 잡는다. ADX는 단독 트리거보다 추세 강도 확인용이지만,
    # 규칙 기반에서 통째로 누락하면 코치가 '없는 조건을 있다'고 오인하므로 명시적으로 포착한다.
    adx_match = re.search(r"adx(?:가|이|은|는)?\s*(\d+(?:\.\d+)?)\s*(이상|초과|이하|미만)?", compact)
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
        rf"{stoch_term}(?:가|이|은|는|을|를)?\s*(\d+)\s*(?:이하|미만|아래|밑).*?(?:매수|진입|반등|올라)"
        rf"|{stoch_term}.*?과매도.*?(?:매수|반등|올라)",
        compact,
    )
    if stoch_buy:
        val = int(stoch_buy.group(1)) if stoch_buy.group(1) else 20
        entry.append(TechnicalSignal(
            indicator="stochastic", signal_type="buy", operator="<=", value=float(val),
        ))
    stoch_sell = re.search(
        rf"{stoch_term}(?:가|이|은|는|을|를)?\s*(\d+)\s*(?:이상|초과|위).*?(?:매도|청산)"
        rf"|{stoch_term}.*?과매수.*?(?:매도|청산)",
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
        r"cci(?:가|이|은|는|을|를)?\s*(-?\d+)\s*(?:이하|미만|아래|밑).*?(?:매수|진입|반등|올라)"
        r"|cci.*?과매도.*?(?:매수|반등|올라)",
        compact,
    )
    if cci_buy:
        val = int(cci_buy.group(1)) if cci_buy.group(1) else -100
        entry.append(TechnicalSignal(
            indicator="cci", signal_type="buy", period=14, operator="<=", value=float(val),
        ))
    cci_sell = re.search(
        r"cci(?:가|이|은|는|을|를)?\s*(-?\d+)\s*(?:이상|초과|위).*?(?:매도|청산)"
        r"|cci.*?과매수.*?(?:매도|청산)",
        compact,
    )
    if cci_sell:
        val = int(cci_sell.group(1)) if cci_sell.group(1) else 100
        exit_.append(TechnicalSignal(
            indicator="cci", signal_type="sell", period=14, operator=">=", value=float(val),
        ))

    # ── 볼린저밴드 ──
    # 하단/중심선 회복 매수(평균회귀)뿐 아니라 상단 돌파 진입(추세)·하단 도달 청산도 포착한다.
    if re.search(r"볼린저.*?(?:하단|중심선).*?(?:매수|진입)|볼린저밴드.*?(?:매수|진입)|볼린저.*?상단.*?돌파", compact):
        entry.append(TechnicalSignal(indicator="bollinger_bands", signal_type="buy"))
    if re.search(r"볼린저.*?상단.*?(?:매도|청산)|볼린저.*?하단.*?(?:매도|청산|닿|도달)", compact):
        exit_.append(TechnicalSignal(indicator="bollinger_bands", signal_type="sell"))

    # ── 브레이크아웃 (신고가 / 박스권 위로 돌파 / N일 고점 돌파) ──
    breakout_lookback = _extract_breakout_lookback(compact)
    has_high_breakout = bool(
        re.search(r"(?:\d+(?:주|일)?)?신고가.*?(?:돌파|매수|진입|들어가|새로만들)", compact)
        or "브레이크아웃" in compact
        or re.search(r"박스권?.{0,8}돌파", compact)
        or re.search(r"\d+일고점.{0,6}(?:돌파|넘|상향|위로|매수)", compact)
        or re.search(r"고점.{0,4}돌파", compact)
    )
    if has_high_breakout:
        entry.append(TechnicalSignal(
            indicator="breakout", signal_type="buy", lookback_period=breakout_lookback,
        ))

    # ── 박스권 이탈 매도 (박스 하단/저점 하향 이탈 → breakout sell) ──
    has_box_breakdown = bool(
        re.search(r"박스권?.{0,6}(?:안으로|내려|아래|하단|이탈).{0,8}(?:매도|청산|팔)", compact)
        or re.search(r"\d+일저점.{0,6}(?:이탈|깨|하향|무너).{0,8}(?:매도|청산|팔)", compact)
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


_FUNDAMENTAL_PATTERN_SPECS = [
    ("pbr", [r"pbr(?:이|가|은|는)?\s*(\d+(?:\.\d+)?)\s*(?:배)?\s*(이하|미만|이상|초과)?"]),
    ("per", [r"per(?:이|가|은|는)?\s*(\d+(?:\.\d+)?)\s*(?:배)?\s*(이하|미만|이상|초과)?"]),
    ("roe_or_gpa", [r"(?:roe|gpa)(?:이|가|은|는)?\s*(\d+(?:\.\d+)?)%?\s*(이하|미만|이상|초과)?"]),
    ("debt_ratio", [r"(?:부채비율|부채)(?:이|가|은|는)?\s*(\d+(?:\.\d+)?)%?\s*(이하|미만|이상|초과)?"]),
    # 금액 지표(억원 단위)는 '조'+'억' 콤보를 결정적으로 합산한다: (조 부분)?(억 부분)?(연산자)?.
    ("market_cap", [r"시가총액(?:이|가|은|는)?\s*(?:(\d+(?:\.\d+)?)조)?\s*(?:(\d+(?:\.\d+)?)(?:억원|억))?\s*(이하|미만|이상|초과)?"]),
    ("trading_value", [r"(?:거래대금|일평균거래대금)(?:이|가|은|는)?\s*(?:(\d+(?:\.\d+)?)조)?\s*(?:(\d+(?:\.\d+)?)(?:억원|억))?\s*(이하|미만|이상|초과)?"]),
]

# 금액 지표는 값을 (조 부분 × 10000) + (억 부분)으로 합산한다. 그 외는 group(1) 단일 값.
_AMOUNT_METRICS = {"market_cap", "trading_value"}

_OPERATOR_BY_KOREAN = {
    "이하": "<=",
    "미만": "<",
    "이상": ">=",
    "초과": ">",
}


def _default_operator_for_metric(metric: str) -> str:
    if metric in {"pbr", "per", "debt_ratio"}:
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
    compact = re.sub(r"\s+", "", user_input.lower())
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
    compact = re.sub(r"\s+", "", user_input.lower())
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
    compact = re.sub(r"\s+", "", user_input.lower())
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
    compact = re.sub(r"\s+", "", user_input.lower())
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

    match = re.search(r"(\d+)개월", compact)
    if match:
        return int(match.group(1)) * 21
    match = re.search(r"(\d+)일(?:간)?보유", compact)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)일(?:정도)?지나면(?:정리|매도|청산)", compact)
    if match:
        return int(match.group(1))
    return None


def _has_explicit_day_holding(user_input: str) -> bool:
    """일(日) 단위로 명시된 보유기간 표현이 있는지 본다('20일 보유'·'30일 지나면 매도').

    개월/년 키워드(3개월·1년)는 모멘텀 룩백('최근 3개월 오른')과 구분이 안 되지만,
    'N일 보유'/'N일 지나면 정리'는 명백한 고정 보유기간이다. 랭킹 전략에서 보유기간을
    비울 때 이 명시적 표현은 보존하기 위한 판별자다.
    """
    compact = re.sub(r"\s+", "", user_input.lower())
    return bool(
        re.search(r"(\d+)일(?:간)?보유", compact)
        or re.search(r"(\d+)일(?:정도)?지나면(?:정리|매도|청산)", compact)
    )


def _extract_rebalancing_period(user_input: str, hold_period_days: Optional[int]) -> str:
    compact = re.sub(r"\s+", "", user_input.lower())
    if re.search(r"매일|일간리밸런싱|날마다|하루에한번", compact):
        return "daily"
    if re.search(r"매주|주간리밸런싱|일주일에한번|한주에한번|주1회|주에한번", compact):
        return "weekly"
    # 격월은 반드시 monthly보다 먼저 — monthly의 '달에한번'이 '두달에한번'을 삼키기 때문.
    if re.search(r"격월|두달에한번|2개월에한번|2달에한번|두달마다|2개월마다|2달마다", compact):
        return "bimonthly"
    if "매월" in compact or "월간리밸런싱" in compact or re.search(r"한달에한번|달에한번|월1회|매달", compact):
        return "monthly"
    if "분기" in compact:
        return "quarterly"
    if "매년" in compact or "연간리밸런싱" in compact:
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
    compact = re.sub(r"\s+", "", user_input.lower())
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
    m = re.search(r"백테스트\D{0,8}(\d+)년|(\d+)년(?:간|동안)?\D{0,6}백테스트", compact)
    if m:
        years = m.group(1) or m.group(2)
        return {"1": "1y", "3": "3y", "5": "5y"}.get(years)
    return None


_YEAR = r"((?:19|20)\d{2})"


def _extract_backtest_dates(user_input: str) -> tuple[Optional[str], Optional[str]]:
    """'2002년부터 2005년까지' 같은 명시적 연도 범위를 (시작일, 종료일) ISO로 추출한다.

    상대 기간(1y/3y/5y)과 달리 명시적 연·범위는 결정적으로 처리한다(LLM 비의존).
    없으면 (None, None). 시작만/종료만 언급되면 한쪽만 채운다.
    """
    compact = re.sub(r"\s+", "", user_input)

    # YYYY (부터|~|-|에서) YYYY (까지)?  — 양끝 모두 명시
    span = re.search(rf"{_YEAR}년?(?:부터|에서|~|-|–|—){_YEAR}년?(?:까지)?", compact)
    if span:
        y1, y2 = int(span.group(1)), int(span.group(2))
        if y1 > y2:
            y1, y2 = y2, y1
        return f"{y1}-01-01", f"{y2}-12-31"

    # 'YYYY년만' — 단일 연도
    only = re.search(rf"{_YEAR}년?만", compact)
    if only:
        y = int(only.group(1))
        return f"{y}-01-01", f"{y}-12-31"

    start_match = re.search(rf"{_YEAR}년?부터", compact)
    end_match = re.search(rf"{_YEAR}년?까지", compact)
    start = f"{int(start_match.group(1))}-01-01" if start_match else None
    end = f"{int(end_match.group(1))}-12-31" if end_match else None
    return start, end


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


def _extract_initial_capital(user_input: str) -> float:
    compact = re.sub(r"\s+", "", user_input.lower())
    # 거래대금/시가총액 필터의 '억' 수치를 초기자금으로 오인하지 않도록 먼저 제거한다.
    compact = _strip_amount_filter_phrases(compact)
    match = re.search(r"(\d+(?:\.\d+)?)억(?:(\d+(?:\.\d+)?)천?만)?", compact)
    if match:
        capital = float(match.group(1)) * 100_000_000
        if match.group(2):
            capital += float(match.group(2)) * 10_000_000
        return capital

    match = re.search(r"(\d+(?:\.\d+)?)천만원", compact)
    if match:
        return float(match.group(1)) * 10_000_000

    match = re.search(r"(\d+(?:\.\d+)?)만원", compact)
    if match:
        return float(match.group(1)) * 10_000

    return 10_000_000.0


def _extract_execution_timing(user_input: str) -> str:
    compact = re.sub(r"\s+", "", user_input.lower())
    if "당일종가" in compact or "현재종가" in compact:
        return "current_close"
    return "next_open"


def _extract_rate(user_input: str, label: str, default: float) -> float:
    compact = re.sub(r"\s+", "", user_input.lower())
    match = re.search(rf"{label}(\d+(?:\.\d+)?)%", compact)
    return float(match.group(1)) if match else default


def _extract_trailing_stop_pct(user_input: str) -> Optional[float]:
    compact = re.sub(r"\s+", "", user_input.lower())
    patterns = [
        r"트레일링(?:스탑|스톱)?(\d+(?:\.\d+)?)%",
        r"최고가대비(\d+(?:\.\d+)?)%하락",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return float(match.group(1))
    return None


def _extract_max_mdd_limit_pct(user_input: str) -> Optional[float]:
    compact = re.sub(r"\s+", "", user_input.lower())
    patterns = [
        r"mdd(\d+(?:\.\d+)?)%.*?(?:초과|이상)",
        r"낙폭(\d+(?:\.\d+)?)%.*?(?:초과|이상)",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return float(match.group(1))
    return None


def _parse_rule_based_strategy(user_input: str) -> Optional[ParsedStrategy]:
    """
    Fast path for explicit, common strategies.

    This keeps the model unchanged, but avoids model inference when the prompt
    contains enough deterministic slots to build the same ParsedStrategy shape.
    Ambiguous prompts still fall through to the LLM.
    """
    fundamental_filters = _extract_fundamental_filters(user_input)
    entry_signals, exit_signals = _extract_technical_signals(user_input)
    hold_period_days = _extract_hold_period_days(user_input)
    ranking_metric, ranking_lookback_days = _extract_ranking(user_input)

    has_entry = bool(fundamental_filters or entry_signals or ranking_metric)
    has_exit = bool(exit_signals or hold_period_days)
    has_risk_exit = bool(
        re.search(
            r"손절|익절|트레일링|최고가대비|mdd|낙폭|수익실현|수익확정|목표수익",
            re.sub(r"\s+", "", user_input.lower()),
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
    # 지정했다면 그게 회전/청산 수단이므로 요청하지 않은 리밸런싱을 임의로 주입하지 않는다.
    # (랭킹 전략의 회전은 리밸런싱이 구동하므로 유지; '3개월' 같은 룩백이 보유기간으로 오인돼도
    # 아래에서 보유기간을 비운다.)
    if (
        periodic_rebalance
        and rebalancing_period == "none"
        and (ranking_metric or not (has_exit or has_risk_exit))
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
_TRAILING_CUE = r"(?:트레일링(?:스탑|스톱)?|최고가대비)"
# 다른 리스크 필드 키워드를 사이에 두고는 연결하지 않아 오인식("손절 없이 익절 10%")을 막는다.
_STOP_LOSS_BLOCK = r"익절|수익실현|수익확정|목표수익|트레일링"
_TAKE_PROFIT_BLOCK = r"손절|손실|트레일링"
_TRAILING_BLOCK = r"손절|익절"


# "매도/청산" 외에 구어체 "팔고/팔아/팔자/팔래/팔면/팔게/팔까"도 매도 동사로 인정
_SELL_VERB = r"(?:매도|청산|팔[고아자래면게까])"

# 필드 키워드가 없는 동사형 표현(주로 최초 입력) 폴백 패턴.
_TAKE_PROFIT_VERB_PATTERNS = (
    rf"수익이?(\d+(?:\.\d+)?)%이상.*?{_SELL_VERB}",
    rf"(\d+(?:\.\d+)?)%이상수익.*?{_SELL_VERB}",
    rf"(\d+(?:\.\d+)?)%수익.*?{_SELL_VERB}",
    rf"수익이?(\d+(?:\.\d+)?)%.*?{_SELL_VERB}",
)
_STOP_LOSS_VERB_PATTERNS = (
    r"손실이?(\d+(?:\.\d+)?)%이상.*?(?:매도|청산)",
    r"(\d+(?:\.\d+)?)%이상하락.*?(?:매도|청산)",
    r"(\d+(?:\.\d+)?)%하락.*?(?:매도|청산)",
    r"-(\d+(?:\.\d+)?)%.*?(?:매도|청산)",
)


def _match_risk_pct(compact: str, cue: str, blocker: str = "") -> Optional[float]:
    """필드 키워드(cue)와 퍼센트가 떨어져 있어도 같은 절 안이면 값을 추출한다.

    표현별 패턴을 늘리는 대신 '키워드 ~ %' / '% ~ 키워드' 두 방향 한 규칙으로 일반화한다.
    blocker(다른 리스크 필드 키워드)가 사이에 끼면 연결하지 않아 오인식을 막는다.
    compact는 공백 제거·소문자화된 입력이다."""
    gap = rf"(?:(?!{blocker})[^%])*?" if blocker else r"[^%]*?"
    for pattern in (rf"{cue}{gap}-?(\d+(?:\.\d+)?)%", rf"-?(\d+(?:\.\d+)?)%{gap}{cue}"):
        match = re.search(pattern, compact)
        if match:
            return float(match.group(1))
    return None


def _first_pct_match(compact: str, patterns: tuple[str, ...]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return float(match.group(1))
    return None


def extract_risk_field_overrides(user_input: str) -> dict[str, Optional[float]]:
    """프롬프트에서 '규칙 기반으로 결정적으로' 바뀐 리스크 필드만 추출한다.

    이것이 리스크 필드(손절/익절/트레일링)의 **단일 진실 소스**다. 값이 잡히면
    {field: value}, 삭제 의도면 {field: None}, 못 찾으면 키 없음.
    파서(_apply_prompt_overrides)와 API가 공유하여, 프론트가 자체 정규식으로
    리스크 변경을 다시 추측하지 않고 이 결과를 그대로 신뢰하게 한다.
    """
    compact = re.sub(r"\s+", "", user_input.lower())
    is_deleting = any(kw in compact for kw in _DELETE_TERMS)
    out: dict[str, Optional[float]] = {}

    # ── 익절(take_profit): 키워드(익절/수익실현/수익확정/목표수익) → 동사형 폴백 ──
    if is_deleting and any(kw in compact for kw in ["익절", "takeprofit", "익절률"]):
        out["take_profit_pct"] = None
    else:
        value = _match_risk_pct(compact, _TAKE_PROFIT_CUE, blocker=_TAKE_PROFIT_BLOCK)
        if value is None:
            value = _first_pct_match(compact, _TAKE_PROFIT_VERB_PATTERNS)
        if value is not None:
            out["take_profit_pct"] = value

    # ── 손절(stop_loss): "손절" 키워드 → "손실·하락+매도", "-N% 매도" 폴백 ──
    if is_deleting and any(kw in compact for kw in ["손절", "stoploss", "스탑로스"]):
        out["stop_loss_pct"] = None
    else:
        value = _match_risk_pct(compact, _STOP_LOSS_CUE, blocker=_STOP_LOSS_BLOCK)
        if value is None:
            value = _first_pct_match(compact, _STOP_LOSS_VERB_PATTERNS)
        if value is not None:
            out["stop_loss_pct"] = value

    # ── 트레일링 스탑: "트레일링/최고가대비" 키워드 + % ──
    if is_deleting and any(kw in compact for kw in ["트레일링", "trailingstop", "최고가대비"]):
        out["trailing_stop_pct"] = None
    else:
        value = _match_risk_pct(compact, _TRAILING_CUE, blocker=_TRAILING_BLOCK)
        if value is not None:
            out["trailing_stop_pct"] = value

    return out


def _apply_prompt_overrides(parsed: ParsedStrategy, user_input: str) -> ParsedStrategy:
    updates: dict[str, object] = {}
    explicit_universe = _extract_explicit_universe(user_input)
    if explicit_universe is not None:
        updates["universe"] = explicit_universe

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

    # ── Step 1: LLM 환각 신호 제거 (프롬프트에 언급되지 않은 지표 제거) ──
    validated_entry = _validate_signals(list(parsed.entry_signals), user_input)
    validated_exit = _validate_signals(list(parsed.exit_signals), user_input)
    if len(validated_entry) != len(parsed.entry_signals):
        updates["entry_signals"] = validated_entry
    if len(validated_exit) != len(parsed.exit_signals):
        updates["exit_signals"] = validated_exit

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
    r"수익률.{0,6}(?:상위|높은|좋은|top)",
    r"(?:상위|높은|좋은).{0,6}수익률",
    r"등락률.{0,6}(?:상위|높은)",
    r"수익률.{0,4}순위",
    r"상대강도",
    r"모멘텀.{0,5}(?:상위|순위|랭킹|상위권)",
    r"(?:상승률|많이오른|꾸준히오른).{0,8}(?:상위|상위권|순)",
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
    ("debt_ratio", (r"부채",),
     "부채비율은 몇 % 이하로 할까요? (예: 100% 이하)", "부채비율 100% 이하", "부채비율 50% 이하"),
    ("market_cap", (r"시가총액", r"시총"),
     "시가총액은 몇 억 이상으로 할까요? (예: 1000억 이상)", "시가총액 1000억 이상", "시가총액 5000억 이상"),
    ("trading_value", (r"거래대금",),
     "거래대금은 몇 억 이상으로 할까요? (예: 100억 이상)", "거래대금 100억 이상", "거래대금 300억 이상"),
)


def _detect_qualitative_metrics(compact: str) -> list[tuple[str, str, str, str]]:
    """언급된 재무 지표 spec들을 입력 순서대로 반환한다.

    이 헬퍼는 진입 규칙이 하나도 구조화되지 않았을 때만 쓰이므로(호출부의 가드 참고),
    여기서 잡히는 지표는 모두 '이름만 말하고 숫자는 안 준' 미구조화 지표다.
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


def detect_missing_entry_clarification(
    parsed: ParsedStrategy,
    user_prompt: str = "",
) -> tuple[Optional[str], Optional[List[str]]]:
    """진입(종목 선정) 규칙을 하나도 구조화하지 못했을 때만 되묻는다.

    파서가 사용자의 진입 의도를 표현하지 못하면 — 미지원 전략 유형이라 못 잡은 경우 포함 —
    조용히 버리지 않고 명시적으로 확인한다. 상대강도(수익률 순위) 랭킹처럼 아직 지원 안 되는
    유형은 가까운 추세추종으로 바꿀 수 있게 안내한다. 진입 규칙이 있으면 (None, None).

    유니버스·초기자금 등 다른 누락은 일부러 묻지 않는다(기본값이 있어 노이즈만 됨).
    여기서는 '진입을 통째로 잃는' 침묵 누락만 막는다.
    """
    if parsed.fundamental_filters or parsed.entry_signals or parsed.ranking_metric:
        return (None, None)
    compact = re.sub(r"\s+", "", user_prompt.lower())
    if _mentions_relative_strength_ranking(compact):
        return (_RELATIVE_STRENGTH_QUESTION, list(_RELATIVE_STRENGTH_SUGGESTIONS))
    # 지표는 말했지만 숫자가 빠진 경우("PER이 낮고 부채비율이 낮은") — 그 지표별로 숫자를 되묻는다.
    metrics = _detect_qualitative_metrics(compact)
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
