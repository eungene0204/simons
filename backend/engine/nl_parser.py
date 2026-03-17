"""
자연어 전략 파서 (NL Strategy Parser)

사용자가 한국어로 입력한 전략 설명을 구조화된 ParsedStrategy로 변환한다.
LLM 백엔드: Ollama (instructor) 또는 MLX (outlines)
"""

from __future__ import annotations

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
        "stochastic", "cci", "adx"
    ] = Field(description="지표 종류")
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


class ParsedStrategy(BaseModel):
    """자연어 전략 → 구조화된 전략 스키마"""

    description: str = Field(description="사용자가 입력한 원문 전략 설명 (그대로 복사)")

    # ── 유니버스
    universe: List[Literal["KOSPI", "KOSDAQ", "KOSPI200"]] = Field(
        default=["KOSPI", "KOSDAQ"],
        description="투자 대상 시장. 언급 없으면 ['KOSPI', 'KOSDAQ']. KOSPI200은 명시적 언급 시만"
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

    # ── 백테스트 설정
    backtest_period: Literal["1y", "3y", "5y", "full"] = Field(
        default="5y",
        description="백테스트 기간. 언급 없으면 '5y'"
    )
    initial_capital: float = Field(
        default=10_000_000.0,
        description="초기 자본금(원). 언급 없으면 10000000 (1천만원)"
    )


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

### 보유기간 / 리밸런싱
- '1년 보유' → hold_period_days: 252, rebalancing_period: "yearly"
- '6개월 보유' → hold_period_days: 126, rebalancing_period: "none"
- '매월 리밸런싱' → rebalancing_period: "monthly"
- 기술적 청산 없이 기간 보유면 exit_signals: []

### 종목 수
- '10개', '10종목', '상위 10개' → max_positions: 10

## 예시

입력: "pbr 1이하 per 7이하 종목을 10개 사서 1년간 보유하는 전략"
출력:
{
  "description": "pbr 1이하 per 7이하 종목을 10개 사서 1년간 보유하는 전략",
  "universe": ["KOSPI", "KOSDAQ"],
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
  "backtest_period": "5y",
  "initial_capital": 10000000.0
}
"""


# ─── 파서 클래스 ──────────────────────────────────────────────────────────────

class NLStrategyParser:
    """
    자연어 전략을 ParsedStrategy로 변환.

    백엔드 선택:
    - backend="ollama" : instructor + Ollama HTTP API (범용, 설정 쉬움)
    - backend="mlx"    : outlines + mlx-lm (M1/M2/M3 Mac 전용, 2~3x 빠름)
    """

    def __init__(
        self,
        backend: Literal["ollama", "mlx"] = "mlx",
        model: str = "mlx-community/Qwen2.5-32B-Instruct-4bit",
        ollama_model: str = "qwen2.5:32b",
        max_retries: int = 3,
    ):
        self.backend = backend
        self.model = model
        self.ollama_model = ollama_model
        self.max_retries = max_retries
        self._client = None
        self._generator = None

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

    def _init_mlx(self):
        """outlines + mlx-lm 초기화 (최초 호출 시, 모델 로딩)"""
        if self._generator is not None:
            return
        try:
            import outlines
            import outlines.models as models
            import mlx_lm
        except ImportError:
            raise RuntimeError("pip install outlines mlx-lm 필요")

        print(f"[NLParser] MLX 모델 로딩: {self.model} ...", flush=True)
        mlx_model, tokenizer = mlx_lm.load(self.model)
        outlines_model = models.from_mlxlm(mlx_model, tokenizer)
        self._generator = outlines.Generator(outlines_model, ParsedStrategy)
        print("[NLParser] 모델 로딩 완료", flush=True)

    # ── 파싱 ─────────────────────────────────────────────────────────────────

    def parse(self, user_input: str) -> ParsedStrategy:
        """자연어 입력 → ParsedStrategy"""
        if self.backend == "mlx":
            return self._parse_mlx(user_input)
        else:
            return self._parse_ollama(user_input)

    def _parse_mlx(self, user_input: str) -> ParsedStrategy:
        self._init_mlx()
        prompt = f"{SYSTEM_PROMPT}\n\n입력: \"{user_input}\"\n출력:"
        result = self._generator(prompt)
        # outlines 1.x: Generator returns JSON string, not Pydantic object
        if isinstance(result, str):
            return ParsedStrategy.model_validate_json(result)
        return result

    def _parse_ollama(self, user_input: str) -> ParsedStrategy:
        self._init_ollama()
        result = self._client.chat.completions.create(
            model=self.ollama_model,
            response_model=ParsedStrategy,
            max_retries=self.max_retries,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
        )
        return result
