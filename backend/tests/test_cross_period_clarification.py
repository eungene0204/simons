"""이동평균 크로스 기간 옵션 되묻기 (2026-07-26 사용자 결정).

"골든크로스로 매수해줘"처럼 기간 미지정 크로스는 조용한 기본값 확정 대신 **옵션 칩과
함께 되묻는다**. completeness의 파라미터별 질문(단기/장기 각각)은 조건당 1개로 병합되고,
칩은 조건 전체를 담아 무상태 재전송이 가능하다("골든크로스(5일/20일) 발생 시 매수").
"""

from engine.nl_parser import ParsedStrategy
from strategy_conversation import primary
from strategy_conversation.interpreter.models import (
    ClarificationQuestion,
    StrategyIntent,
    ValidationReport,
)


def _cross_intent() -> StrategyIntent:
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY",
        "status": "NEEDS_CLARIFICATION",
        "confidence": 0.9,
        "strategy": {
            "universe": {"markets": ["KOSPI"], "sectors": []},
            "entry_conditions": [
                {"factor": "technical.ma_crossover", "operator": "crosses_above",
                 "parameters": {}, "source_text": "골든크로스로 매수"}
            ],
            "exit_conditions": [
                {"factor": "technical.ma_crossover", "operator": "crosses_below",
                 "parameters": {}, "source_text": "데드크로스로 매도"}
            ],
            "ranking": [],
            "portfolio": {"selection_count": 10, "rebalance_frequency": None},
            "risk_management": {"stop_loss": 15, "take_profit": 30},
            "backtest": {},
        },
    })


def _stub_interpreter(monkeypatch, intent: StrategyIntent):
    class _Result:
        pass

    _Result.intent = intent
    _Result.model_name = "test"
    _Result.prompt_version = "test"
    _Result.repair_attempts = 0
    _Result.latency_ms = 0.0
    _Result.unreflected_numbers = []

    class _Interpreter:
        def interpret(self, *_a, **_k):
            return _Result()

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interpreter())


# ── 병합 질문+옵션 칩 ─────────────────────────────────────────────────────────

def test_build_clarification_coalesces_cross_period_questions():
    intent = _cross_intent()
    report = ValidationReport(clarification_questions=[
        ClarificationQuestion(
            field=f"strategy.{path}_conditions[0].parameters.{param}",
            question=f"MA 크로스의 {param} 기간을 몇으로 할까요?",
        )
        for path in ("entry", "exit") for param in ("short_period", "long_period")
    ])
    question, chips, topic = primary._build_clarification(report, intent)
    # 크로스 기간 칩은 조건 칩이라 슬롯 topic이 붙지 않는다(확정 판정 대상 아님).
    assert topic is None
    # 파라미터별 4개 질문 → 역할별 1개 병합 질문 2줄
    assert question is not None
    assert question.count("이동평균 크로스의 기간") == 2
    assert "short" not in question and "단기 기간" not in question
    # 칩은 조건 전체를 담은 재전송 가능 표기 — 진입 3 + 청산 3
    assert chips == [
        "골든크로스(5일/20일) 발생 시 매수",
        "골든크로스(20일/60일) 발생 시 매수",
        "골든크로스(60일/120일) 발생 시 매수",
        "데드크로스(5일/20일) 발생 시 매도",
        "데드크로스(20일/60일) 발생 시 매도",
        "데드크로스(60일/120일) 발생 시 매도",
    ]


# ── 초기 파스: "골든크로스로 매수해줘" ────────────────────────────────────────

def test_initial_parse_asks_period_options_without_silent_confirm(monkeypatch):
    _stub_interpreter(monkeypatch, _cross_intent())
    result = primary.run_primary_parse("골든크로스로 매수해줘")
    assert result is not None
    # 신호는 표준값으로 실행 가능하게 유지하되(조건 소실 금지), 확정 대신 옵션을 묻는다
    sig = result["parsed"].entry_signals[0]
    assert (sig.short_period, sig.long_period) == (20, 60)
    assert "이동평균 크로스의 기간" in (result["clarification_question"] or "")
    assert "골든크로스(5일/20일) 발생 시 매수" in (result["clarification_suggestions"] or [])


# ── 수정: "데드크로스 청산 추가해줘" — 폴백 대신 구체 질문+칩 ─────────────────

def test_modify_incomplete_condition_returns_options_not_fallback(monkeypatch):
    prev = ParsedStrategy(
        description="PER 10 이하",
        fundamental_filters=[{"metric": "per", "operator": "<=", "value": 10}],
        rebalancing_period="monthly",
        max_positions=20,
        stop_loss_pct=8.0,
    )
    _stub_interpreter(monkeypatch, StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY",
        "confidence": 1.0,
        "patches": [{
            "op": "add", "path": "/exit_conditions/-",
            "value": {"factor": "technical.ma_crossover", "operator": "crosses_below",
                      "source_text": "데드크로스 청산"},
            "source_text": "데드크로스 청산",
        }],
    }))
    result = primary.run_primary_modification("데드크로스 청산 추가해줘", prev.model_dump())
    assert result is not None, "미확정 값은 폴백이 아니라 되묻기로 처리돼야 한다"
    assert result["interpreter"]["mode"] == "primary_modify_needs_value"
    # 전략은 무변경 유지, 질문은 청산 크로스 기간 옵션
    assert result["parsed"].model_dump()["exit_signals"] == []
    assert "매도(청산) 이동평균 크로스" in result["clarification_question"]
    assert "데드크로스(20일/60일) 발생 시 매도" in result["clarification_suggestions"]
