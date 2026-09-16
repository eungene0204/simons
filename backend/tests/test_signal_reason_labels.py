import os
import sys

import polars as pl

sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine import trade_reason
from engine.signals import SignalEngine


def test_get_condition_description_uses_roe_label_only():
    engine = SignalEngine()

    desc = engine.get_condition_description(
        {"id": "roe_or_gpa", "params": {"operator": ">=", "value": 10}}
    )

    assert desc == "ROE 10 이상"
    assert "GPA" not in desc


def test_generate_signals_reason_does_not_include_gpa_for_roe_filter():
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

    # 사유는 구조화되어 나른다(engine/trade_reason.py) — 표시 문장은 렌더 결과로 본다.
    rendered = trade_reason.text(reasons[0])
    assert rendered == "ROE 10 이상 + 부채비율 100 이하"
    assert "GPA" not in rendered


def test_strict_operators_are_not_labelled_inclusive():
    # [회귀 2026-09-17] PER > 0 전략의 매매 사유가 "PER 0 이상"으로 찍혔다 — 엔진은 엄격 비교(>)로
    # 평가하는데 사유 낱말은 >, >=를 모두 '이상'으로 적었다. 경계 포함 여부가 표시와 어긋나면 안 된다.
    engine = SignalEngine()
    describe = lambda op: engine.get_condition_description(  # noqa: E731
        {"id": "per", "params": {"operator": op, "value": 0}})

    assert describe(">") == "PER 0 초과"
    assert describe(">=") == "PER 0 이상"
    assert describe("<") == "PER 0 미만"
    assert describe("<=") == "PER 0 이하"
