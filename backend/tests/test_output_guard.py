"""출력 관문(Phase 2) 계약 — Responder 직전 결정론 규제 가드.

핵심: 위반 문장(시스템이 추천·전망·보장을 **하는** 문장)만 제거하고,
추천 기능을 거절·안내하는 문장과 면책 문구는 보존한다. 위반 없는 텍스트는
원문 그대로(개행 포함 무변형).
"""

from strategy_conversation.response.output_guard import finalize_user_response, guard_text


# ── guard_text: 위반 문장 제거 ────────────────────────────────────────────────

def test_recommendation_sentence_dropped_neighbor_kept():
    text = "손절은 10%로 설정됐어요. 이 전략을 추천합니다."
    assert guard_text(text) == "손절은 10%로 설정됐어요."


def test_market_forecast_dropped():
    text = "반도체 업종이 상승할 가능성이 높습니다. 과거 CAGR은 12.4%였습니다."
    assert guard_text(text) == "과거 CAGR은 12.4%였습니다."


def test_superiority_judgement_dropped():
    assert guard_text("전략 A가 더 우수합니다.") == ""


def test_stock_action_directive_dropped_via_shared_guard():
    # 종목 행동 지시는 stock_analysis 가드 정본을 공유한다
    text = "지금 매수하세요. 총 53회의 거래가 발생했습니다."
    assert guard_text(text) == "총 53회의 거래가 발생했습니다."


# ── 보존 계약: 거절 안내·면책·정상 응답 ──────────────────────────────────────

def test_refusal_notice_mentioning_recommendation_kept():
    text = "'종목 추천' 조건은 현재 지원되지 않아 전략에 반영되지 않았어요."
    assert guard_text(text) == text


def test_disclaimer_negated_guarantee_kept():
    text = "결과는 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다."
    assert guard_text(text) == text


def test_clean_multiline_text_unmodified():
    # 위반 없으면 개행·서식까지 원문 그대로 — 관문이 정상 응답을 변형하면 회귀다
    text = "손절 기준은 몇 %로 할까요?\n익절 기준은 몇 %로 할까요?"
    assert guard_text(text) is text


def test_none_and_empty_passthrough():
    assert guard_text(None) is None
    assert guard_text("") == ""


def test_violation_removes_line_but_keeps_other_lines():
    text = "리밸런싱은 월간이에요.\n가치 전략이 유리합니다.\n손절은 8%예요."
    assert guard_text(text) == "리밸런싱은 월간이에요.\n손절은 8%예요."


# ── finalize_user_response: 응답 필드 관문 ────────────────────────────────────

def _result(**overrides):
    base = {
        "parsed": object(),
        "clarification_question": None,
        "clarification_suggestions": None,
        "notices": [],
        "interpreter": {"mode": "primary"},
    }
    base.update(overrides)
    return base


def test_finalize_filters_notices():
    out = finalize_user_response(_result(notices=[
        "손절 하한선을 1%로 보정했어요.",
        "이 전략은 높은 성과가 기대됩니다.",
    ]))
    assert out["notices"] == ["손절 하한선을 1%로 보정했어요."]


def test_finalize_question_fully_dropped_also_drops_chips():
    out = finalize_user_response(_result(
        clarification_question="배당 전략 사용을 권장합니다.",
        clarification_suggestions=["배당수익률 3% 이상"],
    ))
    assert out["clarification_question"] is None
    assert out["clarification_suggestions"] is None


def test_finalize_clean_question_and_chips_kept():
    out = finalize_user_response(_result(
        clarification_question="손절 기준은 몇 %로 할까요?",
        clarification_suggestions=["손절 8%", "손절 10%"],
    ))
    assert out["clarification_question"] == "손절 기준은 몇 %로 할까요?"
    assert out["clarification_suggestions"] == ["손절 8%", "손절 10%"]


def test_finalize_preserves_parsed_and_meta():
    parsed = object()
    out = finalize_user_response(_result(parsed=parsed))
    assert out["parsed"] is parsed
    assert out["interpreter"] == {"mode": "primary"}
