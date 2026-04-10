"""
자연어 전략 파서 (NL Strategy Parser)

사용자가 한국어로 입력한 전략 설명을 구조화된 ParsedStrategy로 변환한다.
LLM 백엔드: Ollama (instructor) 또는 MLX (outlines)
"""

from __future__ import annotations

import json
import re
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


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

    # ── 포트폴리오
    max_positions: int = Field(
        default=10, ge=1, le=100,
        description="동시 보유 최대 종목 수. '10개', '20종목' 등에서 추출"
    )
    hold_period_days: Optional[int] = Field(
        default=None,
        description="최대 보유 기간(거래일). 1년=252, 6개월=126, 3개월=63, 1개월=21. 없으면 null"
    )
    rebalancing_period: Literal["none", "monthly", "quarterly", "yearly"] = Field(
        default="none",
        description="정기 리밸런싱 주기. '매월'=monthly, '분기'=quarterly, '매년/1년마다'=yearly, 언급없음=none"
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
    max_positions: Optional[int] = Field(default=None, ge=1, le=100)
    hold_period_days: Optional[int] = None
    rebalancing_period: Optional[Literal["none", "monthly", "quarterly", "yearly"]] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    max_mdd_limit_pct: Optional[float] = None
    backtest_period: Optional[Literal["1y", "3y", "5y", "full"]] = None
    initial_capital: Optional[float] = None
    execution_timing: Optional[Literal["next_open", "current_close"]] = None
    fee_rate: Optional[float] = None
    slippage_rate: Optional[float] = None


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
- MACD 크로스 → indicator: "macd", signal_type: "buy", mode: "crossover"
- 볼린저밴드 하단 → indicator: "bollinger_bands", signal_type: "buy"
- 볼린저밴드 상단 → indicator: "bollinger_bands", signal_type: "sell"
- 52주 신고가 돌파 → indicator: "breakout", signal_type: "buy", lookback_period: 252
- AI 상승 예측 매수 / AI 모델 매수 → indicator: "ai_model", signal_type: "buy", threshold: 70
- AI 하락 예측 매도 / AI 모델 매도 → indicator: "ai_drop_model", signal_type: "sell", threshold: 70
- AI 모델이 X% 이상 확률로 상승 예측 → indicator: "ai_model", signal_type: "buy", threshold: X

### 보유기간 / 리밸런싱
- '1년 보유' → hold_period_days: 252, rebalancing_period: "yearly"
- '6개월 보유' → hold_period_days: 126, rebalancing_period: "none"
- '매월 리밸런싱' → rebalancing_period: "monthly"
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
"""


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
        backend: Literal["ollama", "mlx"] = "mlx",
        model_7b: str = "mlx-community/Qwen2.5-7B-Instruct-4bit",
        model_32b: str = "mlx-community/Qwen2.5-32B-Instruct-4bit",
        ollama_model_7b: str = "qwen2.5:7b",
        ollama_model_32b: str = "qwen2.5:32b",
        max_retries: int = 3,
    ):
        self.backend = backend
        self.model_7b = model_7b
        self.model_32b = model_32b
        self.ollama_model_7b = ollama_model_7b
        self.ollama_model_32b = ollama_model_32b
        self.max_retries = max_retries
        self._client = None
        # MLX: 7B (parse + modification용), 32B (미사용)
        self._generator_7b = None
        self._diff_generator_7b = None
        self._generator_32b = None
        self._diff_generator_32b = None
        self._mlx_model_7b = None
        self._tokenizer_7b = None
        self._mlx_model_32b = None
        self._tokenizer_32b = None

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
            OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"),
            mode=instructor.Mode.JSON,
        )

    def _init_mlx_7b(self):
        """7B 모델 초기화 (parse + modification용, 서버 시작 시 로드)"""
        if self._generator_7b is not None:
            return
        try:
            import outlines
            import outlines.models as models
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install outlines mlx-lm 필요")

        print(f"[NLParser] 7B 모델 로딩: {self.model_7b} ...", flush=True)
        mlx_model, tokenizer = mlx_lm.load(self.model_7b)
        self._mlx_model_7b = mlx_model
        self._tokenizer_7b = tokenizer
        self._outlines_model_7b = models.from_mlxlm(mlx_model, tokenizer)
        self._generator_7b = outlines.Generator(self._outlines_model_7b, ParsedStrategy)
        self._diff_generator_7b = outlines.Generator(self._outlines_model_7b, ParsedStrategyDiff)
        print("[NLParser] 7B 모델 로딩 완료", flush=True)

    def _init_mlx_32b(self):
        """32B 모델 초기화 (modification용, 첫 수정 요청 시 lazy 로드)"""
        if self._generator_32b is not None:
            return
        try:
            import outlines
            import outlines.models as models
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install outlines mlx-lm 필요")

        print(f"[NLParser] 32B 모델 로딩: {self.model_32b} ...", flush=True)
        mlx_model, tokenizer = mlx_lm.load(self.model_32b)
        self._mlx_model_32b = mlx_model
        self._tokenizer_32b = tokenizer
        self._outlines_model_32b = models.from_mlxlm(mlx_model, tokenizer)
        self._generator_32b = outlines.Generator(self._outlines_model_32b, ParsedStrategy)
        self._diff_generator_32b = outlines.Generator(self._outlines_model_32b, ParsedStrategyDiff)
        print("[NLParser] 32B 모델 로딩 완료", flush=True)

    # 하위 호환: preload_nl_parser에서 _init_mlx() 호출 지원
    def _init_mlx(self):
        self._init_mlx_7b()

    # ── 파싱 ─────────────────────────────────────────────────────────────────

    def parse(self, user_input: str) -> ParsedStrategy:
        """자연어 입력 → ParsedStrategy (7B 사용)"""
        if self.backend == "mlx":
            parsed = self._parse_mlx(user_input)
        else:
            parsed = self._parse_ollama(user_input)
        return _apply_prompt_overrides(parsed, user_input)

    def parse_modification(self, user_input: str, previous: dict) -> ParsedStrategy:
        """수정 요청: diff만 LLM으로 추출 후 previous와 병합 (32B 사용)"""
        if self.backend == "mlx":
            diff = self._modify_mlx(user_input, previous)
        else:
            diff = self._modify_ollama(user_input, previous)

        # diff의 non-null 필드만 previous에 덮어씀
        merged = {**previous}
        for field, val in diff.model_dump().items():
            if val is not None:
                merged[field] = val
        return _apply_prompt_overrides(ParsedStrategy.model_validate(merged), user_input)

    def _modify_mlx(self, user_input: str, previous: dict) -> ParsedStrategyDiff:
        self._init_mlx_7b()
        prompt = (
            f"{MODIFY_PROMPT}\n\n"
            f"현재 전략:\n{json.dumps(previous, ensure_ascii=False)}\n\n"
            f"수정 요청: \"{user_input}\"\n출력:"
        )
        result = self._diff_generator_7b(prompt, max_tokens=1024)
        if isinstance(result, str):
            return ParsedStrategyDiff.model_validate_json(result)
        return result

    def _modify_ollama(self, user_input: str, previous: dict) -> ParsedStrategyDiff:
        self._init_ollama()
        result = self._client.chat.completions.create(
            model=self.ollama_model_7b,
            response_model=ParsedStrategyDiff,
            max_retries=self.max_retries,
            messages=[
                {"role": "system", "content": MODIFY_PROMPT},
                {"role": "user", "content": (
                    f"현재 전략:\n{json.dumps(previous, ensure_ascii=False)}\n\n"
                    f"수정 요청: \"{user_input}\""
                )},
            ],
        )
        return result

    def _parse_mlx(self, user_input: str) -> ParsedStrategy:
        self._init_mlx_7b()
        prompt = f"{SYSTEM_PROMPT}\n\n입력: \"{user_input}\"\n출력:"
        result = self._generator_7b(prompt, max_tokens=1024)
        if isinstance(result, str):
            return ParsedStrategy.model_validate_json(result)
        return result

    def _parse_ollama(self, user_input: str) -> ParsedStrategy:
        self._init_ollama()
        result = self._client.chat.completions.create(
            model=self.ollama_model_7b,
            response_model=ParsedStrategy,
            max_retries=self.max_retries,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
        )
        return result


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


def _apply_prompt_overrides(parsed: ParsedStrategy, user_input: str) -> ParsedStrategy:
    updates: dict[str, object] = {}
    explicit_universe = _extract_explicit_universe(user_input)
    if explicit_universe is not None:
        updates["universe"] = explicit_universe

    compact = re.sub(r"\s+", "", user_input.lower())
    risk_exit_detected = False

    take_profit_patterns = [
        r"수익(\d+(?:\.\d+)?)%이상(?:이면|일때|일시|시)?(?:매도|청산)",
        r"(\d+(?:\.\d+)?)%이상수익(?:이면|일때|일시|시)?(?:매도|청산)",
        r"(\d+(?:\.\d+)?)%수익(?:이면|일때|일시|시)?(?:매도|청산)",
    ]
    for pattern in take_profit_patterns:
        match = re.search(pattern, compact)
        if match:
            updates["take_profit_pct"] = float(match.group(1))
            risk_exit_detected = True
            break

    stop_loss_patterns = [
        r"손실(\d+(?:\.\d+)?)%이상(?:이면|일때|일시|시)?(?:매도|청산)",
        r"(\d+(?:\.\d+)?)%이상하락(?:이면|일때|일시|시)?(?:매도|청산)",
        r"(\d+(?:\.\d+)?)%하락(?:이면|일때|일시|시)?(?:매도|청산)",
    ]
    for pattern in stop_loss_patterns:
        match = re.search(pattern, compact)
        if match:
            updates["stop_loss_pct"] = float(match.group(1))
            risk_exit_detected = True
            break

    if risk_exit_detected and not _mentions_technical_exit_terms(compact):
        updates["exit_signals"] = []

    if not updates:
        return parsed
    return parsed.model_copy(update=updates)


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
            "• **AI 신호**: \"AI 모델이 70% 이상 확률로 상승 예측한 종목\"",
            [
                "PBR 1 이하, PER 10 이하 저평가 종목",
                "골든크로스(5일/20일) 발생 시 매수",
                "RSI 30 이하 과매도 구간에서 매수",
                "AI 모델 상승 예측 종목 매수",
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
