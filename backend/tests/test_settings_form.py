"""인터프리터 설정 옮겨 적기 형태 — 말한 설정만 받아 전체 형태로 펴는 형식 변환 계약.

핵심: 차림표의 경로만 편다, 인용은 요청 문장에 실재해야 한다, null 값은 '말하지 않음',
위반은 고치지 않고 보고해 전체 형태로 다시 받게 한다. 기본은 꺼져 있다.
"""

import json

from strategy_conversation.interpreter.llm_strategy_interpreter import StrategyInterpreter
from strategy_conversation.interpreter.output_repair import expand_settings_form
from strategy_conversation.interpreter.prompts import (
    _OUTPUT_SHAPE,
    _compact_shape,
    build_system_prompt,
    setting_paths,
)

_INPUT = "코스피에서 RSI 30 이하면 매수, 손절 7%, 수수료 0.1%"
_ENTRY = {"factor": "technical.rsi", "operator": "<=", "value": 30, "source_text": "RSI 30 이하면 매수"}


def _form(settings, **strategy):
    return json.dumps({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI"]}, "entry_conditions": [_ENTRY],
        "settings": settings, **strategy}}, ensure_ascii=False)


def _setting(path, value, quote):
    return {"path": path, "value": value, "source_texts": [quote]}


def test_menu_covers_every_setting_key_of_full_shape():
    """차림표에서 빠진 칸은 모델이 채울 자리가 없다 — 전체 형태의 설정 칸 전부가 실린다."""
    full = _OUTPUT_SHAPE["strategy"]
    compact = _compact_shape()["strategy"]
    paths = set(setting_paths())
    for section in ("universe", "portfolio", "risk_management", "backtest"):
        for key in full[section]:
            assert f"{section}.{key}" in paths or key in compact.get(section, {})
    conditions_and_lists = {"entry_conditions", "exit_conditions", "entry_logic", "ranking", "name"}
    assert set(full) - set(compact) - conditions_and_lists <= paths | {
        "portfolio", "risk_management", "backtest"}
    assert "risk_management.stop_loss" in build_system_prompt(compact=True)
    assert '"settings"' not in build_system_prompt()


def test_expands_stated_settings_into_full_shape():
    text, violations = expand_settings_form(_form([
        _setting("risk_management.stop_loss", 7, "손절 7%"),
        _setting("backtest.fee_rate", 0.1, "수수료 0.1%"),
        _setting("portfolio.selection_count", None, "매수"),
        _setting("declined", ["take_profit"], "매수"),
    ]), _INPUT)
    strategy = json.loads(text)["strategy"]
    assert violations == []
    assert strategy["risk_management"] == {"stop_loss": 7}
    assert strategy["backtest"] == {"fee_rate": 0.1}
    assert strategy["declined"] == ["take_profit"]
    assert "settings" not in strategy and "portfolio" not in strategy


def test_reports_unknown_path_and_ungrounded_quote_without_applying():
    text, violations = expand_settings_form(_form([
        _setting("market_filter.exposure_pct", 50, "손절 7%"),
        _setting("risk_management.take_profit", 20, "익절 20%"),
    ]), _INPUT)
    assert len(violations) == 2
    assert "risk_management" not in json.loads(text)["strategy"]


def test_restated_setting_merges_and_conflict_is_reported():
    """같은 설정을 다른 말로 또 말하면 같은 경로가 두 줄 온다 — 같은 값이면 한 번, 다르면 위반."""
    text, violations = expand_settings_form(_form([
        _setting("risk_management.stop_loss", 7, "손절 7%"),
        _setting("risk_management.stop_loss", 7.0, "손절"),
    ]), _INPUT)
    assert violations == [] and json.loads(text)["strategy"]["risk_management"] == {"stop_loss": 7}
    _, violations = expand_settings_form(_form([
        _setting("risk_management.stop_loss", 7, "손절 7%"),
        _setting("risk_management.stop_loss", 0.1, "수수료 0.1%"),
    ]), _INPUT)
    assert len(violations) == 1


def test_hoists_top_level_keys_misplaced_inside_strategy():
    text, _ = expand_settings_form(_form([], unsupported_features=["뉴스 심리"]), _INPUT)
    doc = json.loads(text)
    assert doc["unsupported_features"] == ["뉴스 심리"]
    assert "unsupported_features" not in doc["strategy"]


def test_unparseable_output_is_left_for_schema_repair():
    assert expand_settings_form("JSON 아님", _INPUT) == ("JSON 아님", [])


class _Chat:
    def __init__(self, compact_reply, full_reply):
        self.replies = {True: compact_reply, False: full_reply}
        self.forms = []

    def __call__(self, system_prompt, user_message, **kwargs):
        compact = '"settings"' in system_prompt
        self.forms.append("settings" if compact else "full")
        return self.replies[compact]


_FULL_REPLY = json.dumps({"intent": "CREATE_STRATEGY", "strategy": {
    "universe": {"markets": ["KOSPI"]}, "entry_conditions": [_ENTRY],
    "risk_management": {"stop_loss": 7}, "backtest": {"fee_rate": 0.1}}}, ensure_ascii=False)


def test_interpreter_uses_settings_form_when_enabled(monkeypatch):
    monkeypatch.setenv("STRATEGY_INTERPRETER_SETTINGS_FORM", "on")
    chat = _Chat(_form([_setting("risk_management.stop_loss", 7, "손절 7%")]), _FULL_REPLY)
    result = StrategyInterpreter(chat_fn=chat, model="test").interpret(_INPUT)
    assert chat.forms == ["settings"]
    assert result.intent.strategy.risk_management.stop_loss == 7
    assert result.prompt_version.endswith("+settings")


def test_interpreter_falls_back_to_full_form_on_violation(monkeypatch):
    monkeypatch.setenv("STRATEGY_INTERPRETER_SETTINGS_FORM", "on")
    chat = _Chat(_form([_setting("risk_management.stop_loss", 10, "손절 10%")]), _FULL_REPLY)
    result = StrategyInterpreter(chat_fn=chat, model="test").interpret(_INPUT)
    assert chat.forms == ["settings", "full"]
    assert not result.prompt_version.endswith("+settings")
    assert result.intent.strategy.risk_management.stop_loss == 7
    assert result.intent.strategy.backtest.fee_rate is not None


def test_interpreter_keeps_full_form_by_default_and_for_modify(monkeypatch):
    chat = _Chat("", _FULL_REPLY)
    StrategyInterpreter(chat_fn=chat, model="test").interpret(_INPUT)
    monkeypatch.setenv("STRATEGY_INTERPRETER_SETTINGS_FORM", "on")
    StrategyInterpreter(chat_fn=chat, model="test").interpret(_INPUT, draft={"universe": {}})
    assert chat.forms == ["full", "full"]
