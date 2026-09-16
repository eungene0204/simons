"""매매 사유의 구조화 표현(engine/trade_reason.py) 계약.

거래 내역의 매매사유는 완성 문장이 아니라 한국어 정본 템플릿 + 인자로 나른다 — /us에서
프론트 t()가 번역하려면 값이 문장에서 분리돼 있어야 한다. 여기서는 한국어 렌더 결과가
종전 문장과 같은지(표시 회귀 없음)와 인코딩 왕복을 확인한다.
"""

import os
import sys

import polars as pl

sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine import trade_reason as tr
from engine.signals import SignalEngine


def test_render_kr_substitutes_args_and_nested_segments():
    segments = [tr.part(tr.RSI_LEVEL, 30, tr.part(tr.OP_LTE))]
    assert tr.render_kr(segments) == "RSI 30 이하"


def test_money_arg_renders_with_korean_unit():
    segments = [tr.part(tr.PNL_DETAIL_LOSS, "-12.01", 1013, money=[1])]
    assert tr.render_kr(segments) == " [수익률: -12.01%, 손실: 1,013원]"


def test_encode_decode_roundtrip():
    segments = [tr.part(tr.BREAKOUT_HIGH, 252), tr.SEP_AND, tr.part(tr.VOLUME_OBV_GOLDEN_CROSS)]
    encoded = tr.encode(segments)

    assert tr.decode(encoded) == segments
    assert tr.text(encoded) == "252일 신고가 돌파 + 거래량 OBV 골든크로스"


def test_plain_string_passes_through():
    """과거 결과(구조화 이전)의 평문 사유는 그대로 문장으로 취급한다."""
    assert tr.decode("52주 신고가 돌파") is None
    assert tr.text("52주 신고가 돌파") == "52주 신고가 돌파"
    assert tr.segments_of("52주 신고가 돌파") == [tr.literal("52주 신고가 돌파")]


def test_first_template_identifies_reason_kind():
    assert tr.first_template(tr.encode([tr.part(tr.DATA_END)])) == tr.DATA_END
    composed = tr.encode([tr.PAREN_OPEN, tr.part(tr.RSI_LEVEL, 30, tr.part(tr.OP_LTE)), tr.PAREN_CLOSE])
    assert tr.first_template(composed) == tr.RSI_LEVEL


def test_condition_description_matches_legacy_korean_text():
    """조건 서술의 한국어 표기는 구조화 이전과 같아야 한다(표시 회귀 방지)."""
    engine = SignalEngine()
    cases = [
        ({"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20}}, "5일선-20일선 골든크로스"),
        ({"id": "rsi", "params": {"value": 30, "operator": "<"}}, "RSI 30 미만"),  # 엄격 비교는 경계 미포함(2026-09-17)
        ({"id": "breakout", "params": {"lookbackPeriod": 252}}, "252일 신고가 돌파"),
        ({"id": "volume_spike", "params": {}}, "거래량 OBV 골든크로스"),
        ({"id": "volatility", "params": {"period": 60, "value": 30}}, "변동성(60일, 연환산) 30% 이하"),
        ({"id": "price", "params": {"value": 100000, "operator": ">="}}, "현재가 100,000원 이상"),
        ({"id": "market_cap", "params": {"operator": ">=", "value": 5000}}, "시가총액 5000억 이상"),
        ({"id": "ai_model", "params": {"minProbability": 70, "targetThreshold": 7}},
         "AI 7% 상승 확률 70% 이상 (매수)"),
        ({"id": "price_limit_exit", "params": {"stopLoss": 10, "takeProfit": 20}},
         "현재가 10% 이하 또는 현재가 20% 이상"),
    ]
    for cond, expected in cases:
        assert engine.get_condition_description(cond) == expected, cond["id"]


def test_generate_signals_reason_is_structured_and_renders_legacy_text():
    engine = SignalEngine()
    df = pl.DataFrame({"roe_or_gpa": [12.0], "debt_ratio": [80.0]})
    group = {
        "logic": "AND",
        "conditions": [
            {"id": "roe_or_gpa", "type": "filter", "params": {"operator": ">=", "value": 10}},
            {"id": "debt_ratio", "type": "filter", "params": {"operator": "<=", "value": 100}},
        ],
    }

    _, reasons = engine.generate_signals(df, group)

    assert tr.decode(reasons[0]) is not None, "사유가 구조화되어 있어야 한다"
    assert tr.text(reasons[0]) == "ROE 10 이상 + 부채비율 100 이하"
