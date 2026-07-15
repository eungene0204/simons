"""condition_builder(재무 조건 스택 빌더) 유닛 테스트.

핵심 계약: Pending Condition 상태 관리(슬롯이 비면 완료 차단) + 추천→선택→직접입력 흐름.
"""

import pytest

from intent import condition_builder as cb
from intent.condition_builder import Condition, ConditionState, step


# ─── 지표 인식 ────────────────────────────────────────────────────────────────────

def test_detect_metric_basic():
    assert cb.detect_metric("PER도 넣자") == "per"
    assert cb.detect_metric("PBR 추가") == "pbr"
    assert cb.detect_metric("영업이익률도 보면 좋겠네") == "operating_margin"
    assert cb.detect_metric("ROE 조건") == "roe_or_gpa"
    assert cb.detect_metric("배당수익률도 넣자") == "dividend_yield"


def test_detect_metric_disambiguation_order():
    # 더 구체적인 별칭이 배당수익률/영업이익률보다 먼저 잡혀야 한다.
    assert cb.detect_metric("배당성향 30% 이상") == "payout_rate"
    assert cb.detect_metric("배당성장률 10%") == "dividend_growth"
    assert cb.detect_metric("배당") == "dividend_yield"
    assert cb.detect_metric("영업이익증가율 20%") == "operating_income_growth"
    assert cb.detect_metric("영업이익률 15%") == "operating_margin"


def test_detect_metric_none():
    assert cb.detect_metric("안녕하세요") is None
    assert cb.detect_metric("10종목 보유") is None


# ─── 추천 → 선택 흐름 ─────────────────────────────────────────────────────────────

def test_add_metric_shows_recommendation_chips():
    r = step(ConditionState(), "영업이익률도 넣자")
    assert r.status == "collecting"
    assert r.state.awaiting == "choice"
    # 추천 칩 + '직접 입력' 마지막
    assert r.suggestions == ["5% 이상", "10% 이상", "15% 이상", "20% 이상", "직접 입력"]
    # Pending(미완성) 상태 — 전략 완료 불가
    assert cb.build_parsed_strategy(r.state) is None


def test_select_recommendation_completes_condition():
    r1 = step(ConditionState(), "영업이익률")
    r2 = step(r1.state, "15% 이상")
    assert r2.status == "collecting"
    done = [c for c in r2.state.conditions if c.complete]
    assert len(done) == 1
    assert done[0].metric == "operating_margin"
    assert done[0].operator == ">="
    assert done[0].value == 15.0
    assert r2.state.awaiting is None


def test_per_recommendation_uses_le_direction():
    r1 = step(ConditionState(), "PER도 넣자")
    assert r1.suggestions == ["10배 이하", "15배 이하", "20배 이하", "25배 이하", "직접 입력"]
    r2 = step(r1.state, "15 이하")
    c = r2.state.conditions[-1]
    assert (c.metric, c.operator, c.value) == ("per", "<=", 15.0)


# ─── 직접 입력 흐름 ────────────────────────────────────────────────────────────────

def test_direct_input_flow():
    r1 = step(ConditionState(), "ROE 넣자")
    r2 = step(r1.state, "직접 입력")
    assert r2.state.awaiting == "value"
    assert r2.suggestions == []
    assert "몇" in r2.reply
    r3 = step(r2.state, "18")
    c = r3.state.conditions[-1]
    assert (c.metric, c.operator, c.value) == ("roe_or_gpa", ">=", 18.0)


def test_direct_input_honors_explicit_operator():
    r1 = step(ConditionState(), "시가총액 조건")
    r2 = step(r1.state, "직접 입력")
    r3 = step(r2.state, "5000억 이하")  # 관례는 이상이지만 사용자가 이하로 지정
    c = r3.state.conditions[-1]
    assert (c.metric, c.operator, c.value) == ("market_cap", "<=", 5000.0)


# ─── 인라인 완료 ──────────────────────────────────────────────────────────────────

def test_inline_value_completes_immediately():
    r = step(ConditionState(), "PER 10 이하도 넣어")
    assert r.status == "collecting"
    assert r.state.awaiting is None  # 질문 없이 곧바로 완료
    c = r.state.conditions[-1]
    assert (c.metric, c.operator, c.value) == ("per", "<=", 10.0)


def test_inline_default_operator_when_omitted():
    r = step(ConditionState(), "ROE 15 넣자")  # 방향 미언급 → 관례(>=)
    c = r.state.conditions[-1]
    assert (c.metric, c.operator, c.value) == ("roe_or_gpa", ">=", 15.0)


def test_market_cap_parses_jo_unit():
    r = step(ConditionState(), "시가총액 1조 이상")
    c = r.state.conditions[-1]
    assert (c.metric, c.operator, c.value) == ("market_cap", ">=", 10000.0)


# ─── 조건 스택 ────────────────────────────────────────────────────────────────────

def test_stack_multiple_conditions():
    s = ConditionState()
    s = step(s, "PER 10 이하").state
    s = step(s, "ROE 15% 이상").state
    s = step(s, "부채비율 100 이하").state
    done = [c for c in s.conditions if c.complete]
    assert len(done) == 3
    keys = {c.metric for c in done}
    assert keys == {"per", "roe_or_gpa", "debt_ratio"}


# ─── Pending 차단 ─────────────────────────────────────────────────────────────────

def test_pending_blocks_confirm():
    # 완료 조건 없이 done 신호 → 확정되지 않고 계속 collecting.
    r = step(ConditionState(), "이대로 백테스트")
    assert r.status != "confirmed"
    # Pending만 있는 상태에서도 조립 불가.
    pending_state = ConditionState(conditions=[Condition(metric="per")], awaiting="choice")
    assert cb.build_parsed_strategy(pending_state) is None


def test_done_confirms_with_parsed():
    s = step(ConditionState(), "PBR 1 이하").state
    r = step(s, "이대로 백테스트")
    assert r.status == "confirmed"
    assert r.parsed is not None
    assert r.parsed["fundamental_filters"] == [
        {"metric": "pbr", "operator": "<=", "value": 1.0}
    ]
    assert r.prompt and "PBR" in r.prompt


def test_da_dwaesseo_is_done_not_cancel():
    s = step(ConditionState(), "PER 10 이하").state
    r = step(s, "다 됐어")
    assert r.status == "confirmed"


def test_done_while_pending_drops_incomplete_and_confirms():
    # PER 완료 후 ROE를 시작했지만(미완성) '이대로 백테스트' → ROE를 빼고 확정한다.
    s = step(ConditionState(), "PER 10 이하").state
    s = step(s, "ROE도 넣자").state          # ROE pending(choice)
    assert cb._pending(s) is not None
    r = step(s, "이대로 백테스트")
    assert r.status == "confirmed"
    metrics = {f["metric"] for f in r.parsed["fundamental_filters"]}
    assert metrics == {"per"}                 # 미완성 ROE는 빠짐


def test_skip_pending_condition():
    s = step(ConditionState(), "PER 10 이하").state
    s = step(s, "ROE도 넣자").state
    r = step(s, "그건 빼줘")
    assert r.status == "collecting"
    assert cb._pending(r.state) is None
    assert {c.metric for c in r.state.conditions} == {"per"}


# ─── 중복 처리 ────────────────────────────────────────────────────────────────────

def test_duplicate_prompts_resolution():
    s = step(ConditionState(), "ROE 10 이상").state
    r = step(s, "ROE도 넣자")
    assert r.state.awaiting == "duplicate"
    assert r.state.dup_metric == "roe_or_gpa"
    assert "수정" in r.suggestions and "삭제" in r.suggestions


def test_duplicate_modify_reopens_condition():
    s = step(ConditionState(), "ROE 10 이상").state
    s = step(s, "ROE도 넣자").state
    r = step(s, "수정")
    assert r.state.awaiting == "choice"
    assert not any(c.complete for c in r.state.conditions if c.metric == "roe_or_gpa")
    # 새 값으로 다시 완성
    r2 = step(r.state, "20 이상")
    c = [c for c in r2.state.conditions if c.metric == "roe_or_gpa"][0]
    assert c.value == 20.0


def test_duplicate_remove():
    s = step(ConditionState(), "ROE 10 이상").state
    s = step(s, "ROE도 넣자").state
    r = step(s, "삭제")
    assert not any(c.metric == "roe_or_gpa" for c in r.state.conditions)
    assert r.state.awaiting is None


def test_duplicate_keep():
    s = step(ConditionState(), "ROE 10 이상").state
    s = step(s, "ROE도 넣자").state
    r = step(s, "유지")
    done = [c for c in r.state.conditions if c.metric == "roe_or_gpa" and c.complete]
    assert len(done) == 1 and done[0].value == 10.0
    assert r.state.awaiting is None


# ─── 미지원 지표 ──────────────────────────────────────────────────────────────────

def test_unsupported_metric_notice():
    r = step(ConditionState(), "PEG도 넣자")
    assert r.status == "collecting"
    assert "PEG" in r.reply
    assert not r.state.conditions  # 조건 추가 안 됨


# ─── 제어어 ───────────────────────────────────────────────────────────────────────

def test_cancel():
    s = step(ConditionState(), "PER 10 이하").state
    r = step(s, "취소")
    assert r.status == "exited"
    assert cb.is_empty(r.state)


def test_restart():
    s = step(ConditionState(), "PER 10 이하").state
    r = step(s, "처음부터")
    assert r.status == "collecting"
    assert cb.is_empty(r.state)


def test_empty_input_shows_intro():
    r = step(ConditionState(), "")
    assert r.status == "collecting"
    assert r.suggestions == cb.INTRO_CHIPS


# ─── 조립 검증 ────────────────────────────────────────────────────────────────────

# ─── 수정 대화용 되묻기 감지 ──────────────────────────────────────────────────────

def test_clarification_for_incomplete_add():
    c = cb.clarification_for_add("영업이익률을 추가해 볼까?")
    assert c is not None
    assert c["metric"] == "operating_margin"
    assert c["label"] == "영업이익률"
    assert "몇% 이상일 때" in c["question"]
    # 칩은 라벨 붙은 완결 지시문(클릭 시 그대로 수정 메시지로 재전송). '직접 입력'은 프론트가 추가.
    assert c["suggestions"] == [
        "영업이익률 5% 이상", "영업이익률 10% 이상", "영업이익률 15% 이상", "영업이익률 20% 이상",
    ]


def test_clarification_none_when_value_present():
    # 값이 이미 있으면 되묻지 않고 기존 modify 경로가 처리한다.
    assert cb.clarification_for_add("영업이익률 15% 이상 추가") is None


def test_clarification_none_without_add_cue():
    # 정의 질문·팩터만 언급은 되묻기 트리거가 아니다.
    assert cb.clarification_for_add("영업이익률이 뭐야?") is None
    assert cb.clarification_for_add("오늘 날씨 어때") is None


def test_clarification_per_direction():
    c = cb.clarification_for_add("PER도 넣자")
    assert c["metric"] == "per"
    assert "몇배 이하일 때" in c["question"]
    assert c["suggestions"][0] == "PER 10배 이하"


@pytest.mark.parametrize("prompt", ["영업이익률을 추가해 볼까?", "PER도 넣자", "배당수익률도 추가해줘"])
def test_clarification_chips_roundtrip_through_modify(prompt):
    """되묻기 칩을 클릭하면(=칩 텍스트를 수정 메시지로 재전송) 기존 필터를 보존한 채
    새 조건이 결정적으로 병합되어야 한다(백엔드 무상태 계약의 핵심)."""
    from engine.nl_parser import _modify_rule_based

    prev = {
        "description": "x", "universe": ["KOSPI"],
        "fundamental_filters": [
            {"metric": "roe_or_gpa", "operator": ">=", "value": 10.0},
            {"metric": "debt_ratio", "operator": "<=", "value": 100.0},
        ],
        "entry_signals": [], "exit_signals": [], "max_positions": 10,
        "rebalancing_period": "quarterly", "stop_loss_pct": 10.0,
    }
    clar = cb.clarification_for_add(prompt)
    assert clar is not None
    chip = clar["suggestions"][2 if len(clar["suggestions"]) > 2 else 0]
    result = _modify_rule_based(chip, prev)
    assert result is not None, f"칩 {chip!r}이 규칙 기반 병합으로 완결되지 않음"
    metrics = {f.metric for f in result.fundamental_filters}
    # 기존 필터 보존 + 새 지표 추가
    assert {"roe_or_gpa", "debt_ratio"} <= metrics
    assert clar["metric"] in metrics
    assert result.stop_loss_pct == 10.0  # 리스크 조건도 보존


# ─── 공유 레지스트리(단일 소스) 계약 ────────────────────────────────────────────────

def test_shared_registry_keys_are_valid_engine_metrics():
    # data/fundamental-factors.json의 모든 지표 key는 엔진 스키마(FundamentalFilter.metric)가
    # 받아들이는 값이어야 한다 — 프론트/백엔드가 공유하는 JSON이 엔진과 어긋나지 않도록 가드.
    from engine.nl_parser import FundamentalFilter

    for spec in cb._REGISTRY:
        FundamentalFilter(metric=spec.key, operator=spec.direction, value=1.0)  # 검증 실패 시 raise


def test_shared_registry_wellformed():
    for spec in cb._REGISTRY:
        assert spec.direction in (">=", "<="), spec.key
        assert spec.recommend, f"{spec.key} recommend 비어 있음"
        assert spec.label and spec.unit is not None


def test_registry_loaded_from_shared_json():
    import json
    with open(cb._REGISTRY_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    assert {spec.key for spec in cb._REGISTRY} == {item["key"] for item in raw}
    # 값이 JSON에서 그대로 왔는지(하드코딩 아님) 표본 확인
    om = cb._spec("operating_margin")
    src = next(i for i in raw if i["key"] == "operating_margin")
    assert list(om.recommend) == src["recommend"] and om.direction == src["direction"]


def test_build_parsed_strategy_shape():
    s = ConditionState()
    s = step(s, "PBR 1 이하").state
    s = step(s, "ROE 15% 이상").state
    parsed = cb.build_parsed_strategy(s)
    assert parsed is not None
    assert parsed.universe == ["KOSPI", "KOSDAQ"]
    assert parsed.max_positions == 10
    assert parsed.rebalancing_period == "monthly"
    assert len(parsed.fundamental_filters) == 2
    assert parsed.entry_signals == []
