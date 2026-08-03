"""칩 답변 결정론 귀속(run_chip_answer, Phase 4 후속 ①) 계약 테스트.

핵심 계약:
- 입력이 직전 planner ask(pending_ask 에코)의 칩과 정확히 일치할 때만 발동한다 —
  자유 서술은 §4(답변 강제 귀속 금지)에 따라 인터프리터가 State 변경을 판정한다.
- 발동 시 수정 인터프리터 LLM을 호출하지 않고 결정적 추출로 State에 반영한다.
- 결정적으로 적용되지 않는 칩은 None으로 기존 경로 폴백(자기완결 계약 안전망).
- pending_ask는 사용자가 실제로 본 질문·칩과 항상 일치한다(finalize 동기화).
"""

from __future__ import annotations

import pytest

from engine.nl_parser import ParsedStrategy
from strategy_conversation import primary as primary_mod
from strategy_conversation.primary import (
    _pending_ask_payload,
    run_chip_answer,
)
from strategy_conversation.response.output_guard import finalize_user_response


def _etf_strategy() -> dict:
    return ParsedStrategy(
        description="반도체 etf 골든크로스 전략",
        universe=["ETF"],
        etf_theme="반도체",
        entry_signals=[{
            "indicator": "ma_crossover", "signal_type": "buy",
            "short_period": 5, "long_period": 20,
        }],
    ).model_dump()


def _pending_ask(chips, topic="리스크관리"):
    return {"topic": topic, "question": "손절·익절 기준을 정할까요?", "chips": chips}


@pytest.fixture(autouse=True)
def _no_interpreter(monkeypatch):
    """칩 레인은 인터프리터를 절대 호출하지 않는다 — 호출되면 즉시 실패."""
    def _fail(*args, **kwargs):
        raise AssertionError("칩 결정론 레인이 인터프리터를 호출했다")

    monkeypatch.setattr(primary_mod, "_get_interpreter", _fail)


def test_exact_chip_click_applies_without_llm():
    prev = _etf_strategy()
    result = run_chip_answer("손절 8%", prev, _pending_ask(["손절 8%", "익절 20%"]))
    assert result is not None
    assert result["parsed"].stop_loss_pct == 8.0
    assert result["interpreter"]["mode"] == "primary_chip_answer"
    assert result["interpreter"]["llm_latency_ms"] == 0
    # 기존 전략 필드는 유지된다(부분 병합 — 전체 초기화 금지)
    assert result["parsed"].universe == ["ETF"]
    assert result["parsed"].etf_theme == "반도체"
    assert len(result["parsed"].entry_signals) == 1


def test_signed_risk_chip_binds_to_magnitude():
    """손절·트레일링 칩은 마이너스로 표기하지만(FR-STR-030b) 적용 값은 크기다."""
    prev = _etf_strategy()
    result = run_chip_answer("손절 -8%", prev, _pending_ask(["손절 -8%"]))
    assert result is not None and result["parsed"].stop_loss_pct == 8.0

    result = run_chip_answer(
        "트레일링 스탑 -10%", prev, _pending_ask(["트레일링 스탑 -10%"]),
    )
    assert result is not None and result["parsed"].trailing_stop_pct == 10.0


def test_chip_click_with_whitespace_still_matches():
    prev = _etf_strategy()
    result = run_chip_answer("  손절 8%  ", prev, _pending_ask(["손절 8%"]))
    assert result is not None and result["parsed"].stop_loss_pct == 8.0


def test_free_text_answer_falls_through_to_interpreter_path():
    """칩과 다른 자유 서술은 None — 강제 귀속하지 않는다(§4)."""
    prev = _etf_strategy()
    assert run_chip_answer(
        "손절은 10프로 정도로 하고 싶어", prev, _pending_ask(["손절 8%"])
    ) is None


def test_chip_without_deterministic_extraction_falls_through():
    """결정적 추출이 무변경인 칩(서술형)은 None — 인터프리터가 처리한다(안전망)."""
    prev = _etf_strategy()
    assert run_chip_answer(
        "직접 입력할게요", prev, _pending_ask(["직접 입력할게요"])
    ) is None


def test_missing_context_falls_through():
    prev = _etf_strategy()
    assert run_chip_answer("손절 8%", prev, None) is None
    assert run_chip_answer("손절 8%", None, _pending_ask(["손절 8%"])) is None
    assert run_chip_answer("손절 8%", prev, {"topic": "리스크관리"}) is None  # chips 없음


def test_technical_signal_chip_applies_deterministically():
    """자기완결 기술 지표 칩도 결정적 추출로 반영된다(정본 표기 파싱)."""
    prev = _etf_strategy()
    result = run_chip_answer(
        "데드크로스(5일/20일) 발생 시 매도", prev,
        _pending_ask(["데드크로스(5일/20일) 발생 시 매도"], topic="매도조건"),
    )
    assert result is not None
    assert any(s.get("indicator") == "ma_crossover"
               for s in result["parsed"].model_dump()["exit_signals"])


def test_replan_emits_next_pending_ask(monkeypatch):
    """칩 반영 후 남은 골격 공백이 있으면 planner 재계획 질문+다음 pending_ask를 낸다."""
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.setattr(
        primary_mod, "_dag_planner_clarification",
        lambda user_input, parsed, explicit_fields=None: (
            "어떤 조건에서 매도할까요?", ["데드크로스(5일/20일) 발생 시 매도"], "매도조건",
        ),
    )
    prev = _etf_strategy()
    result = run_chip_answer("손절 8%", prev, _pending_ask(["손절 8%"]))
    assert result is not None
    assert result["clarification_question"] == "어떤 조건에서 매도할까요?"
    assert result["clarification_priority"] == "dag_planner"
    assert result["pending_ask"]["topic"] == "매도조건"
    assert result["pending_ask"]["question"] == "어떤 조건에서 매도할까요?"
    # 재계획 질문의 칩도 planner 문구가 아니라 슬롯 SOT 정본이다(2026-08-02 사용자 결정).
    from engine import strategy_slots
    assert result["pending_ask"]["chips"] == strategy_slots.suggestions_for_topic("매도조건")
    # 칩=값 결속 계약 — 다음 턴의 클릭이 재해석 없이 쓸 값이 함께 실린다.
    binding = result["pending_ask"]["chip_bindings"]["데드크로스(5일/20일) 발생 시 매도"]
    assert binding["exit_signals"][0]["indicator"] == "ma_crossover"


def test_replan_off_mode_returns_no_question(monkeypatch):
    monkeypatch.delenv("STRATEGY_DAG_PLANNER_MODE", raising=False)
    prev = _etf_strategy()
    result = run_chip_answer("손절 8%", prev, _pending_ask(["손절 8%"]))
    assert result is not None
    assert result["clarification_question"] is None
    assert result["pending_ask"] is None


def test_pending_ask_payload_requires_question_and_chips():
    assert _pending_ask_payload(None, ["칩"], "매수조건") is None
    assert _pending_ask_payload("질문?", None, "매수조건") is None
    assert _pending_ask_payload("질문?", ["칩"], "매수조건") == {
        "topic": "매수조건", "question": "질문?", "chips": ["칩"],
    }


def test_finalize_syncs_pending_ask_with_guarded_question():
    """가드가 질문을 제거하면 pending_ask도 함께 지워진다 — 사용자가 본 것과 불일치 금지."""
    result = finalize_user_response({
        "parsed": None,
        "clarification_question": None,
        "clarification_suggestions": ["손절 8%"],
        "pending_ask": {"topic": "리스크관리", "question": "x", "chips": ["손절 8%"]},
        "notices": [],
    })
    assert result["pending_ask"] is None

    result = finalize_user_response({
        "parsed": None,
        "clarification_question": "손절 기준을 정할까요?",
        "clarification_suggestions": ["손절 8%"],
        "pending_ask": {"topic": "리스크관리", "question": "손절 기준을 정할까요?",
                        "chips": ["손절 8%"]},
        "notices": [],
    })
    assert result["pending_ask"] == {
        "topic": "리스크관리", "question": "손절 기준을 정할까요?", "chips": ["손절 8%"],
    }


def test_cache_key_varies_with_pending_ask():
    """같은 프롬프트라도 pending_ask 컨텍스트가 다르면 캐시 키가 달라야 한다."""
    from nl_cache import nl_cache_key

    prev = _etf_strategy()
    base = nl_cache_key("손절 8%", "ollama", None, prev)
    with_ask = nl_cache_key("손절 8%", "ollama", None, prev,
                            _pending_ask(["손절 8%"]))
    assert base != with_ask


# ─── 칩=값 결속 계약(2026-07-29 '거래량 급감' 사고) ──────────────────────────────
# 칩은 우리 agent가 만들어 보여준 열거형 선택지다 — 값은 보여주는 순간 이미 알고
# 있어야 하고, 클릭은 그 값을 꺼내 쓰는 행위여야 한다. 값이 결속되지 않는 칩은
# 엔진이 표현할 수 없는 조건이므로 애초에 노출되지 않는다.


def test_unbindable_chip_is_not_emitted():
    """엔진이 표현할 수 없는 칩(거래량 급감)은 발행 단계에서 탈락한다."""
    prev = ParsedStrategy.model_validate(_etf_strategy())
    payload = _pending_ask_payload(
        "언제 팔까요?",
        ["데드크로스(5일/20일) 발생 시 매도", "거래량 급감(전일 대비 1/2 이하) 시 매도"],
        "매도 조건",
        prev,
    )
    assert payload is not None
    assert payload["chips"] == ["데드크로스(5일/20일) 발생 시 매도"]
    assert "거래량 급감(전일 대비 1/2 이하) 시 매도" not in payload["chip_bindings"]


def test_partially_bindable_chip_with_unsupported_concept_is_not_emitted():
    """미지원 개념(거래량 배수)을 언급하는 칩은 부분 결속에 성공해도 탈락한다.

    2026-08-02 사고: '거래량 급증(전일 대비 3배) 시 매수'가 '거래량 급증'만
    volume_spike로 결속돼 노출됐고, 배수 조건은 조용히 소실됐다 — 클릭하면
    미지원 안내로 끝나는 칩을 애초에 내보내지 않는다."""
    prev = ParsedStrategy.model_validate(_etf_strategy())
    payload = _pending_ask_payload(
        "어떤 조건에서 매수할까요?",
        ["RSI 30 이하에서 매수", "거래량 급증(전일 대비 3배) 시 매수"],
        "매수 조건",
        prev,
    )
    assert payload is not None
    assert payload["chips"] == ["RSI 30 이하에서 매수"]
    assert "거래량 급증(전일 대비 3배) 시 매수" not in payload["chip_bindings"]


def test_plain_volume_spike_chip_still_binds():
    """배수 없는 '거래량 급증 시 매수'는 지원 개념이므로 결속·노출된다."""
    prev = ParsedStrategy.model_validate(_etf_strategy())
    payload = _pending_ask_payload(
        "어떤 조건에서 매수할까요?", ["거래량 급증 시 매수"], "매수 조건", prev,
    )
    assert payload is not None
    assert payload["chips"] == ["거래량 급증 시 매수"]
    binding = payload["chip_bindings"]["거래량 급증 시 매수"]
    assert any(
        signal.get("indicator") == "volume_spike"
        for signal in binding.get("entry_signals", [])
    )


def test_all_chips_unbindable_drops_the_chip_list():
    """전부 결속 실패면 pending_ask 자체를 내지 않는다(질문만 남고 자유 서술로)."""
    prev = ParsedStrategy.model_validate(_etf_strategy())
    assert _pending_ask_payload(
        "언제 팔까요?", ["거래량 급감(전일 대비 1/2 이하) 시 매도"], "매도 조건", prev,
    ) is None


def test_description_only_change_is_not_an_applied_chip():
    """description만 달라진 칩은 '반영'이 아니다 — 무변경을 확정으로 오보고하지 않는다."""
    prev = _etf_strategy()
    ask = _pending_ask(["거래량 급감(전일 대비 1/2 이하) 시 매도"], topic="매도 조건")
    assert run_chip_answer("거래량 급감(전일 대비 1/2 이하) 시 매도", prev, ask) is None


def test_click_applies_stored_binding_without_reinterpreting_the_label():
    """클릭은 발행 때 결속한 값을 그대로 쓴다 — 칩 문구 재추출을 거치지 않는다."""
    prev = _etf_strategy()
    ask = {
        "topic": "매도 조건", "question": "언제 팔까요?",
        "chips": ["데드크로스(5일/20일) 발생 시 매도"],
        "chip_bindings": {
            "데드크로스(5일/20일) 발생 시 매도": {
                "exit_signals": [{
                    "indicator": "ma_crossover", "signal_type": "sell",
                    "short_period": 5, "long_period": 20,
                }],
            },
        },
    }

    def _fail(*args, **kwargs):
        raise AssertionError("결속된 칩이 문구 재추출을 호출했다")

    import engine.nl_parser as nl_parser_mod
    original = nl_parser_mod._apply_prompt_overrides
    nl_parser_mod._apply_prompt_overrides = _fail
    try:
        result = run_chip_answer("데드크로스(5일/20일) 발생 시 매도", prev, ask)
    finally:
        nl_parser_mod._apply_prompt_overrides = original
    assert result is not None
    assert result["parsed"].exit_signals[0].indicator == "ma_crossover"
    assert result["parsed"].exit_signals[0].long_period == 20


# ── 확정 칩(§ 7 CONFIRM) ────────────────────────────────────────────────────────
# 값이 안 바뀌는 칩에는 두 종류가 섞여 있다: 표현할 수 없는 칩(탈락)과 이미 물질화된
# 기본값을 그대로 가리키는 칩(확정). 후자를 함께 떨어뜨리면 우리가 물어놓고 화면에
# 보여준 값을 사용자가 선택할 방법이 사라진다.


def _blank_strategy() -> ParsedStrategy:
    return ParsedStrategy.model_validate({"description": "테스트 전략"})


@pytest.mark.parametrize(
    "topic,chips,default_chip,field",
    [
        ("최대 보유", ["최대 5종목", "최대 10종목", "최대 20종목"], "최대 10종목", "max_positions"),
        ("초기 자본", ["500만원", "1,000만원", "3,000만원"], "1,000만원", "initial_capital"),
        ("백테스트 기간", ["최근 1년 데이터", "최근 5년 데이터"], "최근 5년 데이터",
         "backtest_period"),
    ],
)
def test_default_valued_chip_is_offered_as_a_confirm_chip(topic, chips, default_chip, field):
    """현재값과 같은 칩은 탈락이 아니라 확정 칩으로 노출된다."""
    payload = _pending_ask_payload("?", chips, topic, _blank_strategy())
    assert payload is not None
    assert default_chip in payload["chips"]
    assert payload["chip_confirms"] == {default_chip: field}
    # 값 결속과 섞이지 않는다 — 섞이면 무변경 패치가 되어 '반영 없음'으로 떨어진다.
    assert default_chip not in payload["chip_bindings"]


def test_confirm_chip_click_keeps_the_value_and_promotes_provenance():
    """확정 칩 클릭은 값을 바꾸지 않고 상태만 올린다(PROVISIONAL → CONFIRMED)."""
    prev = _blank_strategy()
    ask = _pending_ask_payload(
        "몇 종목?", ["최대 5종목", "최대 10종목"], "최대 보유", prev)
    result = run_chip_answer(
        "최대 10종목", prev.model_dump(), ask, previous_explicit_fields=["universe"])
    assert result is not None
    assert result["interpreter"]["mode"] == "primary_chip_confirm"
    assert result["parsed"].max_positions == prev.max_positions
    assert result["explicit_fields"] == ["universe", "max_positions"]


def test_inexpressible_chip_is_still_dropped_under_a_confirmable_topic():
    """확정 가능한 topic이어도 그 필드를 정하지 못하는 칩은 확정이 아니다.

    '패치가 비었으니 topic의 확정'으로 추정하면 아무 뜻도 결속되지 않은 칩이 사용자
    확정으로 둔갑해 되묻기를 삼킨다(말하지 않은 값 확정 금지).
    """
    payload = _pending_ask_payload(
        "몇 종목?", ["최대 5종목", "거래량 급감(전일 대비 1/2 이하) 시 매도"],
        "최대 보유", _blank_strategy(),
    )
    assert payload is not None
    assert payload["chips"] == ["최대 5종목"]
    assert not payload.get("chip_confirms")


def test_confirm_chips_survive_the_output_guard():
    """가드가 pending_ask를 재구성해도 확정 채널이 사라지지 않는다."""
    prev = _blank_strategy()
    ask = _pending_ask_payload(
        "몇 종목?", ["최대 5종목", "최대 10종목"], "최대 보유", prev)
    finalized = finalize_user_response({
        "clarification_question": ask["question"],
        "clarification_suggestions": list(ask["chips"]),
        "pending_ask": ask,
    })
    assert finalized["pending_ask"]["chip_confirms"] == {"최대 10종목": "max_positions"}


def test_unknown_topic_cannot_confirm():
    """직전 질문이 확정 가능 슬롯을 가리키지 않으면 확정 대상이 없다."""
    from engine.strategy_slots import confirmable_field_for_topic

    assert confirmable_field_for_topic(None) is None
    assert confirmable_field_for_topic("매수 조건") is None
    assert confirmable_field_for_topic("유니버스") is None
    # planner가 라벨을 늘려 써도 정본 라벨에 맞춘다(표기 정규화).
    assert confirmable_field_for_topic("최대 보유 종목 수") == "max_positions"


# ── 이월 질문 큐(한 턴에 한 질문, 2026-08-03 사용자 결정) ─────────────────────

def _value_strategy() -> dict:
    return ParsedStrategy(description="당기순이익과 영업이익률이 높은 종목",
                          universe=["KOSPI"]).model_dump()


def _queued_ask():
    return {
        "topic": None,
        "question": "진입 조건의 순이익증가율 기준값을 얼마로 할까요?",
        "chips": ["순이익증가율 10% 이상"],
        "chip_bindings": {"순이익증가율 10% 이상": {"fundamental_filters": [
            {"metric": "net_income_growth", "operator": ">=", "value": 10.0}]}},
        "queue": [
            {"question": "진입 조건의 영업이익률 기준값을 얼마로 할까요?",
             "chips": ["영업이익률 10% 이상"], "topic": None, "metric": "operating_margin"},
        ],
    }


def test_chip_answer_surfaces_next_queued_question():
    """[2026-08-03 사용자 결정] 기준값 3개를 한 버블에 묶지 않는다 — 칩으로 답하면
    재계획 대신 큐의 다음 질문(영업이익률 기준값)이 새 결속과 함께 나간다."""
    result = run_chip_answer("순이익증가율 10% 이상", _value_strategy(), _queued_ask())
    assert result is not None
    assert [(f.metric, f.value) for f in result["parsed"].fundamental_filters] == [
        ("net_income_growth", 10.0)]
    assert "영업이익률" in result["clarification_question"]
    assert result["clarification_suggestions"] == ["영업이익률 10% 이상"]
    assert result["clarification_priority"] == "pending_values"
    next_ask = result["pending_ask"]
    assert "영업이익률 10% 이상" in next_ask["chip_bindings"]
    assert "queue" not in next_ask  # 남은 큐가 없으면 싣지 않는다


def test_queued_question_skipped_when_already_answered():
    """큐보다 앞서 자유 서술로 이미 반영된 조건은 재질문하지 않는다."""
    prev = ParsedStrategy(
        description="t", universe=["KOSPI"],
        fundamental_filters=[{"metric": "operating_margin", "operator": ">=", "value": 12.0}],
    ).model_dump()
    ask = _queued_ask()
    # 실제 결속값(_bind_chips)은 기존 목록에 새 조건을 병합해 싣는다(목록형 소실 방지)
    ask["chip_bindings"]["순이익증가율 10% 이상"] = {"fundamental_filters": [
        {"metric": "operating_margin", "operator": ">=", "value": 12.0},
        {"metric": "net_income_growth", "operator": ">=", "value": 10.0}]}
    ask["queue"] = [
        {"question": "진입 조건의 영업이익률 기준값을 얼마로 할까요?",
         "chips": ["영업이익률 10% 이상"], "topic": None, "metric": "operating_margin"},
        {"question": "청산 규칙이 없습니다. 어떻게 매도할까요?",
         "chips": ["20일 보유 후 청산"], "topic": "매도 조건", "metric": None},
    ]
    result = run_chip_answer("순이익증가율 10% 이상", prev, ask)
    assert result is not None
    # 영업이익률은 이미 12%로 반영돼 있다 — 건너뛰고 청산 질문이 나간다
    assert "청산" in result["clarification_question"]
    assert "영업이익률" not in result["clarification_question"]
