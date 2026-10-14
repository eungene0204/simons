"""KR builder and legacy parser cannot fall back to raw-word interpretation."""
import json

import ui_language
from intent import strategy_builder as builder
from intent.builder_interpreter import interpret_utterance
from engine.nl_parser import NLStrategyParser, ParsedStrategy


def test_missing_builder_llm_does_not_apply_raw_words():
    with ui_language.bind("ko"):
        previous = builder.BuilderState(universe="KOSPI", holding_count=10)
        result = builder.step(previous, "코스닥 12개 손절 7%")
        assert result.state.universe == "KOSPI"
        assert result.state.holding_count == 10
        assert result.state.stop_loss_pct is None


def test_structured_builder_fields_are_applied_without_lexical_merge():
    with ui_language.bind("ko"):
        previous = builder.BuilderState(universe="KOSPI", holding_count=10)
        result = builder.step(previous, "코스닥 12개", freetext_interpreter=lambda *args:
                              ({"universe": "KOSDAQ", "holding_count": 12}, []))
        assert result.state.universe == "KOSDAQ"
        assert result.state.holding_count == 12


def test_builder_control_comes_from_grounded_ops():
    state = builder.BuilderState(universe="KOSPI")
    chat = lambda *args, **kwargs: json.dumps({"ops": [{"op": "control", "field": "workflow",
        "value": "cancel", "source_text": "지금 그만"}]})
    with ui_language.bind("ko"):
        result = builder.step(state, "지금 그만", freetext_interpreter=lambda text, current:
                              interpret_utterance(text, current, chat))
        assert result.status == "exited"


def test_kr_seed_does_not_apply_regex_fields():
    with ui_language.bind("ko"):
        assert builder.seed_state("코스닥 12개 손절 7%") == builder.BuilderState()


def test_legacy_parse_routes_to_primary(monkeypatch):
    from strategy_conversation import primary
    expected = ParsedStrategy(max_positions=12)
    monkeypatch.setattr(primary, "run_primary_parse", lambda *args, **kwargs: {"parsed": expected})
    with ui_language.bind("ko"):
        parser = object.__new__(NLStrategyParser)
        assert parser.parse("어떤 말로 하든") is expected
        assert parser.parse_rule_based("코스닥 12개") is None
