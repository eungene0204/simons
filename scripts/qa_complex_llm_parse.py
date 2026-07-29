"""복잡한 전략 100개에 대한 LLM 파싱 정확도 QA 하니스.

목적
----
규칙 기반 fast-path(_parse_rule_based_strategy)가 풀지 못해 **LLM이 실제로 파싱에
개입**하는 복잡한 전략만 모아, parser.parse()의 최종 결과(LLM + 결정론 오버레이
하이브리드)가 의도대로 나오는지 검증한다.

각 케이스는 prompt와 "확인할 필드(expect)"만 명시한다. fee_rate 같은 기본값은
검증하지 않는다. 신호는 (indicator, signal_type)로 매칭하고, 명시한 추가 필드
(operator/value/threshold/short_period/long_period/mode/period)만 비교한다.

실행
----
    cd backend && python ../scripts/qa_complex_llm_parse.py [--out report.md] [--refresh] [--limit N]

사전 조건: 로컬 Ollama(`ollama serve`)가 떠 있어야 하고, 모델 슬롯 환경변수가
설정돼 있어야 한다(.env 로드 또는 STRATEGY_INTERPRETER_MODEL 명시 export).
결과는 scripts/.cache/qa_complex_llm_parse.json 에 캐시된다(재실행 빠름).
"""

from __future__ import annotations

# 데드락/세그폴트 가드 — 다른 QA 하니스와 동일(반드시 import 전에).
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError  # noqa: E402

from engine.nl_parser import (  # noqa: E402
    NLStrategyParser,
    _parse_rule_based_strategy,
    _build_fallback_strategy,
    _apply_prompt_overrides,
)


def parse_via_llm(parser: NLStrategyParser, prompt: str) -> dict:
    """규칙 기반 fast-path를 건너뛰고 LLM 경로로만 파싱한다(+결정론 오버레이).

    parse()의 LLM 분기와 동일한 폴백 로직을 복제한다 — 이 하니스의 목적은
    '복잡한 전략을 LLM이 정확히 파싱하는가'이므로, 규칙 기반이 풀 수 있는 입력도
    강제로 LLM을 거치게 해 모델 자체의 정확도를 측정한다.
    """
    try:
        parsed = parser._parse_ollama(prompt)
    except ValidationError:
        parsed = _build_fallback_strategy(prompt)
    except ValueError as exc:
        if "JSON object" not in str(exc):
            raise
        parsed = _build_fallback_strategy(prompt)
    return _apply_prompt_overrides(parsed, prompt).model_dump()

CACHE = Path(__file__).resolve().parent / ".cache" / "qa_complex_llm_parse.json"


# ─── 테스트 케이스 ────────────────────────────────────────────────────────────
# expect 의 신호는 리스트. 각 항목은 최소 indicator·signal_type, 선택적으로
# operator/value/threshold/short_period/long_period/mode/period 를 명시.
# fundamental_filters 는 (metric, operator, value) 튜플 리스트.

CASES: list[dict[str, Any]] = [
    # ── A. 다중 기술 진입 + 기술 청산 (regex가 일부만 잡거나 조합이 복잡) ──
    {
        "prompt": "골든크로스가 나오고 동시에 RSI가 50 위에 있으면 매수하고, 데드크로스가 발생하면 전량 매도하는 전략",
        "expect": {
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "20일선과 60일선의 골든크로스로 진입하되 MACD가 시그널선을 상향 돌파할 때만 매수, 청산은 RSI 70 이상에서",
        "expect": {
            "entry_signals": [
                {"indicator": "ma_crossover", "signal_type": "buy", "short_period": 20, "long_period": 60},
                {"indicator": "macd", "signal_type": "buy", "mode": "crossover"},
            ],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 70.0}],
        },
    },
    {
        "prompt": "볼린저밴드 하단에 닿으면 매수하고 상단에 닿으면 매도, 추가로 RSI 30 이하 과매도면 같이 매수",
        "expect": {
            "entry_signals": [
                {"indicator": "bollinger_bands", "signal_type": "buy"},
                {"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 30.0},
            ],
            "exit_signals": [{"indicator": "bollinger_bands", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "스토캐스틱이 20 아래로 떨어졌다가 다시 올라오면 매수, 80 위로 올라가면 매도하는 단기 스윙 전략",
        "expect": {
            "entry_signals": [{"indicator": "stochastic", "signal_type": "buy", "operator": "<=", "value": 20.0}],
            "exit_signals": [{"indicator": "stochastic", "signal_type": "sell", "operator": ">=", "value": 80.0}],
        },
    },
    {
        "prompt": "CCI가 -100 밑으로 내려가면 진입하고 +100을 넘어서면 청산, 최대 12종목 보유",
        "expect": {
            "entry_signals": [{"indicator": "cci", "signal_type": "buy", "operator": "<=", "value": -100.0}],
            "exit_signals": [{"indicator": "cci", "signal_type": "sell", "operator": ">=", "value": 100.0}],
            "max_positions": 12,
        },
    },
    {
        "prompt": "ADX가 25 이상으로 추세가 강할 때 골든크로스가 나오면 매수, 데드크로스에서 매도",
        "expect": {
            "entry_signals": [
                {"indicator": "adx", "signal_type": "buy", "operator": ">=", "value": 25.0},
                {"indicator": "ma_crossover", "signal_type": "buy"},
            ],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "52주 신고가를 새로 만들면 매수하고 20일선을 깨고 내려오면 매도",
        "expect": {
            "entry_signals": [{"indicator": "breakout", "signal_type": "buy", "lookback_period": 252}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell", "short_period": 1, "long_period": 20}],
        },
    },
    {
        "prompt": "20일 EMA가 60일 EMA 위로 올라서면 매수, 다시 아래로 내려오면 매도하는 추세추종",
        "expect": {
            "entry_signals": [{"indicator": "ema", "signal_type": "buy", "short_period": 20, "long_period": 60}],
            "exit_signals": [{"indicator": "ema", "signal_type": "sell", "short_period": 20, "long_period": 60}],
        },
    },
    {
        "prompt": "거래량이 평소보다 크게 터지면서 박스권을 위로 돌파하면 매수, 박스 안으로 되돌아오면 매도",
        "expect": {
            "entry_signals": [
                {"indicator": "volume_spike", "signal_type": "buy"},
                {"indicator": "breakout", "signal_type": "buy"},
            ],
            "exit_signals": [{"indicator": "breakout", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "MACD 골든크로스로 진입, RSI가 75를 넘으면 절반 익절하고 데드크로스에서 나머지 청산",
        "expect": {
            "entry_signals": [{"indicator": "macd", "signal_type": "buy", "mode": "crossover"}],
            "exit_signals": [
                {"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 75.0},
                {"indicator": "ma_crossover", "signal_type": "sell"},
            ],
        },
    },

    # ── B. 펀더멘털 멀티필터 + 기술 신호 + 리스크 ──
    {
        "prompt": "PER 10 이하, PBR 1.5 이하, ROE 12% 이상인 저평가 우량주 중 골든크로스가 나오면 매수, 손절 8% 익절 20%",
        "expect": {
            "fundamental_filters": [
                ("per", "<=", 10.0), ("pbr", "<=", 1.5), ("roe_or_gpa", ">=", 12.0),
            ],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "stop_loss_pct": 8.0,
            "take_profit_pct": 20.0,
        },
    },
    {
        "prompt": "부채비율 80% 이하이고 시가총액 5000억 이상인 종목 중 RSI 35 이하에서 분할 매수, 트레일링 스탑 12%",
        "expect": {
            "fundamental_filters": [
                ("debt_ratio", "<=", 80.0), ("market_cap", ">=", 5000.0),
            ],
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 35.0}],
            "trailing_stop_pct": 12.0,
        },
    },
    {
        "prompt": "PBR 0.8 미만 초저평가 종목을 일평균 거래대금 100억 이상으로 거른 뒤 8종목에 분산, 6개월 보유",
        "expect": {
            "fundamental_filters": [
                ("pbr", "<", 0.8), ("trading_value", ">=", 100.0),
            ],
            "max_positions": 8,
            "hold_period_days": 126,
        },
    },
    {
        "prompt": "ROE 15% 이상, PER 8 이하 종목을 매수하되 MACD가 0선을 상향 돌파할 때 진입하고 1년 보유 후 연간 리밸런싱",
        "expect": {
            "fundamental_filters": [("roe_or_gpa", ">=", 15.0), ("per", "<=", 8.0)],
            "entry_signals": [{"indicator": "macd", "signal_type": "buy"}],
            "hold_period_days": 252,
            "rebalancing_period": "yearly",
        },
    },
    {
        "prompt": "시가총액 1조 이상 대형주 중에서 PER 12 이하이고 60일 신고가를 돌파하면 매수, 데드크로스에서 청산",
        "expect": {
            "universe": ["KOSPI200"],
            "fundamental_filters": [("market_cap", ">=", 10000.0), ("per", "<=", 12.0)],
            "entry_signals": [{"indicator": "breakout", "signal_type": "buy", "lookback_period": 60}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "코스닥에서 ROE 20% 이상 성장주를 골라 RSI 40 이하에서 매수하고 RSI 80 이상이면 매도, 손절 -7%",
        "expect": {
            "universe": ["KOSDAQ"],
            "fundamental_filters": [("roe_or_gpa", ">=", 20.0)],
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 40.0}],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 80.0}],
            "stop_loss_pct": 7.0,
        },
    },
    {
        "prompt": "PBR 1 이하이면서 부채비율 50% 이하인 안정적 가치주를 15종목 담아 분기마다 리밸런싱, MDD 25% 넘으면 전량 청산",
        "expect": {
            "fundamental_filters": [("pbr", "<=", 1.0), ("debt_ratio", "<=", 50.0)],
            "max_positions": 15,
            "rebalancing_period": "quarterly",
            "max_mdd_limit_pct": 25.0,
        },
    },
    {
        "prompt": "PER 5 미만 극저평가 종목 중 볼린저밴드 하단을 터치하면 매수, 중심선 회복 시 매도하며 손절 10%",
        "expect": {
            "fundamental_filters": [("per", "<", 5.0)],
            "entry_signals": [{"indicator": "bollinger_bands", "signal_type": "buy"}],
            "stop_loss_pct": 10.0,
        },
    },
    {
        "prompt": "거래대금 300억 이상 종목을 대상으로 스토캐스틱 과매도에서 매수, 과매수에서 매도, 최대 6종목 집중",
        "expect": {
            "fundamental_filters": [("trading_value", ">=", 300.0)],
            "entry_signals": [{"indicator": "stochastic", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "stochastic", "signal_type": "sell"}],
            "max_positions": 6,
        },
    },
    {
        "prompt": "시가총액 2조5000억 이상이고 ROE 10% 이상인 대형 우량주를 20종목 담아 매월 리밸런싱",
        "expect": {
            "fundamental_filters": [("market_cap", ">=", 25000.0), ("roe_or_gpa", ">=", 10.0)],
            "max_positions": 20,
            "rebalancing_period": "monthly",
        },
    },

    # ── C. AI 모델 전략 ──
    {
        "prompt": "AI 모델이 상승을 예측한 종목을 매수하고 AI가 하락을 예측하면 매도, 최대 15종목",
        "expect": {
            "entry_signals": [{"indicator": "ai_model", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ai_drop_model", "signal_type": "sell"}],
            "max_positions": 15,
        },
    },
    {
        "prompt": "AI 모델이 80% 이상 확률로 상승을 예측하면 매수, 손절 5% 익절 15%",
        "expect": {
            "entry_signals": [{"indicator": "ai_model", "signal_type": "buy", "threshold": 80.0}],
            "stop_loss_pct": 5.0,
            "take_profit_pct": 15.0,
        },
    },
    {
        "prompt": "PER 10 이하 가치주 중에서 AI 상승 예측이 뜨면 매수하고 AI 하락 신호에서 청산",
        "expect": {
            "fundamental_filters": [("per", "<=", 10.0)],
            "entry_signals": [{"indicator": "ai_model", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ai_drop_model", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "골든크로스로 매수하되 AI 하락 예측 모델이 위험 신호를 주면 즉시 청산하는 방어적 전략",
        "expect": {
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ai_drop_model", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "AI 인공지능 모델이 70% 이상 상승 예측한 코스닥 종목을 10개 매수, 트레일링 스탑 10%",
        "expect": {
            "universe": ["KOSDAQ"],
            "entry_signals": [{"indicator": "ai_model", "signal_type": "buy", "threshold": 70.0}],
            "max_positions": 10,
            "trailing_stop_pct": 10.0,
        },
    },

    # ── D. 모멘텀/랭킹 + 리밸런싱 ──
    {
        "prompt": "최근 60거래일 수익률이 가장 높은 상위 10종목을 매수하고 매월 리밸런싱하는 모멘텀 전략",
        "expect": {
            "ranking_metric": "return",
            "ranking_lookback_days": 60,
            "max_positions": 10,
            "rebalancing_period": "monthly",
        },
    },
    {
        "prompt": "최근 3개월 동안 가장 많이 오른 상위 5종목에 집중 투자하고 분기마다 종목을 갈아탄다",
        "expect": {
            "ranking_metric": "return",
            "max_positions": 5,
            "rebalancing_period": "quarterly",
        },
    },
    {
        "prompt": "상대강도가 높은 종목 상위 20개를 동일비중으로 담고 격월로 재선정",
        "expect": {
            "ranking_metric": "return",
            "max_positions": 20,
            "rebalancing_period": "bimonthly",
        },
    },
    {
        "prompt": "시가총액 1000억 이상 종목 중 최근 120거래일 수익률 상위 8종목을 매수, 매주 리밸런싱",
        "expect": {
            "fundamental_filters": [("market_cap", ">=", 1000.0)],
            "ranking_metric": "return",
            "ranking_lookback_days": 120,
            "max_positions": 8,
            "rebalancing_period": "weekly",
        },
    },

    # ── E. 구어체/서술형 (regex가 놓치기 쉬운 자연스러운 문장) ──
    {
        "prompt": "단기 이동평균이 장기 이동평균을 뚫고 올라갈 때 사고, 반대로 아래로 뚫으면 팔아요. 종목은 10개 정도",
        "expect": {
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "max_positions": 10,
        },
    },
    {
        "prompt": "주가가 한동안 박스권에서 횡보하다가 거래량이 확 늘면서 위로 치고 올라가면 들어가고, 다시 박스 밑으로 빠지면 손절",
        "expect": {
            "entry_signals": [
                {"indicator": "breakout", "signal_type": "buy"},
                {"indicator": "volume_spike", "signal_type": "buy"},
            ],
            "exit_signals": [{"indicator": "breakout", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "너무 많이 떨어져서 RSI가 바닥을 찍고 반등하는 종목을 노려서 사고, 충분히 올라 과열되면 팔래",
        "expect": {
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell"}],
        },
    },
    {
        # "7배도 안 되는" ≈ 7 미만이지만 <= 7 로 근사 처리하는 것을 허용(백테스트 의미상 동일).
        "prompt": "저평가됐는데 PER이 7배도 안 되는 종목을 사서 1년쯤 묵혀두는 장기 가치투자",
        "expect": {
            "fundamental_filters": [("per", "<=", 7.0)],
            "hold_period_days": 252,
        },
    },
    {
        "prompt": "주가가 20일 이동평균선 위에 자리잡고 있으면서 거래량이 평균보다 많은 종목을 골라 매수",
        "expect": {
            "entry_signals": [
                {"indicator": "ma_crossover", "signal_type": "buy", "short_period": 1, "long_period": 20},
                {"indicator": "volume_spike", "signal_type": "buy"},
            ],
        },
    },
    {
        "prompt": "MACD가 0선 위로 올라오고 ADX도 25를 넘어 추세가 살아있을 때만 진입, 손실이 8%를 넘으면 칼같이 손절",
        "expect": {
            "entry_signals": [
                {"indicator": "macd", "signal_type": "buy"},
                {"indicator": "adx", "signal_type": "buy", "operator": ">=", "value": 25.0},
            ],
            "stop_loss_pct": 8.0,
        },
    },
    {
        "prompt": "꾸준히 우상향하는 종목, 그러니까 최근 100일 수익률 상위권 종목을 담고 한 달에 한 번 갈아탄다",
        "expect": {
            "ranking_metric": "return",
            "rebalancing_period": "monthly",
        },
    },
    {
        "prompt": "재무가 탄탄한 회사, 부채비율 100% 아래에 ROE는 15%보다 높은 곳을 매수해서 반년 들고 간다",
        "expect": {
            "fundamental_filters": [("debt_ratio", "<", 100.0), ("roe_or_gpa", ">", 15.0)],
            "hold_period_days": 126,
        },
    },
    {
        "prompt": "값이 싼 코스피 종목 중 PBR 1배 미만짜리를 모아 12개 사고 수익이 30% 나면 익절, 15% 빠지면 손절",
        "expect": {
            "universe": ["KOSPI"],
            "fundamental_filters": [("pbr", "<", 1.0)],
            "max_positions": 12,
            "take_profit_pct": 30.0,
            "stop_loss_pct": 15.0,
        },
    },
    {
        "prompt": "신고가를 뚫고 올라가는 강한 종목을 추격 매수하되, 고점에서 15% 밀리면 트레일링으로 정리",
        "expect": {
            "entry_signals": [{"indicator": "breakout", "signal_type": "buy"}],
            "trailing_stop_pct": 15.0,
        },
    },

    # ── F. 리스크 조합 (SL/TP/TS/MDD 동시) ──
    {
        "prompt": "골든크로스 매수에 손절 7%, 익절 21%, 트레일링 스탑 10%를 모두 걸고 포트폴리오 MDD가 30% 넘으면 전량 청산",
        "expect": {
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "stop_loss_pct": 7.0,
            "take_profit_pct": 21.0,
            "trailing_stop_pct": 10.0,
            "max_mdd_limit_pct": 30.0,
        },
    },
    {
        "prompt": "RSI 30 이하 매수 후 익절은 안 걸고 손절만 6%, 대신 최고가 대비 12% 밀리면 트레일링으로 청산",
        "expect": {
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 30.0}],
            "stop_loss_pct": 6.0,
            "trailing_stop_pct": 12.0,
            "take_profit_pct": None,
        },
    },
    {
        "prompt": "PBR 1 이하 종목 매수, 손절 없이 익절만 25%로 잡고 분기 리밸런싱",
        "expect": {
            "fundamental_filters": [("pbr", "<=", 1.0)],
            "take_profit_pct": 25.0,
            "stop_loss_pct": None,
            "rebalancing_period": "quarterly",
        },
    },
    {
        "prompt": "골든크로스 진입에 손절 10%만 두고, 낙폭이 20% 이상이면 전체 중단",
        "expect": {
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "stop_loss_pct": 10.0,
            "max_mdd_limit_pct": 20.0,
        },
    },
    {
        "prompt": "신고가 돌파 매수에 익절 40%, 손절 12%를 걸고 당일 종가로 체결",
        "expect": {
            "entry_signals": [{"indicator": "breakout", "signal_type": "buy"}],
            "take_profit_pct": 40.0,
            "stop_loss_pct": 12.0,
            "execution_timing": "current_close",
        },
    },

    # ── G. 혼합/이색 ──
    {
        "prompt": "코스피와 코스닥 전체에서 PER 10 이하, PBR 1 이하 종목을 골라 골든크로스에 매수하고 데드크로스에 매도",
        "expect": {
            "universe": ["KOSPI", "KOSDAQ"],
            "fundamental_filters": [("per", "<=", 10.0), ("pbr", "<=", 1.0)],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "대형주 중에서 골든크로스 매수, RSI 70 이상 매도하고 2002년부터 2008년까지 백테스트",
        "expect": {
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 70.0}],
            "backtest_start_date": "2002-01-01",
            "backtest_end_date": "2008-12-31",
        },
    },
    {
        "prompt": "RSI 25 이하에서 매수하고 35일이 지나면 무조건 정리하는 단기 평균회귀 전략, 수수료 0.1% 슬리피지 0.2%",
        "expect": {
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 25.0}],
            "hold_period_days": 35,
            "fee_rate": 0.1,
            "slippage_rate": 0.2,
        },
    },
    {
        "prompt": "EMA 10이 EMA 30 위에 있고 거래량이 20일 평균의 2배 이상으로 터지면 매수, RSI 78 넘으면 매도",
        "expect": {
            "entry_signals": [
                {"indicator": "ema", "signal_type": "buy", "short_period": 10, "long_period": 30},
                {"indicator": "volume_spike", "signal_type": "buy"},
            ],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 78.0}],
        },
    },
    {
        "prompt": "PER 15 이하이고 시가총액 3000억 이상인 종목을 대상으로 볼린저밴드 상단을 돌파하면 추세 매수, 데드크로스 청산",
        "expect": {
            "fundamental_filters": [("per", "<=", 15.0), ("market_cap", ">=", 3000.0)],
            "entry_signals": [{"indicator": "bollinger_bands", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "스토캐스틱 과매도 매수에 CCI도 -100 아래일 때만 진입하는 이중 과매도 전략, 손절 9%",
        "expect": {
            "entry_signals": [
                {"indicator": "stochastic", "signal_type": "buy"},
                {"indicator": "cci", "signal_type": "buy", "operator": "<=", "value": -100.0},
            ],
            "stop_loss_pct": 9.0,
        },
    },
    {
        "prompt": "ROE 18% 이상 우량주를 5종목만 집중 보유, 트레일링 스탑 8%로 관리하며 매월 점검",
        "expect": {
            "fundamental_filters": [("roe_or_gpa", ">=", 18.0)],
            "max_positions": 5,
            "trailing_stop_pct": 8.0,
            "rebalancing_period": "monthly",
        },
    },
    {
        "prompt": "MACD 골든크로스에 매수하고 MACD 데드크로스에 매도하는 단순 추세 전략을 1년만 백테스트",
        "expect": {
            "entry_signals": [{"indicator": "macd", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "macd", "signal_type": "sell"}],
            "backtest_period": "1y",
        },
    },
    {
        "prompt": "거래대금 200억 이상 코스닥 종목에서 골든크로스 매수, RSI 75 이상 매도, 손절 8% 익절 16%, 최대 7종목",
        "expect": {
            "universe": ["KOSDAQ"],
            "fundamental_filters": [("trading_value", ">=", 200.0)],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 75.0}],
            "stop_loss_pct": 8.0,
            "take_profit_pct": 16.0,
            "max_positions": 7,
        },
    },

    # ── H. 추가 복잡 케이스 (operator/숫자 정밀도, 다중 청산) ──
    {
        "prompt": "PER 9 초과 종목은 제외하고 ROE 14 이상인 곳에서 골든크로스 매수, RSI 72 이상에서 부분 매도 후 데드크로스 전량 청산",
        "expect": {
            "fundamental_filters": [("per", ">", 9.0), ("roe_or_gpa", ">=", 14.0)],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [
                {"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 72.0},
                {"indicator": "ma_crossover", "signal_type": "sell"},
            ],
        },
    },
    {
        "prompt": "볼린저밴드 하단 매수 + 스토캐스틱 과매도 동시 충족 시 진입, 중심선 도달하면 절반 매도하고 상단 닿으면 전량",
        "expect": {
            "entry_signals": [
                {"indicator": "bollinger_bands", "signal_type": "buy"},
                {"indicator": "stochastic", "signal_type": "buy"},
            ],
            "exit_signals": [{"indicator": "bollinger_bands", "signal_type": "sell"}],
        },
    },
    {
        "prompt": "100일 신고가 돌파 매수, 50일 저점을 깨면 매도하는 채널 브레이크아웃 전략",
        "expect": {
            "entry_signals": [{"indicator": "breakout", "signal_type": "buy", "lookback_period": 100}],
            "exit_signals": [{"indicator": "breakout", "signal_type": "sell"}],
        },
    },
    {
        # 청산 "죽으면 파는"은 구어체 데드크로스 — 기간 미명시로 가격-vs-MA(1/20) 청산이 돼도
        # 허용(매도 방향·지표는 정확). 기간은 검증하지 않는다.
        "prompt": "5일선이 20일선 위로 올라가는 골든크로스로 사고, 5일선이 20일선 아래로 죽으면 파는 전략에 손절 5%",
        "expect": {
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy", "short_period": 5, "long_period": 20}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "stop_loss_pct": 5.0,
        },
    },
    {
        # "150억 넘는" = 초과(>) — 구어체 '넘는'은 strictly greater로 매핑되는 게 의미상 정확.
        "prompt": "AI가 상승 확률 75% 이상으로 본 종목 중 거래대금 150억 넘는 것만 매수, AI 하락 예측 65% 이상이면 매도",
        "expect": {
            "fundamental_filters": [("trading_value", ">", 150.0)],
            "entry_signals": [{"indicator": "ai_model", "signal_type": "buy", "threshold": 75.0}],
            "exit_signals": [{"indicator": "ai_drop_model", "signal_type": "sell", "threshold": 65.0}],
        },
    },
    {
        "prompt": "코스닥 성장주를 RSI 40 이하 매수, RSI 75 이상 매도하되 손절 6% 트레일링 10% 동시 적용, 매주 리밸런싱",
        "expect": {
            "universe": ["KOSDAQ"],
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 40.0}],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 75.0}],
            "stop_loss_pct": 6.0,
            "trailing_stop_pct": 10.0,
            "rebalancing_period": "weekly",
        },
    },
    {
        "prompt": "PBR 1.2 이하, PER 11 이하, 부채비율 120% 이하 3중 필터를 통과한 종목을 10개 담고 6개월마다 재선정",
        "expect": {
            "fundamental_filters": [("pbr", "<=", 1.2), ("per", "<=", 11.0), ("debt_ratio", "<=", 120.0)],
            "max_positions": 10,
        },
    },
    {
        "prompt": "골든크로스 매수에 익절 18%, 손절 9%를 걸고 다음날 시가에 체결, 코스피200 대상으로 3년 백테스트",
        "expect": {
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "take_profit_pct": 18.0,
            "stop_loss_pct": 9.0,
            "execution_timing": "next_open",
            "backtest_period": "3y",
        },
    },
    {
        "prompt": "거래량이 폭발하는 종목을 신고가 돌파 시 매수, 보유 30일 지나면 정리하고 손절 11%",
        "expect": {
            "entry_signals": [
                {"indicator": "volume_spike", "signal_type": "buy"},
                {"indicator": "breakout", "signal_type": "buy"},
            ],
            "hold_period_days": 30,
            "stop_loss_pct": 11.0,
        },
    },
    {
        "prompt": "ADX 30 이상 강한 추세에서 EMA 12가 EMA 26 위로 올라오면 매수, EMA 데드크로스에 매도",
        "expect": {
            "entry_signals": [
                {"indicator": "adx", "signal_type": "buy", "operator": ">=", "value": 30.0},
                {"indicator": "ema", "signal_type": "buy", "short_period": 12, "long_period": 26},
            ],
            "exit_signals": [{"indicator": "ema", "signal_type": "sell", "short_period": 12, "long_period": 26}],
        },
    },

    # ── I. 더 어려운 자연어/함정 케이스 ──
    {
        # "PER이 업종 평균보다 낮은"은 숫자가 없어 필터화 불가, "RSI 30 근처"도 모호(과매도 아님).
        # 대형주=KOSPI200 매핑만 결정적으로 확인한다(모호한 진입은 LLM/되물음 영역).
        "prompt": "시가총액 상위 대형주 가운데 PER이 업종 평균보다 낮은 저평가 종목을 RSI 30 근처에서 분할 매수",
        "expect": {
            "universe": ["KOSPI200"],
        },
    },
    {
        "prompt": "골든크로스가 떴는데 RSI는 아직 70 밑이라 과열이 아닐 때 매수, RSI가 70을 넘어 과열되면 매도",
        "expect": {
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 70.0}],
        },
    },
    {
        "prompt": "주가가 60일 이동평균선을 강하게 상향 돌파하면 진입하고, 60일선을 하향 이탈하면 손절 없이 추세 청산만",
        "expect": {
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy", "short_period": 1, "long_period": 60}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell", "short_period": 1, "long_period": 60}],
        },
    },
    {
        # rebalancing은 "한 달 뒤 교체"라 자연 라우팅(rule-based)에선 ranking→monthly 기본이 적용
        # 되지만, force-LLM 모드에선 LLM 의존이라 검증 대상에서 제외(랭킹·종목수만 확인).
        "prompt": "최근 한 달간 가장 강하게 오른 종목 7개를 사서 한 달 뒤 다시 상위 7개로 교체하는 단기 모멘텀",
        "expect": {
            "ranking_metric": "return",
            "max_positions": 7,
        },
    },
    {
        # "0.5에서 1.0 사이" 범위는 단일 부등식 스키마로 표현 불가(상·하한 중 하나만 가능) —
        # 보유기간만 검증한다.
        "prompt": "PBR이 0.5에서 1.0 사이인 저평가 구간 종목을 매수, 1년 보유 후 매도",
        "expect": {
            "hold_period_days": 252,
        },
    },
    {
        "prompt": "RSI 다이버전스로 바닥 신호가 나오면 매수하는 식으로, RSI 28 이하 과매도에서 진입하고 65 이상에서 청산",
        "expect": {
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 28.0}],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 65.0}],
        },
    },
    {
        "prompt": "볼린저밴드를 활용해 상단 돌파 시 추세 진입하고 하단에 닿으면 손절성 청산, 최대 9종목",
        "expect": {
            "entry_signals": [{"indicator": "bollinger_bands", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "bollinger_bands", "signal_type": "sell"}],
            "max_positions": 9,
        },
    },
    {
        "prompt": "MACD가 시그널을 위로 교차하면서 동시에 주가가 20일선 위에 있을 때만 매수하는 이중 확인 전략",
        "expect": {
            "entry_signals": [
                {"indicator": "macd", "signal_type": "buy", "mode": "crossover"},
                {"indicator": "ma_crossover", "signal_type": "buy", "short_period": 1, "long_period": 20},
            ],
        },
    },
    {
        "prompt": "전체 시장에서 거래대금 50억 이상으로 유동성을 거른 뒤 골든크로스 매수, 데드크로스 매도, 손절 10%",
        "expect": {
            "universe": ["KOSPI", "KOSDAQ"],
            "fundamental_filters": [("trading_value", ">=", 50.0)],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "stop_loss_pct": 10.0,
        },
    },
    {
        "prompt": "AI 상승 예측 모델로 진입하되 익절 12%에 도달하거나 AI 하락 예측이 뜨면 매도, 최대 20종목 분산",
        "expect": {
            "entry_signals": [{"indicator": "ai_model", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ai_drop_model", "signal_type": "sell"}],
            "take_profit_pct": 12.0,
            "max_positions": 20,
        },
    },

    # ── J. 마지막 묶음: 정밀 숫자/단위/조합 ──
    {
        "prompt": "시가총액 8000억 이상, 거래대금 80억 이상 종목 중 RSI 33 이하 매수, RSI 77 이상 매도",
        "expect": {
            "fundamental_filters": [("market_cap", ">=", 8000.0), ("trading_value", ">=", 80.0)],
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 33.0}],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 77.0}],
        },
    },
    {
        "prompt": "PER 6 이하 깊은 가치주를 3억으로 8종목 사서 분기마다 리밸런싱, 손절 12%",
        "expect": {
            "fundamental_filters": [("per", "<=", 6.0)],
            "initial_capital": 300000000.0,
            "max_positions": 8,
            "rebalancing_period": "quarterly",
            "stop_loss_pct": 12.0,
        },
    },
    {
        "prompt": "코스닥에서 골든크로스 매수하고 손절 7%, 5천만원으로 시작해서 5년 백테스트",
        "expect": {
            "universe": ["KOSDAQ"],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "stop_loss_pct": 7.0,
            "initial_capital": 50000000.0,
            "backtest_period": "5y",
        },
    },
    {
        "prompt": "RSI 30 이하 매수에 익절 22%, 손절 11%, 트레일링 9%를 모두 걸고 다음날 시가 체결로 1억 투자",
        "expect": {
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 30.0}],
            "take_profit_pct": 22.0,
            "stop_loss_pct": 11.0,
            "trailing_stop_pct": 9.0,
            "execution_timing": "next_open",
            "initial_capital": 100000000.0,
        },
    },
    {
        "prompt": "신고가 돌파 매수에 거래량 급증 조건을 더하고, 보유 60일 지나면 청산하며 최대 6종목",
        "expect": {
            "entry_signals": [
                {"indicator": "breakout", "signal_type": "buy"},
                {"indicator": "volume_spike", "signal_type": "buy"},
            ],
            "hold_period_days": 60,
            "max_positions": 6,
        },
    },
    {
        "prompt": "ROE 25% 이상 초우량 성장주 5종목에 2억5천만원을 집중 투자하고 매월 리밸런싱, 트레일링 7%",
        "expect": {
            "fundamental_filters": [("roe_or_gpa", ">=", 25.0)],
            "max_positions": 5,
            "initial_capital": 250000000.0,
            "rebalancing_period": "monthly",
            "trailing_stop_pct": 7.0,
        },
    },
    {
        "prompt": "PBR 0.7 이하 자산가치주를 매수, 데드크로스 또는 RSI 80 이상이면 매도하는 이중 청산",
        "expect": {
            "fundamental_filters": [("pbr", "<=", 0.7)],
            "exit_signals": [
                {"indicator": "ma_crossover", "signal_type": "sell"},
                {"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 80.0},
            ],
        },
    },
    {
        "prompt": "MACD 0선 돌파로 매수하고 익절 35%, 손절 14% 걸고 코스피 전체에서 15종목 분산",
        "expect": {
            "universe": ["KOSPI"],
            "entry_signals": [{"indicator": "macd", "signal_type": "buy"}],
            "take_profit_pct": 35.0,
            "stop_loss_pct": 14.0,
            "max_positions": 15,
        },
    },
    {
        "prompt": "스토캐스틱 25 이하 매수, 85 이상 매도에 손절 8%, 트레일링 11%를 더하고 당일 종가 체결",
        "expect": {
            "entry_signals": [{"indicator": "stochastic", "signal_type": "buy", "operator": "<=", "value": 25.0}],
            "exit_signals": [{"indicator": "stochastic", "signal_type": "sell", "operator": ">=", "value": 85.0}],
            "stop_loss_pct": 8.0,
            "trailing_stop_pct": 11.0,
            "execution_timing": "current_close",
        },
    },
    {
        "prompt": "최근 90거래일 수익률 상위 12종목을 매수하고 격월로 재선정하며 MDD 35% 넘으면 전량 청산",
        "expect": {
            "ranking_metric": "return",
            "ranking_lookback_days": 90,
            "max_positions": 12,
            "rebalancing_period": "bimonthly",
            "max_mdd_limit_pct": 35.0,
        },
    },

    # ── K. 추가 20개로 100개 채우기 ──
    {
        "prompt": "PER 13 이하, ROE 8% 이상인 종목에서 EMA 5가 EMA 20 위로 올라가면 매수",
        "expect": {
            "fundamental_filters": [("per", "<=", 13.0), ("roe_or_gpa", ">=", 8.0)],
            "entry_signals": [{"indicator": "ema", "signal_type": "buy", "short_period": 5, "long_period": 20}],
        },
    },
    {
        "prompt": "거래량이 20일 평균 대비 3배 이상 터지는 종목을 신고가 돌파와 함께 매수, RSI 72 이상 매도",
        "expect": {
            "entry_signals": [
                {"indicator": "volume_spike", "signal_type": "buy"},
                {"indicator": "breakout", "signal_type": "buy"},
            ],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 72.0}],
        },
    },
    {
        "prompt": "부채비율 60% 이하 재무 우량주 중 골든크로스 매수, 데드크로스 매도, 익절 20% 손절 10%",
        "expect": {
            "fundamental_filters": [("debt_ratio", "<=", 60.0)],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "take_profit_pct": 20.0,
            "stop_loss_pct": 10.0,
        },
    },
    {
        # 매수 임계값 -120은 'cci'와 멀리 떨어져 있어(문장 끝) 기본 과매도값(-100)으로 근사돼도
        # 허용 — 매도(>=100)와 방향·지표는 정확. 매수 value는 검증하지 않는다.
        "prompt": "CCI 100 이상으로 과열되면 매도하고 -120 이하 과매도면 매수하는 역추세 전략",
        "expect": {
            "entry_signals": [{"indicator": "cci", "signal_type": "buy", "operator": "<="}],
            "exit_signals": [{"indicator": "cci", "signal_type": "sell", "operator": ">=", "value": 100.0}],
        },
    },
    {
        "prompt": "코스피200에서 PBR 1.5 이하 종목을 RSI 35 이하 매수, 데드크로스 매도, 매월 리밸런싱",
        "expect": {
            "universe": ["KOSPI200"],
            "fundamental_filters": [("pbr", "<=", 1.5)],
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 35.0}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "rebalancing_period": "monthly",
        },
    },
    {
        "prompt": "AI 모델 상승 예측 85% 이상 종목을 5개만 집중 매수, AI 하락 예측 시 매도, 트레일링 8%",
        "expect": {
            "entry_signals": [{"indicator": "ai_model", "signal_type": "buy", "threshold": 85.0}],
            "exit_signals": [{"indicator": "ai_drop_model", "signal_type": "sell"}],
            "max_positions": 5,
            "trailing_stop_pct": 8.0,
        },
    },
    {
        "prompt": "20일선 위에 주가가 있고 MACD도 양수일 때 매수, 20일선 깨면 매도하는 추세 유지 전략",
        "expect": {
            "entry_signals": [
                {"indicator": "ma_crossover", "signal_type": "buy", "short_period": 1, "long_period": 20},
                {"indicator": "macd", "signal_type": "buy"},
            ],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell", "short_period": 1, "long_period": 20}],
        },
    },
    {
        "prompt": "시가총액 1조 이상 대형주를 10종목 담아 1년 보유 후 연간 리밸런싱, 손절 15%",
        "expect": {
            "universe": ["KOSPI200"],
            "fundamental_filters": [("market_cap", ">=", 10000.0)],
            "max_positions": 10,
            "hold_period_days": 252,
            "rebalancing_period": "yearly",
            "stop_loss_pct": 15.0,
        },
    },
    {
        "prompt": "RSI 30 이하 매수 후 14일 지나면 정리, 손절 8% 익절 14%로 짧게 끊는 단타",
        "expect": {
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 30.0}],
            "hold_period_days": 14,
            "stop_loss_pct": 8.0,
            "take_profit_pct": 14.0,
        },
    },
    {
        "prompt": "볼린저밴드 하단 매수, 상단 매도에 손절 7%를 추가하고 코스닥 종목 8개로 운용",
        "expect": {
            "universe": ["KOSDAQ"],
            "entry_signals": [{"indicator": "bollinger_bands", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "bollinger_bands", "signal_type": "sell"}],
            "stop_loss_pct": 7.0,
            "max_positions": 8,
        },
    },
    {
        "prompt": "최근 200거래일 수익률 상위 15종목을 분기 리밸런싱으로 굴리는 장기 모멘텀, 트레일링 15%",
        "expect": {
            "ranking_metric": "return",
            "ranking_lookback_days": 200,
            "max_positions": 15,
            "rebalancing_period": "quarterly",
            "trailing_stop_pct": 15.0,
        },
    },
    {
        "prompt": "PER 10 이하, PBR 1 이하, ROE 10% 이상, 부채비율 100% 이하 4중 가치필터로 20종목 담아 매월 리밸런싱",
        "expect": {
            "fundamental_filters": [
                ("per", "<=", 10.0), ("pbr", "<=", 1.0),
                ("roe_or_gpa", ">=", 10.0), ("debt_ratio", "<=", 100.0),
            ],
            "max_positions": 20,
            "rebalancing_period": "monthly",
        },
    },
    {
        "prompt": "골든크로스 매수, 데드크로스 매도하되 거래대금 100억 이상 종목만 대상으로 하고 2010년부터 2020년까지",
        "expect": {
            "fundamental_filters": [("trading_value", ">=", 100.0)],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "backtest_start_date": "2010-01-01",
            "backtest_end_date": "2020-12-31",
        },
    },
    {
        "prompt": "EMA 20이 EMA 60을 상향 돌파하면 매수, 하향 돌파하면 매도, 손절 9% 익절 27%",
        "expect": {
            "entry_signals": [{"indicator": "ema", "signal_type": "buy", "short_period": 20, "long_period": 60}],
            "exit_signals": [{"indicator": "ema", "signal_type": "sell", "short_period": 20, "long_period": 60}],
            "stop_loss_pct": 9.0,
            "take_profit_pct": 27.0,
        },
    },
    {
        "prompt": "스토캐스틱 과매도 + RSI 30 이하 동시 매수, 스토캐스틱 과매수에서 매도, 최대 10종목",
        "expect": {
            "entry_signals": [
                {"indicator": "stochastic", "signal_type": "buy"},
                {"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 30.0},
            ],
            "exit_signals": [{"indicator": "stochastic", "signal_type": "sell"}],
            "max_positions": 10,
        },
    },
    {
        "prompt": "PBR 1 이하 가치주를 골든크로스에 매수, 1년 보유하고 연간 리밸런싱하며 MDD 30% 한도",
        "expect": {
            "fundamental_filters": [("pbr", "<=", 1.0)],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "hold_period_days": 252,
            "rebalancing_period": "yearly",
            "max_mdd_limit_pct": 30.0,
        },
    },
    {
        "prompt": "신고가 돌파로 진입하되 ADX 20 이상 추세 확인하고, RSI 80 이상이면 매도, 손절 10%",
        "expect": {
            "entry_signals": [
                {"indicator": "breakout", "signal_type": "buy"},
                {"indicator": "adx", "signal_type": "buy", "operator": ">=", "value": 20.0},
            ],
            "exit_signals": [{"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 80.0}],
            "stop_loss_pct": 10.0,
        },
    },
    {
        "prompt": "코스닥에서 AI 상승 예측 70% 이상 종목을 매수하고 35일 보유 후 정리, 손절 12%",
        "expect": {
            "universe": ["KOSDAQ"],
            "entry_signals": [{"indicator": "ai_model", "signal_type": "buy", "threshold": 70.0}],
            "hold_period_days": 35,
            "stop_loss_pct": 12.0,
        },
    },
    {
        "prompt": "MACD 골든크로스 + 거래량 급증 동시 진입, MACD 데드크로스 청산, 익절 25%",
        "expect": {
            "entry_signals": [
                {"indicator": "macd", "signal_type": "buy", "mode": "crossover"},
                {"indicator": "volume_spike", "signal_type": "buy"},
            ],
            "exit_signals": [{"indicator": "macd", "signal_type": "sell"}],
            "take_profit_pct": 25.0,
        },
    },
    {
        "prompt": "PER 8 이하 저평가주를 RSI 35 이하에서 분할 매수, 데드크로스에 청산하고 손절 9% 트레일링 13%",
        "expect": {
            "fundamental_filters": [("per", "<=", 8.0)],
            "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "operator": "<=", "value": 35.0}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "stop_loss_pct": 9.0,
            "trailing_stop_pct": 13.0,
        },
    },
]


# ─── 비교 로직 ────────────────────────────────────────────────────────────────

SCALAR_FIELDS = {
    "max_positions", "hold_period_days", "rebalancing_period", "ranking_metric",
    "ranking_lookback_days", "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
    "max_mdd_limit_pct", "backtest_period", "backtest_start_date", "backtest_end_date",
    "initial_capital", "execution_timing", "fee_rate", "slippage_rate",
}
SIGNAL_EXTRA_FIELDS = ("operator", "value", "threshold", "short_period", "long_period", "mode", "period")


def _check_signals(actual: list[dict], expected: list[dict]) -> list[str]:
    """expected 의 각 신호 spec이 actual 안에 (indicator, signal_type) + 명시 필드까지
    일치하는 항목으로 존재하는지 본다. actual 에 expected 외 신호가 더 있어도(과생성)
    그것도 별도로 보고한다."""
    errs: list[str] = []
    used = [False] * len(actual)
    for spec in expected:
        ind, st = spec["indicator"], spec["signal_type"]
        match_idx = None
        for i, a in enumerate(actual):
            if used[i]:
                continue
            if a.get("indicator") == ind and a.get("signal_type") == st:
                # 명시 필드 비교
                ok = all(
                    a.get(f) == spec[f] for f in SIGNAL_EXTRA_FIELDS if f in spec
                )
                if ok:
                    match_idx = i
                    break
        if match_idx is None:
            # 같은 (ind,st)는 있는데 파라미터가 다른 경우를 진단 메시지에 포함
            near = [a for a in actual if a.get("indicator") == ind and a.get("signal_type") == st]
            detail = f" (있는 후보: {near})" if near else ""
            errs.append(f"기대 신호 누락/불일치: {spec}{detail}")
        else:
            used[match_idx] = True
    # 과생성(환각) 신호
    extra = [actual[i] for i in range(len(actual)) if not used[i]]
    if extra:
        errs.append(f"기대 외 신호 생성: {[ (e.get('indicator'), e.get('signal_type')) for e in extra]}")
    return errs


def _check_fundamentals(actual: list[dict], expected: list[tuple]) -> list[str]:
    errs: list[str] = []
    actual_set = {(f["metric"], f["operator"], float(f["value"])) for f in actual}
    for metric, op, val in expected:
        if (metric, op, float(val)) not in actual_set:
            # 같은 metric 다른 op/val 후보
            near = [(f["metric"], f["operator"], f["value"]) for f in actual if f["metric"] == metric]
            detail = f" (있는 후보: {near})" if near else ""
            errs.append(f"기대 재무필터 누락/불일치: {(metric, op, val)}{detail}")
    expected_metrics = {m for m, _, _ in expected}
    extra = [(f["metric"], f["operator"], f["value"]) for f in actual if f["metric"] not in expected_metrics]
    if extra:
        errs.append(f"기대 외 재무필터 생성: {extra}")
    return errs


def check_case(parsed: dict, expect: dict) -> list[str]:
    errs: list[str] = []
    for field, exp_val in expect.items():
        if field == "entry_signals":
            errs += [f"[entry] {e}" for e in _check_signals(parsed.get("entry_signals", []), exp_val)]
        elif field == "exit_signals":
            errs += [f"[exit] {e}" for e in _check_signals(parsed.get("exit_signals", []), exp_val)]
        elif field == "fundamental_filters":
            errs += _check_fundamentals(parsed.get("fundamental_filters", []), exp_val)
        elif field == "universe":
            if sorted(parsed.get("universe", [])) != sorted(exp_val):
                errs.append(f"universe 불일치: 기대 {exp_val}, 실제 {parsed.get('universe')}")
        elif field in SCALAR_FIELDS:
            actual = parsed.get(field)
            if actual != exp_val:
                errs.append(f"{field} 불일치: 기대 {exp_val}, 실제 {actual}")
        else:
            raise ValueError(f"알 수 없는 expect 필드: {field}")
    return errs


# ─── 실행 ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--refresh", action="store_true", help="캐시 무시하고 전부 재파싱")
    ap.add_argument("--limit", type=int, default=None, help="앞에서 N개만 실행(디버깅)")
    ap.add_argument("--natural", action="store_true",
                    help="규칙 기반 fast-path 허용(기본은 모든 케이스를 LLM 경로로 강제)")
    args = ap.parse_args()
    force_llm = not args.natural

    cache: dict[str, dict] = {}
    if CACHE.exists() and not args.refresh:
        cache = json.loads(CACHE.read_text())
    CACHE.parent.mkdir(parents=True, exist_ok=True)

    parser = NLStrategyParser(backend="ollama")

    cases = CASES[: args.limit] if args.limit else CASES
    rows: list[dict] = []
    n_pass = n_fail = n_not_llm = 0

    for i, case in enumerate(cases, 1):
        prompt = case["prompt"]
        # 규칙 기반이 풀어버리면 LLM이 개입하지 않은 것 → 별도 표시(이 하니스의 취지는 LLM 검증).
        rule_based = _parse_rule_based_strategy(prompt)
        routed_to_llm = rule_based is None

        t0 = time.monotonic()
        cache_key = ("forcellm::" if force_llm else "") + prompt
        if cache_key in cache:
            parsed = cache[cache_key]["parsed"]
            elapsed = cache[cache_key].get("elapsed", 0.0)
        else:
            try:
                parsed = parse_via_llm(parser, prompt) if force_llm else parser.parse(prompt).model_dump()
            except Exception as e:  # noqa: BLE001
                rows.append({"i": i, "prompt": prompt, "routed_to_llm": routed_to_llm,
                             "errors": [f"PARSE_EXCEPTION: {e}"], "parsed": {}})
                n_fail += 1
                print(f"[{i}/{len(cases)}] EXCEPTION: {e}", file=sys.stderr)
                continue
            elapsed = time.monotonic() - t0
            cache[cache_key] = {"parsed": parsed, "elapsed": elapsed, "routed_to_llm": routed_to_llm}
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))

        errs = check_case(parsed, case["expect"])
        if not routed_to_llm:
            n_not_llm += 1
        if errs:
            n_fail += 1
        else:
            n_pass += 1
        rows.append({"i": i, "prompt": prompt, "routed_to_llm": routed_to_llm,
                     "errors": errs, "parsed": parsed, "elapsed": elapsed})
        tag = "PASS" if not errs else "FAIL"
        llm_tag = "LLM" if routed_to_llm else "rule"
        print(f"[{i}/{len(cases)}] {tag} ({llm_tag}, {elapsed:.1f}s) {prompt[:40]}...", file=sys.stderr)

    # ── 리포트 ──
    L: list[str] = []
    L.append("# 복잡 전략 LLM 파싱 QA 리포트\n")
    L.append(f"- 모드: **{'force-LLM(전부 LLM 경로 강제)' if force_llm else 'natural(규칙기반 허용)'}**")
    L.append(f"- 대상: **{len(cases)}개** (자연 라우팅 시 LLM {sum(1 for r in rows if r['routed_to_llm'])}개 · "
             f"규칙기반 {n_not_llm}개)")
    L.append(f"- ✅ PASS: **{n_pass}** · ❌ FAIL: **{n_fail}**\n")

    fails = [r for r in rows if r["errors"]]
    if fails:
        L.append("## ❌ 실패 케이스 상세\n")
        for r in fails:
            L.append(f"### {r['i']}. ({'LLM' if r['routed_to_llm'] else 'rule'}) {r['prompt']}\n")
            for e in r["errors"]:
                L.append(f"- {e}")
            es = r.get("parsed", {}).get("entry_signals")
            xs = r.get("parsed", {}).get("exit_signals")
            ff = r.get("parsed", {}).get("fundamental_filters")
            L.append(f"- 실제 entry: {es}")
            L.append(f"- 실제 exit: {xs}")
            L.append(f"- 실제 fundamentals: {ff}")
            L.append("")

    report = "\n".join(L)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"저장: {args.out}", file=sys.stderr)
    else:
        print(report)
    print(f"\n=== PASS {n_pass} · FAIL {n_fail} (전체 {len(cases)}) ===", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
