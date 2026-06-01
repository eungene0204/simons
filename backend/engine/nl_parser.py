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
- MACD, 볼린저밴드, 신고가 돌파, 거래량 급증, AI 상승/하락 예측을 해당 indicator로 변환
- 1년/6개월/3개월/1개월 보유 → 252/126/63/21 거래일
- 매월/분기/매년 리밸런싱 → monthly/quarterly/yearly
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
        backend: Literal["ollama", "mlx"] = "mlx",
        model_7b: str = "mlx-community/Qwen3.5-9B-OptiQ-4bit",
        model_32b: str = "mlx-community/Qwen3.5-9B-OptiQ-4bit",
        ollama_model_7b: str = "qwen3.5:9b",
        ollama_model_32b: str = "qwen3.5:9b",
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

    def _model_log_label(self, model_name: str) -> str:
        """로그에 표시할 사람이 읽기 쉬운 모델 라벨을 만든다."""
        model_id = model_name.split("/")[-1]
        normalized = model_id.replace("-OptiQ-4bit", "").replace("-Instruct-4bit", "")
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
            OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"),
            mode=instructor.Mode.JSON,
        )

    def _init_mlx_7b(self):
        """기본 MLX 모델 초기화 (parse + modification용, 서버 시작 시 로드)"""
        if self._generator_7b is not None:
            return
        try:
            import outlines
            import outlines.models as models
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install outlines mlx-lm 필요")

        log_label = self._model_log_label(self.model_7b)
        print(f"[NLParser] {log_label} 모델 로딩: {self.model_7b} ...", flush=True)
        mlx_model, tokenizer = mlx_lm.load(self.model_7b)
        self._mlx_model_7b = mlx_model
        self._tokenizer_7b = tokenizer
        self._outlines_model_7b = models.from_mlxlm(mlx_model, tokenizer)
        self._generator_7b = outlines.Generator(self._outlines_model_7b, ParsedStrategy)
        self._diff_generator_7b = outlines.Generator(self._outlines_model_7b, ParsedStrategyDiff)
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

    # 하위 호환: preload_nl_parser에서 _init_mlx() 호출 지원
    def _init_mlx(self):
        self._init_mlx_7b()

    # ── 파싱 ─────────────────────────────────────────────────────────────────

    def parse(self, user_input: str) -> ParsedStrategy:
        """자연어 입력 → ParsedStrategy (7B 사용)"""
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
        self._init_mlx_7b()
        prompt = (
            f"{MODIFY_PROMPT}\n\n"
            f"현재 전략:\n{json.dumps(previous, ensure_ascii=False)}\n\n"
            f"수정 요청: \"{user_input}\"\n출력:"
        )
        result = self._diff_generator_7b(prompt, max_tokens=1024)
        if isinstance(result, str):
            return _parse_model_json_response(result, ParsedStrategyDiff)
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

    def chat(self, system_prompt: str, user_message: str, max_tokens: int = 512) -> str:
        """자유형식 텍스트 생성 — 코치/요약 등 비구조화 응답용 (MLX 전용)."""
        self._init_mlx_7b()
        try:
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install mlx-lm 필요")

        tokenizer = self._tokenizer_7b
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
            self._mlx_model_7b, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False
        ).strip()

    def stream_chat(self, system_prompt: str, user_message: str, max_tokens: int = 512):
        """토큰 단위 스트리밍 생성 — 각 yield마다 누적된 전체 텍스트를 반환 (MLX 전용)."""
        self._init_mlx_7b()
        try:
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install mlx-lm 필요")

        tokenizer = self._tokenizer_7b
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
            self._mlx_model_7b, tokenizer, prompt=prompt, max_tokens=max_tokens
        ):
            # resp.text is the incremental delta for this step
            yield resp.text

    def _parse_mlx(self, user_input: str) -> ParsedStrategy:
        self._init_mlx_7b()
        prompt = f"{COMPACT_SYSTEM_PROMPT}\n\n입력: \"{user_input}\"\n출력:"
        result = self._generator_7b(prompt, max_tokens=1024)
        if isinstance(result, str):
            return _parse_model_json_response(result, ParsedStrategy)
        return result

    def _parse_ollama(self, user_input: str) -> ParsedStrategy:
        self._init_ollama()
        result = self._client.chat.completions.create(
            model=self.ollama_model_7b,
            response_model=ParsedStrategy,
            max_retries=self.max_retries,
            messages=[
                {"role": "system", "content": COMPACT_SYSTEM_PROMPT},
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


def _validate_signals(
    signals: list[TechnicalSignal],
    user_input: str,
) -> list[TechnicalSignal]:
    """
    LLM이 생성한 신호 중 프롬프트에 실제로 언급된 지표만 남긴다.
    프롬프트에 키워드가 없는 지표는 LLM 환각으로 간주하고 제거한다.
    """
    compact = re.sub(r"\s+", "", user_input.lower())
    validated: list[TechnicalSignal] = []
    for sig in signals:
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

    # ── RSI 매수/매도 ──
    rsi_buy_match = re.search(r"rsi\s*(\d+)\s*이하.*?매수|rsi.*?과매도.*?매수", compact)
    if rsi_buy_match:
        val = int(rsi_buy_match.group(1)) if rsi_buy_match.group(1) else 30
        entry.append(TechnicalSignal(
            indicator="rsi", signal_type="buy", period=14, operator="<=", value=float(val),
        ))
    rsi_sell_match = re.search(r"rsi\s*(\d+)\s*이상.*?매도|rsi.*?과매수.*?매도", compact)
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

    # ── 볼린저밴드 ──
    if re.search(r"볼린저.*?하단.*?매수|볼린저밴드.*?매수", compact):
        entry.append(TechnicalSignal(indicator="bollinger_bands", signal_type="buy"))
    if re.search(r"볼린저.*?상단.*?매도|볼린저밴드.*?매도", compact):
        exit_.append(TechnicalSignal(indicator="bollinger_bands", signal_type="sell"))

    # ── 브레이크아웃 ──
    breakout_match = re.search(
        r"(?:(\d+)(주|일)?신고가.*?(?:돌파|매수|진입|들어가|새로만들)|브레이크아웃)",
        compact,
    )
    if breakout_match:
        lookback = 20
        period_text = breakout_match.group(1)
        period_unit = breakout_match.group(2)
        if period_text:
            period_value = int(period_text)
            if period_unit == "주":
                lookback = period_value * 5 if period_value < 52 else 252
            elif period_unit == "일":
                lookback = period_value
            else:
                lookback = 252 if period_value == 52 else period_value
        entry.append(TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=lookback))

    # ── 거래량 급증 ──
    if (
        "거래량급증" in compact
        or "거래량폭발" in compact
        or "거래량도평소보다확늘" in compact
        or "거래량이평소보다확늘" in compact
        or "거래량평소보다확늘" in compact
        or "volumespike" in compact
    ):
        entry.append(TechnicalSignal(indicator="volume_spike", signal_type="buy", period=20))

    return entry, exit_


_FUNDAMENTAL_PATTERN_SPECS = [
    ("pbr", [r"pbr(?:이|가|은|는)?\s*(\d+(?:\.\d+)?)\s*(?:배)?\s*(이하|미만|이상|초과)?"]),
    ("per", [r"per(?:이|가|은|는)?\s*(\d+(?:\.\d+)?)\s*(?:배)?\s*(이하|미만|이상|초과)?"]),
    ("roe_or_gpa", [r"(?:roe|gpa)\s*(\d+(?:\.\d+)?)%?\s*(이하|미만|이상|초과)?"]),
    ("debt_ratio", [r"(?:부채비율|부채)\s*(\d+(?:\.\d+)?)%?\s*(이하|미만|이상|초과)?"]),
    ("market_cap", [r"시가총액\s*(\d+(?:\.\d+)?)\s*(억|억원)?\s*(이하|미만|이상|초과)?"]),
    ("trading_value", [r"(?:거래대금|일평균거래대금)\s*(\d+(?:\.\d+)?)\s*(억|억원)?\s*(이하|미만|이상|초과)?"]),
]

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


def _extract_fundamental_filters(user_input: str) -> list[FundamentalFilter]:
    compact = re.sub(r"\s+", "", user_input.lower())
    filters: list[FundamentalFilter] = []
    seen: set[tuple[str, str, float]] = set()

    for metric, patterns in _FUNDAMENTAL_PATTERN_SPECS:
        for pattern in patterns:
            for match in re.finditer(pattern, compact):
                raw_value = float(match.group(1))
                op_word = next(
                    (group for group in match.groups()[1:] if group in _OPERATOR_BY_KOREAN),
                    None,
                )
                operator = _OPERATOR_BY_KOREAN.get(op_word or "", _default_operator_for_metric(metric))
                value = raw_value
                key = (metric, operator, value)
                if key in seen:
                    continue
                filters.append(FundamentalFilter(metric=metric, operator=operator, value=value))
                seen.add(key)

    return filters


def _extract_max_positions(user_input: str) -> Optional[int]:
    compact = re.sub(r"\s+", "", user_input.lower())
    patterns = [
        r"(?:최대|상위)?(\d+)(?:개|종목)",
        r"maxpositions?(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return max(1, min(100, int(match.group(1))))
    return None


def _extract_hold_period_days(user_input: str) -> Optional[int]:
    compact = re.sub(r"\s+", "", user_input.lower())
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


def _extract_rebalancing_period(user_input: str, hold_period_days: Optional[int]) -> str:
    compact = re.sub(r"\s+", "", user_input.lower())
    if "매월" in compact or "월간리밸런싱" in compact:
        return "monthly"
    if "분기" in compact:
        return "quarterly"
    if "매년" in compact or "연간리밸런싱" in compact:
        return "yearly"
    if hold_period_days == 252 and "보유" in compact:
        return "yearly"
    return "none"


def _extract_backtest_period(user_input: str) -> str:
    compact = re.sub(r"\s+", "", user_input.lower())
    if "전체기간" in compact or "full" in compact:
        return "full"
    if "1년백테스트" in compact or "1y" in compact:
        return "1y"
    if "3년백테스트" in compact or "3y" in compact:
        return "3y"
    if "5년백테스트" in compact or "5y" in compact:
        return "5y"
    return "5y"


def _extract_initial_capital(user_input: str) -> float:
    compact = re.sub(r"\s+", "", user_input.lower())
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

    has_entry = bool(fundamental_filters or entry_signals)
    has_exit = bool(exit_signals or hold_period_days)
    has_risk_exit = bool(
        re.search(r"손절|익절|트레일링|최고가대비|mdd|낙폭", re.sub(r"\s+", "", user_input.lower()))
    )
    if not has_entry or not (has_exit or has_risk_exit):
        return None

    parsed = ParsedStrategy(
        description=user_input,
        universe=_extract_explicit_universe(user_input) or ["KOSPI200"],
        fundamental_filters=fundamental_filters,
        entry_signals=entry_signals,
        exit_signals=exit_signals,
        max_positions=_extract_max_positions(user_input) or 10,
        hold_period_days=hold_period_days,
        rebalancing_period=_extract_rebalancing_period(user_input, hold_period_days),
        stop_loss_pct=None,
        take_profit_pct=None,
        trailing_stop_pct=_extract_trailing_stop_pct(user_input),
        max_mdd_limit_pct=_extract_max_mdd_limit_pct(user_input),
        backtest_period=_extract_backtest_period(user_input),
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
    parsed = ParsedStrategy(
        description=user_input,
        universe=_extract_explicit_universe(user_input) or ["KOSPI200"],
        fundamental_filters=_extract_fundamental_filters(user_input),
        entry_signals=entry_signals,
        exit_signals=exit_signals,
        max_positions=_extract_max_positions(user_input) or 10,
        hold_period_days=hold_period_days,
        rebalancing_period=_extract_rebalancing_period(user_input, hold_period_days),
        stop_loss_pct=None,
        take_profit_pct=None,
        trailing_stop_pct=_extract_trailing_stop_pct(user_input),
        max_mdd_limit_pct=_extract_max_mdd_limit_pct(user_input),
        backtest_period=_extract_backtest_period(user_input),
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


def _apply_prompt_overrides(parsed: ParsedStrategy, user_input: str) -> ParsedStrategy:
    updates: dict[str, object] = {}
    explicit_universe = _extract_explicit_universe(user_input)
    if explicit_universe is not None:
        updates["universe"] = explicit_universe

    compact = re.sub(r"\s+", "", user_input.lower())

    is_deleting = any(kw in compact for kw in _DELETE_TERMS)
    is_deleting_stop_loss = is_deleting and any(kw in compact for kw in ["손절", "stoploss", "스탑로스"])
    is_deleting_take_profit = is_deleting and any(kw in compact for kw in ["익절", "takeprofit", "익절률"])

    take_profit_patterns = [
        # "수익이 10% 이상 날때도 매도", "수익이 10% 이상이면 매도"
        r"수익이?(\d+(?:\.\d+)?)%이상.*?(?:매도|청산)",
        # "10% 이상 수익이면 매도", "10% 이상 수익시 매도"
        r"(\d+(?:\.\d+)?)%이상수익.*?(?:매도|청산)",
        # "10% 수익이면 매도"
        r"(\d+(?:\.\d+)?)%수익.*?(?:매도|청산)",
        # "수익 10%에서 매도", "수익 10% 매도"
        r"수익이?(\d+(?:\.\d+)?)%.*?(?:매도|청산)",
        # "익절 10%", "익절10%"
        r"익절-?(\d+(?:\.\d+)?)%",
    ]
    if is_deleting_take_profit:
        updates["take_profit_pct"] = None
    else:
        for pattern in take_profit_patterns:
            match = re.search(pattern, compact)
            if match:
                updates["take_profit_pct"] = float(match.group(1))
                break

    stop_loss_patterns = [
        # "손실 10% 이상이면 매도"
        r"손실이?(\d+(?:\.\d+)?)%이상.*?(?:매도|청산)",
        # "10% 이상 하락시 매도", "10% 이상 하락하면 매도"
        r"(\d+(?:\.\d+)?)%이상하락.*?(?:매도|청산)",
        # "10% 하락시 매도", "10% 하락하면 매도"
        r"(\d+(?:\.\d+)?)%하락.*?(?:매도|청산)",
        # "-10% 매도", "-10%에서 매도"
        r"-(\d+(?:\.\d+)?)%.*?(?:매도|청산)",
        # "-10% 손절", "-10%에서 손절"
        r"-(\d+(?:\.\d+)?)%.*?손절",
        # "손절 10%", "손절은 -10%", "손절률 10%"
        r"손절(?:은|은요|은\s*|률은|률|선은|선)?-?(\d+(?:\.\d+)?)%",
    ]
    if is_deleting_stop_loss:
        updates["stop_loss_pct"] = None
    else:
        for pattern in stop_loss_patterns:
            match = re.search(pattern, compact)
            if match:
                updates["stop_loss_pct"] = float(match.group(1))
                break

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
