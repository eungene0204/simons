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


def _run(chat, result=_READY, feasibility=None, turns=(), has_strategy=True):
    calls = {"interpret": 0, "feasibility": 0, "recall": 0, "quotes": None}

    def interpret(recalled_quotes=()):
        calls["interpret"] += 1
        calls["quotes"] = list(recalled_quotes)
        return result

    def recall():
        calls["recall"] += 1
        return list(turns)

    def check(parsed_result):
        calls["feasibility"] += 1
        return feasibility or {"checked": True, "trades": 0}

    out = orchestrator.orchestrate(
        "PER 10 이하 종목", has_strategy=has_strategy, pending_question=None, chat_fn=chat,
        interpret=interpret, recall=recall, check_feasibility=check, max_steps=4)
    calls = {key: value for key, value in calls.items() if key != "quotes" or value}
    return out, calls


def test_interpret_then_feasibility_then_finish():
    chat = _Chat({"action": "interpret"})
    out, calls = _run(chat)

    assert out["result"] is _READY and out["feasibility"] == {"checked": True, "trades": 0}
    assert calls == {"interpret": 1, "feasibility": 1, "recall": 0}
    # LLM이 고르는 것은 해석 전 한 번뿐 — 해석 뒤의 점검·종료는 묻지 않는다.
    assert [state["available_actions"] for state in chat.states] == [["recall", "interpret"]]


def test_feasibility_runs_without_asking_the_llm_after_interpret():
    """해석 뒤 선택을 LLM에 물으면 interpret를 다시 골라 점검이 빠졌다(2026-11-14~15 Trace 43/93턴)."""
    chat = _Chat({"action": "interpret"}, {"action": "interpret"})
    out, calls = _run(chat)

    assert out["feasibility"] == {"checked": True, "trades": 0}
    assert calls == {"interpret": 1, "feasibility": 1, "recall": 0}
    assert len(chat.states) == 1


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

    chat = _Chat({"action": "interpret"})
    out, calls = _run(chat)
    assert out["result"] is _READY
    assert calls["interpret"] == 1  # 같은 발화를 두 번 반영하지 않는다


def test_single_available_action_runs_without_asking_the_llm():
    chat = _Chat({"action": "recall"})
    out, calls = _run(chat)

    # recall 뒤에는 interpret뿐, 해석 뒤에는 점검뿐 — 기록이 비어 있으면 LLM은 처음 한 번만 부른다.
    assert calls == {"interpret": 1, "feasibility": 1, "recall": 1}
    assert [state["available_actions"] for state in chat.states] == [["recall", "interpret"]]


def test_turn_without_a_strategy_never_asks_the_llm():
    """고칠 전략이 없는 턴은 기억 조회를 열지 않는다 — 고를 것이 없어 진행 전체가 결정론이다."""
    chat = _Chat()
    out, calls = _run(chat, has_strategy=False)

    assert out["result"] is _READY and out["feasibility"] == {"checked": True, "trades": 0}
    assert calls == {"interpret": 1, "feasibility": 1, "recall": 0} and chat.states == []


_PAST = [{"turn": 1, "utterance": "PER 10 이하이고 ROE 15% 이상, 손절 5%", "question": None,
          "state_hash": "a" * 64, "feasibility": None}]


def test_recalled_reference_reaches_interpret_as_a_verbatim_quote():
    """기억이 해석에 쓰인다 — LLM은 이전 발화 조각을 고를 뿐이고, 기록에 없는 조각은 버린다."""
    chat = _Chat({"action": "recall"},
                 {"quotes": ["ROE 15% 이상", "PBR 1 이하", "PER 10 이하"]})
    out, calls = _run(chat, turns=_PAST)

    # 'PBR 1 이하'는 기록에 없고(지어낸 조각), 'PER 10 이하'는 이번 발화에 이미 있는 말이다.
    assert calls["quotes"] == ["ROE 15% 이상"]
    assert chat.states[1] == {"utterance": "PER 10 이하 종목", "turns": [
        {"turn": 1, "utterance": _PAST[0]["utterance"]}]}


@pytest.mark.parametrize("reply", ["JSON 아님", {"quotes": "PER 10 이하"}, {"quotes": []}])
def test_unresolved_reference_interprets_the_utterance_as_is(reply):
    out, calls = _run(_Chat({"action": "recall"}, reply), turns=_PAST)
    assert out["result"] is _READY and "quotes" not in calls


@pytest.mark.parametrize("reply", ["말로만 답함", {"action": "rewrite_strategy"}, {"action": "check_feasibility"}])
def test_contract_violation_without_interpret_leaves_fallback_to_caller(reply):
    out, calls = _run(_Chat(reply))

    assert out == {"result": None, "feasibility": None}
    assert calls["interpret"] == 0


def test_llm_failure_falls_back_but_interpret_errors_propagate():
    def broken_chat(system, user, max_tokens=None):
        raise RuntimeError("upstream 502")

    out = orchestrator.orchestrate(
        "x", has_strategy=True, pending_question=None, chat_fn=broken_chat,
        interpret=lambda: _READY, recall=list, check_feasibility=lambda r: {})
    assert out == {"result": None, "feasibility": None}

    def failing_interpret():
        raise OSError("LLM 연결 실패")

    with pytest.raises(OSError):
        orchestrator.orchestrate(
            "x", has_strategy=True, pending_question=None,
            chat_fn=_Chat({"action": "interpret"}), interpret=failing_interpret,
            recall=list, check_feasibility=lambda r: {})


def test_feasibility_samples_a_large_universe_first():
    """전 종목 점검은 60초를 넘겨 '점검 못 함'으로 끝났다(2026-11-16 10턴 중 6턴) — 표본을 먼저 본다."""
    symbols = [f"{i:06d}" for i in range(2600)]
    request = {"symbols": symbols, "universe_id": "kosdaq_kospi"}
    seen = []

    def run(trades_by_size):
        def backtest(req):
            seen.append((len(req["symbols"]), req.get("universe_id")))
            return {"trades": trades_by_size[len(req["symbols"])]}
        return backtest

    # 표본에서 거래가 나오면 전체를 돌지 않는다. 표본은 종목 목록으로만 돈다(universe_id 없음).
    assert orchestrator.run_feasibility(request, run({300: 7})) == {
        "checked": True, "trades": 7, "sampled": True}
    assert seen == [(300, None)]
    # 표본이 0건이면 전체로 확인한다 — '거래 0건' 안내는 전체 결과로만 낸다.
    seen.clear()
    assert orchestrator.run_feasibility(request, run({300: 0, 2600: 0})) == {"checked": True, "trades": 0}
    assert seen == [(300, None), (2600, "kosdaq_kospi")]
    assert orchestrator.feasibility_notice({"checked": True, "trades": 7, "sampled": True}) is None
    # 작은 유니버스는 표본 없이 그대로다.
    seen.clear()
    orchestrator.run_feasibility({"symbols": symbols[:200]}, run({200: 3}))
    assert seen == [(200, None)]


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


def test_memory_renumbers_when_a_concurrent_turn_takes_the_number(app_db, monkeypatch):
    """2026-11-17: MAX+1로 매긴 번호를 동시 요청이 먼저 쓰면 같은 턴 번호가 두 줄 생겼다.
    (draftId, turn) 유니크에 걸리면 번호를 다시 매겨 기록한다."""
    import db

    real_connect = db.connect
    raced = []

    class RacingConn:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def __enter__(self):
            self._conn.__enter__()
            return self

        def __exit__(self, *exc):
            return self._conn.__exit__(*exc)

        def execute(self, sql, params=()):
            if sql.startswith("INSERT") and not raced:
                raced.append(True)  # 이 INSERT 직전에 다른 요청이 같은 번호를 먼저 커밋한다
                other = real_connect()
                try:
                    with other:
                        values = list(params)
                        values[0], values[4] = "concurrent", "동시 발화"
                        other.execute(sql, tuple(values))
                finally:
                    other.close()
            return self._conn.execute(sql, params)

    monkeypatch.setattr(db, "connect", lambda: RacingConn(real_connect()))
    memory.remember("draft-000000000001", None, "내 발화", None, "a" * 64)

    turns = memory.recall("draft-000000000001")
    assert [(t["turn"], t["utterance"]) for t in turns] == [(1, "동시 발화"), (2, "내 발화")]


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


_PREVIOUS = {"description": "x", "universe": ["KOSPI"]}


def test_wiring_falls_back_to_fixed_pipeline_when_agent_fails(monkeypatch):
    main, calls = _wire(monkeypatch, "primary", _Chat("JSON 아님"), _PARSED)
    result, _remember = main._run_nl_parse_orchestrated(
        main.NLParseRequest(prompt="x", previous_parsed=_PREVIOUS), None, None, "d" * 16)

    assert result["parsed"] == _PARSED["parsed"] and result["notices"] == []
    assert calls["parse"] == 1 and calls["backtest"] == 0


def test_wiring_appends_recalled_quotes_to_the_interpreted_prompt(monkeypatch):
    chat = _Chat({"action": "recall"}, {"quotes": ["PER 10 이하"]})
    main, calls = _wire(monkeypatch, "primary", chat, _PARSED)
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "primary")
    monkeypatch.setattr(memory, "recall", lambda draft_id, owner_id=None, limit=memory.RECALL_LIMIT: list(_PAST))
    prompts = []
    monkeypatch.setattr(main, "_run_nl_parse_traced",
                        lambda request, on_stage=None, defer_holder=None: prompts.append(request.prompt) or dict(_PARSED))
    _result, remember = main._run_nl_parse_orchestrated(
        main.NLParseRequest(prompt="아까 말한 PER 조건 다시 넣어줘", previous_parsed=_PREVIOUS),
        None, None, "d" * 16)
    remember()

    assert prompts == ['아까 말한 PER 조건 다시 넣어줘 (앞서 한 말: "PER 10 이하")']
    # 기억에는 사용자가 실제로 친 말만 남긴다.
    assert calls["remembered"][0][2] == "아까 말한 PER 조건 다시 넣어줘"


def test_wiring_keeps_a_chip_click_away_from_the_agent(monkeypatch):
    """칩 클릭은 시스템 선택지의 선택이다 — 입력이 바뀌면 결정론 귀속이 깨진다."""
    chat = _Chat()
    main, calls = _wire(monkeypatch, "primary", chat, _PARSED)
    main._run_nl_parse_orchestrated(main.NLParseRequest(
        prompt="손절 기준 7%", previous_parsed=_PREVIOUS,
        pending_ask={"question": "q", "topic": "값 확인", "chips": ["손절 기준 7%", "손절 기준 5% 유지"]}),
        None, None, "d" * 16)
    assert chat.states == [] and calls["parse"] == 1


def test_owner_header_is_parsed_defensively():
    import main

    assert main._owner_id("42") == 42
    assert main._owner_id(None) is None and main._owner_id("") is None
    assert main._owner_id("1; DROP") is None and main._owner_id("-3") is None
    # 엔드포인트를 직접 부를 때의 기본값(Header 객체)도 비로그인으로 본다.
    assert main._owner_id(main.Header(default=None)) is None


def test_wiring_leaves_the_prompt_alone_when_the_primary_lane_is_off(monkeypatch):
    """primary가 꺼진 레인에는 '앞서 한 말'을 덧붙이지 않는다 — 레거시 원문 스캔의 입력을 넓히지 않는다."""
    chat = _Chat({"action": "recall"}, {"quotes": ["PER 10 이하"]})
    main, _calls = _wire(monkeypatch, "primary", chat, _PARSED)
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "off")
    monkeypatch.setattr(memory, "recall", lambda draft_id, owner_id=None, limit=memory.RECALL_LIMIT: list(_PAST))
    prompts = []
    monkeypatch.setattr(main, "_run_nl_parse_traced",
                        lambda request, on_stage=None, defer_holder=None: prompts.append(request.prompt) or dict(_PARSED))
    main._run_nl_parse_orchestrated(
        main.NLParseRequest(prompt="아까 말한 PER 조건 다시 넣어줘", previous_parsed=_PREVIOUS),
        None, None, "d" * 16)
    assert prompts == ["아까 말한 PER 조건 다시 넣어줘"]
