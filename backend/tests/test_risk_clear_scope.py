"""위험 관리 설정을 비우는 수정 패치의 출처 판정 회귀 테스트.

배경(2026-11-06 되묻기 하니스): "이제 언제 매도할지 정해볼까요?"에 "RSI 70 이상이면 매도"라고 답하자
수정 인터프리터가 RSI 매도 조건 추가와 함께 `replace /risk_management/take_profit = null`을 내고, 답 전체를
인용으로 달았다. 인용 대조는 글자가 입력에 있다는 것만 보므로 통과해 기존 익절 30%가 사라졌다.
사용자가 그 설정을 없애라고 명시했다는 LLM 판정(yes+실재 인용)이 있을 때만 비운다.
"""

from __future__ import annotations

import json

from test_strategy_conversation import _rich_parsed, _stub_modify_interpreter

from strategy_conversation.interpreter.models import PatchOp
from strategy_conversation.interpreter.patch_scope_check import (
    is_risk_clear_patch,
    risk_clear_scope_verdict,
)
from strategy_conversation.interpreter.quote_check import QuoteVerdicts


def _run(monkeypatch, utter, verdict):
    from strategy_conversation import primary

    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.95,
        "patches": [
            {"op": "add", "path": "/exit_conditions/-",
             "value": {"factor": "technical.macd", "operator": "crosses_below", "value": None,
                       "source_text": "MACD 데드크로스면 매도"}},
            {"op": "replace", "path": "/risk_management/take_profit", "value": None,
             "source_text": utter},
        ],
    })
    calls = []

    def chat(system, user, **_kwargs):
        calls.append(system)
        return json.dumps(verdict, ensure_ascii=False)

    primary._interpreter_singleton._chat = chat
    monkeypatch.setattr(primary, "_check_condition_quotes", lambda *_a, **_k: QuoteVerdicts([]))
    prev = _rich_parsed()
    return primary.run_primary_modification(utter, prev.model_dump()), prev, calls


def test_unrequested_take_profit_clear_is_rejected_and_other_change_kept(monkeypatch):
    utter = "MACD 데드크로스면 매도"
    result, prev, calls = _run(monkeypatch, utter, {"verdict": "no", "quote": None})
    assert result is not None
    assert result["parsed"].take_profit_pct == prev.take_profit_pct == 20.0
    assert "macd" in [s.indicator for s in result["parsed"].exit_signals]
    assert any("익절" in c for c in calls)


def test_explicit_take_profit_clear_is_applied(monkeypatch):
    utter = "익절은 빼고 MACD 데드크로스면 매도"
    result, _, _ = _run(monkeypatch, utter, {"verdict": "yes", "quote": "익절은 빼고"})
    assert result is not None
    assert result["parsed"].take_profit_pct is None


def test_risk_clear_verdict_requires_real_quote_and_fails_closed():
    utter = "익절은 빼줘"
    patch = PatchOp(op="replace", path="/risk_management/take_profit", value=None, source_text=utter)
    answer = lambda payload: (lambda *_a, **_k: json.dumps(payload, ensure_ascii=False))
    assert risk_clear_scope_verdict(patch, utter, answer({"verdict": "yes", "quote": "익절은 빼줘"})) is True
    assert risk_clear_scope_verdict(patch, utter, answer({"verdict": "no", "quote": None})) is False
    assert risk_clear_scope_verdict(patch, utter, answer({"verdict": "yes", "quote": "없는 말"})) is None
    assert risk_clear_scope_verdict(patch, utter, answer({"verdict": "unclear", "quote": None})) is None
    assert risk_clear_scope_verdict(patch, utter, None) is None


def test_only_clearing_risk_patches_are_candidates():
    assert is_risk_clear_patch(PatchOp(op="replace", path="/risk_management/stop_loss", value=None))
    assert is_risk_clear_patch(PatchOp(op="replace", path="/risk_management/partial_take_profits", value=[]))
    assert is_risk_clear_patch(PatchOp(op="remove", path="/risk_management/trailing_stop"))
    assert not is_risk_clear_patch(PatchOp(op="replace", path="/risk_management/take_profit", value=15))
    assert not is_risk_clear_patch(PatchOp(op="replace", path="/portfolio/max_positions", value=None))


def test_over_clearing_decline_answer_keeps_turn_and_asks_only_real_changes(monkeypatch):
    """'익절은 굳이 안 할래' 한 마디에 위험 관리 칸 전부를 비우고 declined를 엉뚱한 자리에 쓴 수정 LLM 원출력
    형태(2026-11-13 가상 사용자 QA) — 없는 경로 하나로 턴 전체가 "해석하지 못했어요"로 끝났다."""
    from strategy_conversation import primary

    utter = "아 익절은 굳이 안 할래"
    quote = "익절은 굳이 안 할래"
    _stub_modify_interpreter(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.95,
        "patches": [
            {"op": "replace", "path": f"/risk_management/{field}", "value": value, "source_text": quote}
            for field, value in [
                ("take_profit", None), ("stop_loss", None), ("trailing_stop", None),
                ("partial_take_profits", []), ("max_position_weight", None),
                ("declined", [{"field": "take_profit", "source_text": quote}]),
            ]
        ],
    })
    calls = []

    def chat(system, user, **_kwargs):
        calls.append(system)
        asked_take_profit = '"/risk_management/take_profit"' in user
        return json.dumps({"verdict": "yes", "quote": quote} if asked_take_profit
                          else {"verdict": "no", "quote": None}, ensure_ascii=False)

    primary._interpreter_singleton._chat = chat
    monkeypatch.setattr(primary, "_check_condition_quotes", lambda *_a, **_k: QuoteVerdicts([]))
    prev = _rich_parsed().model_copy(update={"take_profit_pct": None})
    result = primary.run_primary_modification(utter, prev.model_dump())

    assert result is not None
    assert result["declined_fields"] == ["take_profit"]
    assert result["parsed"].stop_loss_pct == prev.stop_loss_pct == 8.0
    assert len(calls) == 2          # 익절(거부 신고)·손절(값이 있는 칸)만 묻는다 — 이미 빈 칸은 묻지 않는다


def test_misplaced_declined_patch_is_relocated_and_missing_field_clear_is_noop():
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.conversation.patch_applier import PatchError, apply_patches
    import pytest

    draft = decompile_strategy(ParsedStrategy(description="저PBR", stop_loss_pct=5.0))
    patched = apply_patches(draft, [
        PatchOp(op="replace", path="/risk_management/declined",
                value=[{"field": "take_profit", "source_text": "익절 안 함"}], source_text="익절 안 함"),
        PatchOp(op="replace", path="/risk_management/max_position_weight", value=None,
                source_text="익절 안 함"),
    ])
    assert patched.declined == ["take_profit"]
    assert patched.risk_management.stop_loss == 5
    with pytest.raises(PatchError):
        apply_patches(draft, [PatchOp(op="replace", path="/risk_management/no_such_field", value=3)])


def test_exit_decline_is_recorded_only_when_no_exit_condition_existed():
    """'매도 조건은 안 정할게요'를 빈 매도 조건 비움(+인용)으로 낸 수정 LLM 원출력 형태(2026-11-13 SU01) —
    '안 함'으로 기록한다. 있던 매도 조건을 지우는 패치는 삭제일 뿐 거부가 아니다."""
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.conversation.patch_applier import apply_patches
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.completeness_validator import validate_completeness

    clear = PatchOp(op="replace", path="/exit_conditions", value=[],
                    source_text="매도 조건은 딱히 정하지 않을게요")
    empty = decompile_strategy(ParsedStrategy(description="저PBR"))
    assert apply_patches(empty, [clear]).declined == ["exit"]
    assert apply_patches(decompile_strategy(_rich_parsed()), [clear]).declined == []

    # 거부한 전략에는 완결성 검증도 청산 규칙을 다시 묻지 않는다.
    spec = decompile_strategy(ParsedStrategy.model_validate({
        "description": "저PER", "universe": ["KOSPI"],
        "fundamental_filters": [{"metric": "per", "operator": "<=", "value": 10}],
        "rebalancing_period": "none",
    }))
    asked, _ = validate_completeness(StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0))
    assert "strategy.exit_conditions" in asked
    spec.declined = ["exit"]
    declined, _ = validate_completeness(StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0))
    assert "strategy.exit_conditions" not in declined
