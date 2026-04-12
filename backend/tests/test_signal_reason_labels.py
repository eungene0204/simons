import os
import sys

import polars as pl

sys.path.append(os.path.join(os.getcwd(), "backend"))

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

    assert reasons[0] == "ROE 10 이상 + 부채비율 100 이하"
    assert "GPA" not in reasons[0]
