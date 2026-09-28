"""단계별 분할 매수 사다리(엔진 v16.36)와 분할 익절 끝값 정규화 — 엔진·대화 레인 계약.

2026-09-28 실측: "골든크로스 매수 → -15%에 최대 투자금의 10%, -25%에 25% 추가 매수 / +25%·+35%·+45%·+60%에
보유 수량의 10·20·30·40% 매도, +100%면 전량 매도" 전략이 '해석하지 못했어요'로 끝났다.
① 인터프리터가 '+100% 전량 매도'를 분할 익절 {profit 100, sell 100}으로 옮겼고, 분할 익절 스키마(매도 < 100%)에서
  조립이 ValidationError로 실패해 요청 전체가 해석 실패로 떨어졌다.
② '+5%·+15%에서는 계속 보유'가 값 없는 익절 단계로 들어가 엉뚱한 되묻기를 부를 자리였다.
③ 단계마다 폭·비중이 다른 추가 매수는 균등 사다리({count, step_pct})로 표현할 수 없어 미지원으로 빠졌다.
"""

import pandas as pd
import pytest

from engine import trade_reason as tr
from engine.simulator import Simulator
from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation

_CASH = 10_000_000.0
_OPTS = {"fees": 0.0, "slippage": 0.0, "execution_timing": "next_open"}


def _loop_frames(a_path):
    idx = pd.bdate_range("2024-01-01", periods=len(a_path))
    px = pd.DataFrame({"A": list(map(float, a_path))}, index=idx)
    ents = pd.DataFrame(False, index=idx, columns=["A"])
    ents.iloc[0, 0] = True
    exts = pd.DataFrame(False, index=idx, columns=["A"])
    return px, ents, exts


def _weight(pf, row):
    values = pf.asset_value(group_by=False).iloc[row]
    return float(values["A"]) / float(pf.value().iloc[row])


def test_ladder_buys_stated_shares_at_stated_drops():
    px, ents, exts = _loop_frames([100, 100, 85, 85, 75, 75])
    risk = {"max_positions": 1, "init_cash": _CASH, "entry_signal_driven": True,
            "entry_tranches": {"first_pct": 65, "levels": [{"drop_pct": 25, "size_pct": 25},
                                                           {"drop_pct": 15, "size_pct": 10}]}}
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, risk, _OPTS, low_df=px, high_df=px)
    assert _weight(pf, 0) == pytest.approx(0.65, abs=0.02)      # 첫 회차 = 목표 비중의 65%
    assert _weight(pf, 1) == pytest.approx(0.65, abs=0.02)      # -15% 전에는 추가 매수 없음
    assert sim.tranche_fills == 2
    assert _weight(pf, 5) > 0.95                                # 65 + 10 + 25 = 최대 포지션 완성
    reasons = [r for by in sim.entry_reason_overrides.values() for r in by.values()]
    assert any(tr.TRANCHE_BUY in r and "15" in r for r in reasons)
    assert any(tr.TRANCHE_BUY in r and "25" in r for r in reasons)


def test_ladder_second_step_waits_for_its_own_drop():
    px, ents, exts = _loop_frames([100, 100, 85, 85, 85, 85])       # -25%에는 닿지 않는다
    risk = {"max_positions": 1, "init_cash": _CASH, "entry_signal_driven": True,
            "entry_tranches": {"first_pct": 65, "levels": [{"drop_pct": 15, "size_pct": 10},
                                                           {"drop_pct": 25, "size_pct": 25}]}}
    sim = Simulator()
    sim.run(px, px, ents, exts, risk, _OPTS, low_df=px, high_df=px)
    assert sim.tranche_fills == 1


def test_uniform_tranches_keep_request_and_hash_shape():
    """균등 사다리 전략의 정본 DSL·엔진 요청에 levels가 새지 않는다(기존 전략 해시 불변)."""
    _, _, parsed, _, _ = _compile(_intent(backtest={"entry_tranches": {"count": 3, "step_percent": 5}}))
    assert to_canonical_strategy_dsl(parsed)["entry_tranches"] == {"count": 3, "step_pct": 5.0}
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["entry_tranches"] == {
        "count": 3, "step_pct": 5.0}


# ── 대화 레인 ────────────────────────────────────────────────────────────────

def _intent(**strategy_overrides):
    strategy = {
        "universe": {"markets": ["KOSPI"], "sectors": [], "symbols": []},
        "entry_conditions": [{"factor": "technical.ma_crossover", "operator": "crosses_above",
                              "parameters": {"short_period": 5, "long_period": 20}}],
        "exit_conditions": [],
        "portfolio": {"selection_count": 10},
        "risk_management": {},
        "backtest": {},
    }
    strategy.update(strategy_overrides)
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9, "strategy": strategy,
    })


def _compile(intent):
    validated, report = run_validation(intent)
    parsed, dropped, pending = compile_partial(validated, report, "")
    return validated, report, parsed, dropped, pending


def _reported_strategy():
    """2026-09-28 사용자 전략을 새 출력 형태로 옮긴 인터프리터 출력."""
    return _intent(
        risk_management={"partial_take_profits": [
            {"profit_percent": 5, "sell_percent": 0},
            {"profit_percent": 15, "sell_percent": 0},
            {"profit_percent": 25, "sell_percent": 10},
            {"profit_percent": 35, "sell_percent": 20},
            {"profit_percent": 45, "sell_percent": 30},
            {"profit_percent": 60, "sell_percent": 40},
            {"profit_percent": 100, "sell_percent": 100},
        ]},
        backtest={"entry_tranches": {"levels": [
            {"drop_percent": -5, "buy_percent": 0},
            {"drop_percent": -15, "buy_percent": 10},
            {"drop_percent": -25, "buy_percent": 25},
        ]}},
    )


def test_reported_strategy_compiles_and_reaches_engine():
    _, report, parsed, _, _ = _compile(_reported_strategy())
    assert not report.errors and not report.unsupported_features
    assert parsed.take_profit_pct == 100                         # '+100% 전량 매도' = 익절 청산
    assert [(p.profit_pct, p.sell_pct) for p in parsed.partial_take_profits] == [
        (25, 10), (35, 20), (45, 30), (60, 40)]                   # '계속 보유' 단계는 주문이 아니다
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["take_profit_pct"] == 100
    # 첫 매수 비중은 원문에 없다 — 추가 회차 합에서 65%를 역산하지 않고 묻는다(2026-09-28 '매번 물어봐 줘').
    assert risk["entry_tranches"] is None                            # 값 대기 = 미전송
    fields = {q.field for q in report.clarification_questions}
    assert "strategy.backtest.entry_tranches.first_percent" in fields
    assert not any("partial_take_profits" in f for f in fields)


def test_answered_first_share_completes_the_ladder():
    intent = _reported_strategy()
    intent.strategy.backtest.entry_tranches.first_percent = 65
    _, report, parsed, _, _ = _compile(intent)
    assert not any("entry_tranches" in q.field for q in report.clarification_questions)
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["entry_tranches"] == {
        "first_pct": 65.0, "levels": [{"drop_pct": 15.0, "size_pct": 10.0}, {"drop_pct": 25.0, "size_pct": 25.0}]}


def test_ladder_round_trips_through_decompile():
    _, _, parsed, _, _ = _compile(_reported_strategy())
    spec = decompile_strategy(parsed).backtest.entry_tranches
    assert [(lv.drop_percent, lv.buy_percent) for lv in spec.levels] == [(15, 10), (25, 25)]
    assert spec.first_percent is None


def test_full_sell_stage_keeps_earlier_take_profit():
    intent = _intent(risk_management={"take_profit": 50, "partial_take_profits": [
        {"profit_percent": 100, "sell_percent": 100}]})
    assert intent.strategy.risk_management.take_profit == 50
    assert intent.strategy.risk_management.partial_take_profits == []


def test_full_sell_stage_without_level_asks_instead_of_crashing():
    _, report, parsed, _, _ = _compile(_intent(risk_management={"partial_take_profits": [
        {"profit_percent": None, "sell_percent": 100}]}))
    assert any(q.field == "strategy.risk_management.partial_take_profits.0"
               for q in report.clarification_questions)
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["partial_take_profits"] is None


def test_ladder_missing_share_asks_and_is_not_sent():
    _, report, parsed, _, _ = _compile(_intent(backtest={"entry_tranches": {"levels": [
        {"drop_percent": 15, "buy_percent": None}]}}))
    assert any(q.field == "strategy.backtest.entry_tranches" for q in report.clarification_questions)
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["entry_tranches"] is None


@pytest.mark.parametrize("tranches", [
    {"levels": [{"drop_percent": 120, "buy_percent": 10}], "first_percent": 50},
    {"levels": [{"drop_percent": 15, "buy_percent": 150}], "first_percent": 50},
    {"levels": [{"drop_percent": 15, "buy_percent": 10}], "first_percent": 120},
])
def test_ladder_out_of_range_is_reported_and_dropped(tranches):
    from strategy_conversation.response.output_guard import guard_text

    _, report, parsed, _, _ = _compile(_intent(backtest={"entry_tranches": tranches}))
    errs = [e for e in report.errors if "추가 매수" in e]
    assert errs and all(guard_text(e) == e for e in errs)          # 규제 가드에 지워지지 않는 문구
    assert parsed.entry_tranches is None


def test_first_buy_plus_adds_may_exceed_full_position():
    """[회귀 2026-09-28] '100% 사자' — 첫 매수 100% + 추가 10%·25%(합 135%)를 거부해 같은 질문이 되풀이됐다.
    사용자가 정한 규칙이므로 받아들이고, 엔진은 추가 매수를 남은 현금 안에서만 체결한다."""
    intent = _reported_strategy()
    intent.strategy.backtest.entry_tranches.first_percent = 100
    _, report, parsed, _, _ = _compile(intent)
    assert not report.errors
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["entry_tranches"]["first_pct"] == 100.0


def test_ladder_add_on_beyond_allocation_uses_only_free_cash():
    """첫 매수 100%인 1종목 포트폴리오 — 추가 매수 조건에 닿아도 현금이 없으면 비중이 늘지 않는다(빚 없음)."""
    px, ents, exts = _loop_frames([100, 100, 85, 85, 75, 75])
    risk = {"max_positions": 1, "init_cash": _CASH, "entry_signal_driven": True,
            "entry_tranches": {"first_pct": 100, "levels": [{"drop_pct": 15, "size_pct": 10}]}}
    pf = Simulator().run(px, px, ents, exts, risk, _OPTS, low_df=px, high_df=px)
    assert float(pf.cash().min()) >= -1e-6
    assert _weight(pf, 5) <= 1.0 + 1e-9


# ── 출력 형태: risk_management.scale_in_buys (프롬프트 8.4) ────────────────────
# [회귀 2026-09-28] 사다리를 backtest.entry_tranches에 두었더니 120B가 '최대 투자금의 10% 추가 매수'를
# 분할 익절 옆 position_sizing(ATR)에 적어 분할 매수가 사라지고 ATR 위험 %를 되물었다. 자리를 분할
# 익절의 대칭 칸으로 옮기고, 검증기가 엔진 계약 자리(backtest.entry_tranches.levels)로 옮긴다.

def test_scale_in_buys_relocate_to_entry_tranches():
    intent = _intent(risk_management={"scale_in_buys": [
        {"drop_percent": -5, "buy_percent": 0},
        {"drop_percent": 15, "buy_percent": 10},
        {"drop_percent": 25, "buy_percent": 25},
    ]})
    tr = intent.strategy.backtest.entry_tranches
    assert [(lv.drop_percent, lv.buy_percent) for lv in tr.levels] == [(15, 10), (25, 25)]
    assert tr.first_percent is None and intent.strategy.risk_management.scale_in_buys == []
    _, report, parsed, _, _ = _compile(intent)
    assert not report.errors
    assert parsed.entry_tranches.first_pct is None                   # 역산하지 않는다


def test_scale_in_zero_drop_step_is_the_first_buy():
    """'처음에는 30%만 사고 -10%에 30% 추가' — 첫 매수 비중을 나머지(70%)로 지어내지 않는다."""
    intent = _intent(risk_management={"scale_in_buys": [
        {"drop_percent": 0, "buy_percent": 30}, {"drop_percent": 10, "buy_percent": 30}]})
    _, report, parsed, _, _ = _compile(intent)
    assert not report.errors
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["entry_tranches"] == {
        "first_pct": 30.0, "levels": [{"drop_pct": 10.0, "size_pct": 30.0}]}


@pytest.mark.parametrize("tranches", [
    {"levels": [{"drop_percent": 15, "buy_percent": 10}]},                        # 첫 매수 비중 미정
    {"levels": [{"drop_percent": 15, "buy_percent": None}], "first_percent": 50},  # 단계 값 미정
    {"count": 3},                                                                   # 균등 회차 미정
])
def test_tranche_questions_survive_the_regulatory_output_guard(tranches):
    """[회귀 2026-09-28] 질문 문구의 '분할 매수'를 규제 출력 가드가 매매 권유로 보고 문장째 지워, 첫 매수
    비중 질문이 사라지고 사다리가 조용히 엔진 요청에서 빠졌다."""
    from strategy_conversation.response.output_guard import guard_text

    _, report, _, _, _ = _compile(_intent(backtest={"entry_tranches": tranches}))
    questions = [q.question for q in report.clarification_questions if "entry_tranches" in (q.field or "")]
    assert questions
    for q in questions:
        assert guard_text(q) == q


# ── 수정 턴: 초안 모양 = 프롬프트 모양 ─────────────────────────────────────────
# [회귀 2026-09-28] 첫 매수 비중 되묻기에 "첫 매수는 50%"라고 답했는데, 수정 LLM이 초안의 엔진 자리
# (backtest.entry_tranches)와 프롬프트의 자리(risk_management.scale_in_buys)가 달라 `/position_sizing`
# 칸을 지어냈고 패치가 버려져 답이 조용히 사라졌다.

def test_modify_draft_shows_ladder_in_prompt_shape_and_patches_round_trip():
    from strategy_conversation.conversation.patch_applier import apply_patches
    from strategy_conversation.interpreter.models import PatchOp, scale_in_view

    spec = _reported_strategy().strategy
    view = scale_in_view(spec.model_dump())
    assert [(lv["drop_percent"], lv["buy_percent"]) for lv in view["risk_management"]["scale_in_buys"]] == [
        (15, 10), (25, 25)]
    assert view["backtest"]["entry_tranches"]["levels"] == []

    for patch in (
        PatchOp(op="replace", path="/backtest/entry_tranches/first_percent", value=50),
        PatchOp(op="add", path="/risk_management/scale_in_buys/-", value={"drop_percent": 0, "buy_percent": 50}),
    ):
        patched = apply_patches(spec, [patch])
        tr = patched.backtest.entry_tranches
        assert tr.first_percent == 50
        assert [(lv.drop_percent, lv.buy_percent) for lv in tr.levels] == [(15, 10), (25, 25)]
        assert patched.risk_management.scale_in_buys == []

    # 기존 단계 값 수정도 보이는 경로(scale_in_buys/0)로 맞는다.
    patched = apply_patches(spec, [PatchOp(op="replace", path="/risk_management/scale_in_buys/0/buy_percent", value=20)])
    assert [(lv.drop_percent, lv.buy_percent) for lv in patched.backtest.entry_tranches.levels] == [(15, 20), (25, 25)]


# ── 첫 매수 비중 답변 전용 판정 ───────────────────────────────────────────────
# [회귀 2026-09-28] 일반 수정 LLM이 "첫 매수는 50%"를 `/position_sizing`·`/portfolio/selection_count=5`로
# 지어내 답이 조용히 사라졌다(2/2). 질문 문장 동일성으로 받고, 값 옮겨 적기만 LLM이 한다.

def test_first_buy_answer_is_routed_by_our_question_text(monkeypatch):
    from strategy_conversation import primary
    from strategy_conversation.conversation.patch_applier import apply_patches
    from strategy_conversation.validation.completeness_validator import FIRST_BUY_QUESTION

    class _Interp:
        model_name = "stub"

        def _chat(self, system, _user, **_kw):
            assert "첫 매수" in system
            return '{"percent": 50}'

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interp())
    spec = _reported_strategy().strategy
    result = primary._first_buy_answer_result(spec, "첫 매수는 50%", FIRST_BUY_QUESTION[0])
    assert [(p.path, p.value) for p in result.intent.patches] == [("/backtest/entry_tranches/first_percent", 50.0)]
    patched = apply_patches(spec, result.intent.patches)
    assert patched.backtest.entry_tranches.first_percent == 50
    assert [(lv.drop_percent, lv.buy_percent) for lv in patched.backtest.entry_tranches.levels] == [(15, 10), (25, 25)]
    # 다른 질문의 답이면 일반 레인
    assert primary._first_buy_answer_result(spec, "50%", "손절 기준을 몇 %로 할까요?") is None


@pytest.mark.parametrize("raw,expected", [
    ('{"percent": 65}', {"first_percent": 65.0}),
    ('{"percent": null}', {}),                 # 값을 말하지 않음
    ('{"percent": 150}', {}),                  # 범위 밖은 옮기지 않는다
    ('not json', None),                        # 실패 = 판정 없음
])
def test_first_buy_answer_transcription(raw, expected):
    from strategy_conversation.interpreter.tranche_check import check_first_buy_answer

    assert check_first_buy_answer("첫 매수 65%", lambda *_a, **_k: raw) == expected


# ── 진행 게이트: 첫 매수 비중이 비면 골격 질문보다 먼저, 우선순위 마커와 함께 묻는다 ──────────
# [회귀 2026-09-28] 1턴 질문에 우선순위 마커가 없어 프론트 게이트의 골격 질문(최대 보유·리밸런싱·…)이
# 삼켰고, 골격이 다 찬 뒤에도 아무도 다시 묻지 않아 카드에 '첫 회차 비중 미정'만 남았다.

def _gate_result(**fields):
    import time

    import main
    from engine.nl_parser import ParsedStrategy

    parsed = ParsedStrategy(description="x", universe=["KOSPI"],
                            entry_signals=[{"indicator": "ma_crossover", "signal_type": "buy",
                                            "short_period": 5, "long_period": 20}], **fields)
    return main._build_parse_result(
        main.NLParseRequest(prompt="리밸런싱 안 함", backend="ollama"), "rule", parsed, None,
        load_ms=0.0, parse_ms=0.0, request_started=time.perf_counter(),
    )


def test_gate_asks_first_buy_before_skeleton_with_priority():
    from engine.strategy_slots import FIRST_BUY_QUESTION
    from strategy_conversation.response.output_guard import guard_text

    result = _gate_result(entry_tranches={"levels": [{"drop_pct": 15, "size_pct": 10}]}, take_profit_pct=100)
    assert result["clarification_question"] == FIRST_BUY_QUESTION[0]
    assert result["clarification_priority"] == "pending_values"      # 프론트 게이트가 삼키지 않게
    assert not result["clarification_suggestions"]                    # 추천값 없이
    assert guard_text(FIRST_BUY_QUESTION[0]) == FIRST_BUY_QUESTION[0]


def test_gate_does_not_ask_first_buy_once_answered():
    from engine.strategy_slots import FIRST_BUY_QUESTION

    result = _gate_result(entry_tranches={"levels": [{"drop_pct": 15, "size_pct": 10}], "first_pct": 50},
                          take_profit_pct=100)
    assert result["clarification_question"] != FIRST_BUY_QUESTION[0]
