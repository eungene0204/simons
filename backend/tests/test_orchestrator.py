"""총괄 에이전트(planner/orchestrator.py)·대화 기억(conversation/memory.py) 회귀.

에이전트는 진행만 고른다 — 전략을 만들지도, 사용자에게 보일 글을 쓰지도 않는다. 이 파일은
결정론 관문(해석 한 번·미완성 전략 점검 금지·폴백)과 기억의 왕복·보관 기한을 고정한다.
"""

import json
from datetime import timedelta

import pytest

from strategy_conversation.conversation import memory
from strategy_conversation.planner import orchestrator
from strategy_conversation.response.output_guard import guard_text


class _Chat:
    def __init__(self, *actions):
        self.replies = [json.dumps(a) if isinstance(a, dict) else a for a in actions]
        self.states = []

    def __call__(self, system, user, max_tokens=None):
        self.states.append(json.loads(user))
        return self.replies.pop(0) if self.replies else '{"action":"finish"}'


_READY = {"parsed": {"universe": ["KOSPI"]}, "backtest_request": {"symbols": ["005930"]},
          "symbol_count": 1, "clarification_question": None, "notices": []}
_ASKING = {**_READY, "clarification_question": "얼마나 자주 다시 구성할까요?"}


def _run(chat, result=_READY, feasibility=None, turns=()):
    calls = {"interpret": 0, "feasibility": 0, "recall": 0}

    def interpret():
        calls["interpret"] += 1
        return result

    def recall():
        calls["recall"] += 1
        return list(turns)

    def check(parsed_result):
        calls["feasibility"] += 1
        return feasibility or {"checked": True, "trades": 0}

    out = orchestrator.orchestrate(
        "PER 10 이하 종목", has_strategy=False, pending_question=None, chat_fn=chat,
        interpret=interpret, recall=recall, check_feasibility=check, max_steps=4)
    return out, calls


def test_interpret_then_feasibility_then_finish():
    chat = _Chat({"action": "interpret"}, {"action": "check_feasibility"}, {"action": "finish"})
    out, calls = _run(chat)

    assert out["result"] is _READY and out["feasibility"] == {"checked": True, "trades": 0}
    assert calls == {"interpret": 1, "feasibility": 1, "recall": 0}
    # 관찰에는 진행 판단용 구조 필드만 — 전략 본문은 LLM에 다시 싣지 않는다.
    assert chat.states[1]["steps"][0]["observation"] == {
        "question": None, "priority": None, "notices": 0, "symbol_count": 1}
    assert [state["available_actions"] for state in chat.states] == [
        ["recall", "interpret"], ["check_feasibility", "finish"]]  # 점검 뒤에는 finish뿐이라 호출 없음


def test_feasibility_is_refused_while_a_question_is_open():
    chat = _Chat({"action": "interpret"}, {"action": "check_feasibility"}, {"action": "finish"})
    out, calls = _run(chat, result=_ASKING)

    assert out["result"] is _ASKING and out["feasibility"] is None
    assert calls["feasibility"] == 0
    # 남은 질문이 있으면 고를 액션이 finish뿐이다 — LLM을 더 부르지 않고 끝낸다.
    assert len(chat.states) == 1
    assert orchestrator.feasibility_blocker(_ASKING) and not orchestrator.feasibility_blocker(_READY)


def test_finish_before_interpret_is_a_violation_and_interpret_never_repeats():
    out, calls = _run(_Chat({"action": "finish"}))
    assert out == {"result": None, "feasibility": None} and calls["interpret"] == 0

    chat = _Chat({"action": "interpret"}, {"action": "interpret"})
    out, calls = _run(chat)
    assert out["result"] is _READY
    assert calls["interpret"] == 1  # 같은 발화를 두 번 반영하지 않는다


def test_single_available_action_runs_without_asking_the_llm():
    chat = _Chat({"action": "recall"}, {"action": "finish"})
    out, calls = _run(chat)

    # recall 뒤에는 interpret뿐 — LLM 호출 없이 해석하고, 그다음 선택(점검/종료)만 묻는다.
    assert calls == {"interpret": 1, "feasibility": 0, "recall": 1}
    assert [state["available_actions"] for state in chat.states] == [
        ["recall", "interpret"], ["check_feasibility", "finish"]]


@pytest.mark.parametrize("reply", ["말로만 답함", {"action": "rewrite_strategy"}, {"action": "check_feasibility"}])
def test_contract_violation_without_interpret_leaves_fallback_to_caller(reply):
    out, calls = _run(_Chat(reply))

    assert out == {"result": None, "feasibility": None}
    assert calls["interpret"] == 0


def test_llm_failure_falls_back_but_interpret_errors_propagate():
    def broken_chat(system, user, max_tokens=None):
        raise RuntimeError("upstream 502")

    out = orchestrator.orchestrate(
        "x", has_strategy=False, pending_question=None, chat_fn=broken_chat,
        interpret=lambda: _READY, recall=list, check_feasibility=lambda r: {})
    assert out == {"result": None, "feasibility": None}

    def failing_interpret():
        raise OSError("LLM 연결 실패")

    with pytest.raises(OSError):
        orchestrator.orchestrate(
            "x", has_strategy=False, pending_question=None,
            chat_fn=_Chat({"action": "interpret"}), interpret=failing_interpret,
            recall=list, check_feasibility=lambda r: {})


def test_recall_shows_past_turns_to_the_agent():
    turns = [{"turn": 1, "utterance": "PER 10 이하", "question": "기간은요?",
              "state_hash": "a" * 64, "feasibility": None}]
    chat = _Chat({"action": "recall"}, {"action": "finish"})
    _run(chat, turns=turns)

    assert chat.states[1]["steps"][0]["observation"] == {"turns": [
        {"utterance": "PER 10 이하", "question": "기간은요?", "feasibility": None}]}


def test_feasibility_runner_counts_trades_and_swallows_failures():
    assert orchestrator.run_feasibility({}, lambda req: {"trades": 0}) == {"checked": True, "trades": 0}
    assert orchestrator.run_feasibility({}, lambda req: {"trades": 12}) == {"checked": True, "trades": 12}

    def boom(req):
        raise TimeoutError("watchdog")

    assert orchestrator.run_feasibility({}, boom) == {"checked": False}


def test_notice_only_for_a_checked_zero_trade_strategy():
    assert orchestrator.feasibility_notice({"checked": True, "trades": 0}) == orchestrator.NO_TRADE_NOTICE
    assert orchestrator.feasibility_notice({"checked": True, "trades": 3}) is None
    assert orchestrator.feasibility_notice({"checked": False}) is None
    assert orchestrator.feasibility_notice(None) is None
    # 규제 출력 가드가 문장을 건드리지 않는다(사실 문장 — 예측·권유 없음).
    assert guard_text(orchestrator.NO_TRADE_NOTICE) == orchestrator.NO_TRADE_NOTICE


# ── 대화 기억(앱 DB) ─────────────────────────────────────────────────────────

def test_memory_round_trip_and_feasibility_reuse(app_db):
    memory.remember("draft-000000000001", None, "PER 10 이하", "기간은요?", "a" * 64)
    memory.remember("draft-000000000001", None, "5년", None, "b" * 64, {"checked": True, "trades": 0})
    memory.remember("draft-000000000002", None, "다른 대화", None, "c" * 64)

    turns = memory.recall("draft-000000000001")
    assert [(t["turn"], t["utterance"], t["question"]) for t in turns] == [
        (1, "PER 10 이하", "기간은요?"), (2, "5년", None)]
    assert memory.remembered_feasibility(turns, "b" * 64) == {"checked": True, "trades": 0}
    assert memory.remembered_feasibility(turns, "a" * 64) is None


def test_memory_is_scoped_to_its_owner_and_dies_with_the_account(app_db):
    import db

    for user_id in (1, 2):
        app_db.execute('INSERT INTO "User" (id, email, name, password, "updatedAt") VALUES (?, ?, ?, ?, ?)',
                       (user_id, f"u{user_id}@example.com", "u", "x", db.now()))
    app_db.commit()
    memory.remember("draft-000000000001", 1, "내 발화", None, "a" * 64)

    assert [t["utterance"] for t in memory.recall("draft-000000000001", 1)] == ["내 발화"]
    # 초안 ID를 알아도 다른 계정·비로그인으로는 읽히지 않는다.
    assert memory.recall("draft-000000000001", 2) == []
    assert memory.recall("draft-000000000001", None) == []

    app_db.execute('DELETE FROM "User" WHERE id = 1')
    app_db.commit()
    assert app_db.execute(f'SELECT COUNT(*) FROM "{memory.TABLE}"').fetchone()[0] == 0


def test_memory_drops_turns_past_retention(app_db):
    import db

    memory.remember("draft-000000000001", None, "오래된 발화", None, "a" * 64)
    app_db.execute(f'UPDATE "{memory.TABLE}" SET "createdAt" = ?',
                   (db.now() - memory.RETENTION - timedelta(hours=1),))
    app_db.commit()
    assert memory.recall("draft-000000000001") == []
    # 읽기만 해도 기한 지난 원문이 지워진다.
    assert app_db.execute(f'SELECT COUNT(*) FROM "{memory.TABLE}"').fetchone()[0] == 0

    memory.remember("draft-000000000001", None, "새 발화", None, "b" * 64)
    rows = app_db.execute(f'SELECT "utterance" FROM "{memory.TABLE}"').fetchall()
    assert [r[0] for r in rows] == ["새 발화"]  # 기한 지난 원문은 지워진다


def test_memory_is_optional(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:x@127.0.0.1:1/none")
    assert memory.recall(None) == []
    assert memory.recall("draft-000000000001") == []          # 연결 실패 = 기억 없음
    memory.remember("draft-000000000001", None, "x", None, "a" * 64)  # 예외 없이 지나간다


# ── 배선(main._run_nl_parse_orchestrated) ────────────────────────────────────

def _wire(monkeypatch, mode, chat, parse_result):
    import main
    from strategy_conversation import primary

    monkeypatch.setenv("STRATEGY_ORCHESTRATOR_MODE", mode)
    calls = {"parse": 0, "backtest": 0, "remembered": []}

    def fake_traced(request, on_stage=None, defer_holder=None):
        calls["parse"] += 1
        return dict(parse_result)

    def fake_backtest(_engine, req):
        calls["backtest"] += 1
        return {"trades": 0}

    monkeypatch.setattr(main, "_run_nl_parse_traced", fake_traced)
    monkeypatch.setattr(main.backtest_executor, "run", fake_backtest)
    monkeypatch.setattr(main, "watchdog_run_with_timeout", lambda fn, timeout_s=None: fn())
    monkeypatch.setattr(main.BacktestRequest, "model_validate",
                        classmethod(lambda cls, req: type("R", (), {"model_dump": lambda self: req})()))
    monkeypatch.setattr(primary, "_interpreter_singleton", type("I", (), {"_chat": staticmethod(chat)})())
    monkeypatch.setattr(memory, "recall", lambda draft_id, owner_id=None, limit=memory.RECALL_LIMIT: [])
    monkeypatch.setattr(memory, "remember", lambda *a: calls["remembered"].append(a))
    return main, calls


_PARSED = {"parsed": {"description": "x", "universe": ["KOSPI"]},
           "backtest_request": {"symbols": ["005930"]}, "symbol_count": 1,
           "clarification_question": None, "notices": []}


def test_wiring_off_runs_fixed_pipeline_only(monkeypatch):
    main, calls = _wire(monkeypatch, "off", _Chat(), _PARSED)
    result, remember = main._run_nl_parse_orchestrated(main.NLParseRequest(prompt="x"), None, None, "d" * 16)

    assert remember is None
    assert result["notices"] == [] and calls == {"parse": 1, "backtest": 0, "remembered": []}


def test_wiring_adds_zero_trade_notice_and_remembers_the_turn(monkeypatch):
    chat = _Chat({"action": "interpret"}, {"action": "check_feasibility"}, {"action": "finish"})
    main, calls = _wire(monkeypatch, "primary", chat, _PARSED)
    result, remember = main._run_nl_parse_orchestrated(
        main.NLParseRequest(prompt="PER 10 이하"), None, None, "d" * 16, 7)

    assert calls["remembered"] == []  # 기록은 호출부가 버전 commit 뒤에 한다(취소·충돌 턴은 기억하지 않는다)
    remember()
    assert result["notices"] == [orchestrator.NO_TRADE_NOTICE]
    assert result["parsed"] == _PARSED["parsed"]  # 전략은 그대로다
    assert calls["parse"] == 1 and calls["backtest"] == 1
    (draft_id, owner_id, utterance, question, _hash, feasibility), = calls["remembered"]
    assert (draft_id, owner_id, utterance, question, feasibility) == (
        "d" * 16, 7, "PER 10 이하", None, {"checked": True, "trades": 0})


def test_wiring_falls_back_to_fixed_pipeline_when_agent_fails(monkeypatch):
    main, calls = _wire(monkeypatch, "primary", _Chat("JSON 아님"), _PARSED)
    result, _remember = main._run_nl_parse_orchestrated(main.NLParseRequest(prompt="x"), None, None, "d" * 16)

    assert result["parsed"] == _PARSED["parsed"] and result["notices"] == []
    assert calls["parse"] == 1 and calls["backtest"] == 0


def test_owner_header_is_parsed_defensively():
    import main

    assert main._owner_id("42") == 42
    assert main._owner_id(None) is None and main._owner_id("") is None
    assert main._owner_id("1; DROP") is None and main._owner_id("-3") is None
    # 엔드포인트를 직접 부를 때의 기본값(Header 객체)도 비로그인으로 본다.
    assert main._owner_id(main.Header(default=None)) is None
