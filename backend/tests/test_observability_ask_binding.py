"""되묻기 결속 게이트 판정(ask_binding_gate) 테스트.

pending_ask는 "이 답이 저 질문의 답"이라는 유일한 결정론 근거다. 발행까지 통과해야
하는 게이트가 여럿인데 실패가 전부 조용한 폴백이라, Trace에 유무만 실으면 원인을
구분할 수 없다. 이 판정이 그 구분을 만든다 — 판정을 새로 하지 않고 실행 계층의
결과에 이름만 붙인다는 계약도 함께 지킨다.
"""

from __future__ import annotations

from observability.agent_trace import ask_binding_gate


def _gate(**overrides):
    base = dict(
        question="리밸런싱 주기를 정할까요?",
        priority="dag_planner",
        chips_offered=["매월 리밸런싱"],
        pending_ask={"topic": "리밸런싱", "question": "리밸런싱 주기를 정할까요?",
                     "chips": ["매월 리밸런싱"]},
        planner_mode_primary=True,
        planner_ran=True,
        ask_reason=None,
    )
    base.update(overrides)
    return ask_binding_gate(**base)


def test_bound_ask_is_ok():
    verdict = _gate()
    assert verdict["gate"] == "ok"
    assert verdict["bound"] is True
    assert verdict["chips_bound"] == 1
    assert "chips_dropped" not in verdict


def test_turn_without_question_is_not_a_loss():
    """되묻기가 없는 턴은 결속할 대상이 없다 — 실패로 세면 안 된다."""
    verdict = _gate(question=None, pending_ask=None, chips_offered=None)
    assert verdict["gate"] == "no_question"
    assert verdict["bound"] is False


def test_planner_off_is_named_separately():
    """planner가 꺼져 있으면 결속 자체가 발행되지 않는다 — 칩 결속 실패와 다른 원인이다."""
    verdict = _gate(pending_ask=None, planner_mode_primary=False, planner_ran=False)
    assert verdict["gate"] == "planner_off"


def test_planner_failure_is_distinguished_from_ask_rejection():
    assert _gate(pending_ask=None, planner_ran=False)["gate"] == "planner_failed"
    assert _gate(pending_ask=None, ask_reason="filled_slot")["gate"] == (
        "ask_rejected:filled_slot")


def test_sector_path_never_issues_binding():
    """미해결 업종/종목 질문 경로는 pending_ask를 발행하지 않는다(현행 구조).

    planner 실패와 같은 이름으로 뭉개면 "고칠 대상이 planner"라고 오독하게 된다.
    """
    verdict = _gate(pending_ask=None, priority="sector_unresolved", chips_offered=[])
    assert verdict["gate"] == "path_without_binding"


def test_question_without_chips_cannot_bind():
    """칩 없는 자유 서술 질문은 결속 대상이 없다 — _pending_ask_payload가 None을 낸다."""
    verdict = _gate(question="어떤 조건으로 종목을 선택할까요?",
                    pending_ask=None, chips_offered=None)
    assert verdict["gate"] == "no_chips"


def test_all_chips_dropped_reports_the_dropped_text():
    """칩이 있었는데 전부 결속에 실패한 경우 — 어떤 문구가 탈락했는지가 수정 대상이다."""
    verdict = _gate(pending_ask=None,
                    chips_offered=["거래량 급감 시 매도", "박스권 이탈 시 매도"])
    assert verdict["gate"] == "chip_binding_failed"
    assert verdict["chips_dropped"] == ["거래량 급감 시 매도", "박스권 이탈 시 매도"]
    assert verdict["chips_bound"] == 0


def test_modify_lane_does_not_blame_the_planner():
    """수정 레인은 설계상 플래너를 돌리지 않는다 — 플래너 게이트를 적용하면 정상 동작이
    전부 planner_failed로 잡혀 Trace가 없는 원인을 가리킨다.

    [회귀 2026-08-01] Trace 실측에서 create 7턴만 게이트가 잡히고 modify 7턴이 공백이라
    수정 경로에 span을 붙였는데, 그때 planner_ran=False가 그대로 planner_failed로 읽혔다.
    """
    verdict = _gate(pending_ask=None, chips_offered=None, planner_ran=False,
                    priority="modify_unapplied", lane="modify")
    assert verdict["gate"] == "no_chips"
    assert verdict["lane"] == "modify"
    # 같은 입력이 파스 레인이면 플래너 실패로 읽히는 것이 맞다.
    assert _gate(pending_ask=None, chips_offered=None,
                 planner_ran=False)["gate"] == "planner_failed"


def test_partial_binding_still_counts_as_bound():
    """일부 칩만 결속돼도 질문↔답변 귀속은 성립한다 — 탈락 칩은 함께 남긴다."""
    verdict = _gate(
        chips_offered=["매월 리밸런싱", "거래량 급감 시 매도"],
        pending_ask={"topic": "리밸런싱", "chips": ["매월 리밸런싱"]},
    )
    assert verdict["gate"] == "ok"
    assert verdict["chips_dropped"] == ["거래량 급감 시 매도"]
