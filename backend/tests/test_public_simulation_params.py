import copy

import pytest

from public_simulation.params import OverrideError, apply_overrides, build_editable_params

SNAPSHOT = {
    "universe_id": "kospi200",
    "entry": {"conditions": [
        {"type": "indicator", "id": "rsi", "params": {"signalType": "buy", "period": 14, "operator": "<", "value": 30}},
        {"type": "indicator", "id": "ma_crossover", "params": {"signalType": "buy", "shortMA": 5, "longMA": 20}},
        {"type": "filter", "id": "per", "params": {"operator": "<=", "value": 5}},
    ]},
    "exit": {"conditions": [
        {"type": "indicator", "id": "ema", "params": {"signalType": "sell", "shortPeriod": 12, "longPeriod": 26}},
        {"type": "indicator", "id": "breakout", "params": {"signalType": "sell", "lookbackPeriod": 20}},
        {"type": "indicator", "id": "bollinger_bands",
         "params": {"band": "lower", "cross": "above", "period": 20, "touchLookback": 3}},
        {"type": "indicator", "id": "candle_pattern", "params": {"signalType": "buy", "pattern": "doji"}},
        {"type": "indicator", "id": "not_in_registry", "params": {"period": 9}},
    ]},
    "risk": {"position_size_pct": 10, "stop_loss_pct": 10, "init_cash": 10_000_000},
}


def by_path():
    return {d["path"]: d for d in build_editable_params(SNAPSHOT)}


def test_descriptors_come_from_registry_ranges():
    d = by_path()
    rsi_period, rsi_value = d["entry.conditions.0.params.period"], d["entry.conditions.0.params.value"]
    assert (rsi_period["minimum"], rsi_period["maximum"], rsi_period["integer"], rsi_period["original"]) == (2, 250, True, 14)
    assert rsi_period["label"].endswith("기간") and rsi_period["editable"] is True
    assert (rsi_value["minimum"], rsi_value["maximum"], rsi_value["integer"]) == (0, 100, False)
    assert d["entry.conditions.1.params.shortMA"]["editable"] and d["entry.conditions.1.params.longMA"]["maximum"] == 500
    assert d["entry.conditions.2.params.value"]["maximum"] == 1000  # PER value_range
    assert d["exit.conditions.0.params.shortPeriod"]["minimum"] == 1
    assert d["exit.conditions.1.params.lookbackPeriod"]["minimum"] == 5
    assert d["exit.conditions.2.params.touchLookback"]["editable"] is True
    assert d["exit.conditions.2.params.period"]["maximum"] == 250


def test_only_existing_numeric_params_are_listed_and_nothing_is_filled():
    paths = set(by_path())
    assert not any(".operator" in p or ".signalType" in p or ".band" in p for p in paths)
    assert not any(p.startswith("entry.conditions.3") or ".params.pattern" in p for p in paths)
    # RSI에 없는 키(예: threshold)나 default 값을 만들어 넣지 않는다.
    assert "entry.conditions.0.params.threshold" not in paths


def test_unregistered_indicator_is_locked_with_reason():
    d = by_path()["exit.conditions.4.params.period"]
    assert d["editable"] is False and d["reason"] == "UNSUPPORTED_INDICATOR"
    assert "minimum" not in d


def test_param_without_range_metadata_is_locked():
    snap = copy.deepcopy(SNAPSHOT)
    snap["entry"]["conditions"][0]["params"]["extra"] = 3
    d = {x["path"]: x for x in build_editable_params(snap)}["entry.conditions.0.params.extra"]
    assert d["editable"] is False and d["reason"] == "NO_RANGE_METADATA"


def test_apply_overrides_changes_only_a_copy():
    before = copy.deepcopy(SNAPSHOT)
    modified, changed = apply_overrides(SNAPSHOT, [
        {"path": "entry.conditions.0.params.period", "value": 21},
        {"path": "entry.conditions.0.params.value", "value": 27.5},
        {"path": "exit.conditions.0.params.longPeriod", "value": 30.0},
    ])
    assert SNAPSHOT == before                                    # 원본 불변
    assert modified is not SNAPSHOT and modified["entry"] is not SNAPSHOT["entry"]
    assert modified["entry"]["conditions"][0]["params"]["period"] == 21
    assert modified["entry"]["conditions"][0]["params"]["value"] == 27.5
    assert modified["exit"]["conditions"][0]["params"]["longPeriod"] == 30
    assert isinstance(modified["exit"]["conditions"][0]["params"]["longPeriod"], int)
    assert len(changed) == 3
    modified["entry"]["conditions"][0]["params"]["period"] = 99  # 복사본 수정이 원본에 번지지 않는다
    assert SNAPSHOT["entry"]["conditions"][0]["params"]["period"] == 14


def test_overrides_equal_to_original_are_not_reported_as_changes():
    modified, changed = apply_overrides(SNAPSHOT, [{"path": "entry.conditions.0.params.period", "value": 14}])
    assert changed == [] and modified == SNAPSHOT


@pytest.mark.parametrize("override, code", [
    ({"path": "entry.conditions.0.params.period", "value": 1}, "OUT_OF_RANGE"),
    ({"path": "entry.conditions.0.params.period", "value": 251}, "OUT_OF_RANGE"),
    ({"path": "entry.conditions.0.params.value", "value": 101}, "OUT_OF_RANGE"),
    ({"path": "entry.conditions.0.params.period", "value": 14.5}, "NOT_INTEGER"),
    ({"path": "entry.conditions.0.params.period", "value": "14"}, "NOT_A_NUMBER"),
    ({"path": "entry.conditions.0.params.period", "value": float("nan")}, "NOT_A_NUMBER"),
    ({"path": "entry.conditions.0.params.period", "value": True}, "NOT_A_NUMBER"),
    ({"path": "entry.conditions.0.params.period", "value": None}, "NOT_A_NUMBER"),
    ({"path": "entry.conditions.0.params.operator", "value": 1}, "UNKNOWN_PATH"),
    ({"path": "entry.conditions.9.params.period", "value": 10}, "UNKNOWN_PATH"),
    ({"path": "risk.stop_loss_pct", "value": 5}, "UNKNOWN_PATH"),
    ({"path": "exit.conditions.4.params.period", "value": 10}, "NOT_EDITABLE"),
    ({"value": 10}, "UNKNOWN_PATH"),
])
def test_invalid_overrides_are_rejected_with_code(override, code):
    before = copy.deepcopy(SNAPSHOT)
    with pytest.raises(OverrideError) as exc:
        apply_overrides(SNAPSHOT, [override])
    assert exc.value.errors[0]["code"] == code
    assert SNAPSHOT == before


def test_duplicate_path_and_all_errors_are_reported_together():
    with pytest.raises(OverrideError) as exc:
        apply_overrides(SNAPSHOT, [
            {"path": "entry.conditions.0.params.period", "value": 10},
            {"path": "entry.conditions.0.params.period", "value": 11},
            {"path": "entry.conditions.0.params.value", "value": 500},
        ])
    assert [e["code"] for e in exc.value.errors] == ["DUPLICATE_PATH", "OUT_OF_RANGE"]


def test_non_list_overrides_are_treated_as_empty():
    modified, changed = apply_overrides(SNAPSHOT, None)
    assert changed == [] and modified == SNAPSHOT
