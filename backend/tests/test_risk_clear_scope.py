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
