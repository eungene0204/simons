"""Strategy Builder Mode 상태 머신 테스트.

[규제 안전] 열린 종목 추천 전환 직후 빌더 대화가 짧은 답변을 전략 필드로 누적하고,
완성 시 요약·확정·합성까지 거절 없이 이어지는지 검증한다(명세 핵심 케이스 1~4 포함).
"""

from __future__ import annotations

import pytest

from intent import strategy_builder as sb
from intent.scope import OFFTOPIC_REFUSAL


def _step(state: sb.BuilderState, text: str) -> sb.StepResult:
    return sb.step(state, text)


# ─── 필드 파서 ────────────────────────────────────────────────────────────────

def test_parse_universe_variants():
    assert sb._parse_universe("일단 코스피") == "KOSPI"
    assert sb._parse_universe("코스닥으로") == "KOSDAQ"
    assert sb._parse_universe("둘 다") == "KOSPI_KOSDAQ"
    assert sb._parse_universe("전체 시장") == "KOSPI_KOSDAQ"
    assert sb._parse_universe("코스피랑 코스닥 모두") == "KOSPI_KOSDAQ"


def test_parse_universe_single_market_with_jeonche_is_that_market():
    # [회귀] "코스피 전체"는 코스피 전 종목이지 양시장이 아니다. 예전엔 '전체'가 양시장
    # 패턴에 먼저 잡혀 KOSPI_KOSDAQ로 오해석됐다(메인 NL 파서는 KOSPI로 해석 — 불일치).
    assert sb._parse_universe("코스피 전체") == "KOSPI"
    assert sb._parse_universe("코스닥 전체로 해줘") == "KOSDAQ"
    # 시장명 없는 '전체/모두'는 여전히 양시장.
    assert sb._parse_universe("전체") == "KOSPI_KOSDAQ"
    assert sb._parse_universe("모두") == "KOSPI_KOSDAQ"
    assert sb._parse_universe("코스피·코스닥 전체") == "KOSPI_KOSDAQ"


def test_parse_universe_kospi200_not_swallowed_by_kospi():
    # [회귀] '코스피200'은 '코스피'를 부분 문자열로 포함해 KOSPI로 조용히 새던 버그.
    # 엔진이 지원하는 KOSPI200 유니버스로 정확히 잡혀야 한다.
    assert sb._parse_universe("코스피200") == "KOSPI200"
    assert sb._parse_universe("코스피 200으로 해줘") == "KOSPI200"
    assert sb._parse_universe("대형주") == "KOSPI200"


def test_parse_rebalance_daily_ilgan():
    # [회귀] 주간/월간/연간은 '-간' 형을 인식하는데 daily만 '일간'을 못 잡아 리밸런싱 단계가
    # 완료되지 않고 대화 흐름이 끊기던 버그.
    assert sb._parse_rebalance("일간") == "daily"
    assert sb._parse_rebalance("매일") == "daily"
    assert sb._parse_rebalance("하루마다") == "daily"


def test_parse_strategy_type_variants():
    assert sb._parse_strategy_type("모멘텀") == "momentum"
    assert sb._parse_strategy_type("최근 오른 종목") == "momentum"
    assert sb._parse_strategy_type("골든크로스") == "golden_cross"
    assert sb._parse_strategy_type("이동평균 교차") == "golden_cross"
    assert sb._parse_strategy_type("MACD") == "macd"
    assert sb._parse_strategy_type("전고점 돌파") == "breakout"
    assert sb._parse_strategy_type("거래량 급증") == "volume_spike"
    assert sb._parse_strategy_type("과매도 반등") == "mean_reversion"
    assert sb._parse_strategy_type("저평가 가치주") == "value"
    assert sb._parse_strategy_type("직접 설명할게") == "custom"
    # 볼린저는 별도 유형이며, '하단 돌파'의 '돌파'가 breakout으로 새면 안 된다.
    assert sb._parse_strategy_type("볼린저 밴드") == "bollinger"
    assert sb._parse_strategy_type("볼린저 밴드 하단 돌파") == "bollinger"


def test_bollinger_named_strategy_locks_on_and_skips_generic_menu():
    """[회귀] 특정 전략(볼린저)을 이름으로 지목하면 잃어버리지 않고 잠근다.

    이전 버그: '볼린저 밴드 전략' 시드가 strategy_type을 못 잡아 일반 종목 선정 메뉴
    ('어떤 방식으로 종목을 고를까요?')를 띄웠고, 사용자가 모멘텀 등 다른 전략으로 흘러갔다.
    """
    state = sb.seed_state("볼린저 밴드 전략을 사용하고 싶어")
    assert state.strategy_type == "bollinger"

    # 첫 질문은 볼린저를 확인하며 시장을 묻는다(일반 전략 메뉴가 아니다).
    opening, _ = sb.next_question(state)
    assert "볼린저 밴드" in opening

    # 시장을 답한 뒤에도 일반 종목 선정 메뉴가 절대 나오면 안 된다.
    after_universe = _step(state, "코스피")
    assert "어떤 방식으로 종목을 고를까요" not in after_universe.reply

    # 남은 필드를 채우면 볼린저 백테스트 프롬프트로 합성된다(엔진 지원 신호로).
    s = after_universe.state
    s = _step(s, "없음").state              # 옵션 필터 스텝(볼린저)
    s = _step(s, "10개").state
    s = _step(s, "리밸런싱 안 함").state
    confirmed = _step(s, "10% 손절 20% 익절")
    assert confirmed.status == "confirmed"
    assert "볼린저밴드" in confirmed.prompt
    assert "하단" in confirmed.prompt and "매수" in confirmed.prompt


def test_parse_lookback_months_and_days():
    s = sb.BuilderState(universe="KOSPI", strategy_type="momentum")
    patch = sb.parse_input("3개월", s, expecting="lookback_days")
    assert patch["lookback_days"] == 63
    assert patch["lookback_label"] == "3개월"

    s2 = sb.BuilderState(universe="KOSPI", strategy_type="breakout")
    patch2 = sb.parse_input("60일", s2, expecting="lookback_days")
    assert patch2["lookback_days"] == 60


def test_bare_number_resolves_by_expecting():
    s = sb.BuilderState(universe="KOSPI", strategy_type="momentum")
    # 기준 기간을 묻는 중 "3" → 3개월
    assert sb.parse_input("3", s, expecting="lookback_days")["lookback_days"] == 63
    # 보유 수를 묻는 중 "10" → 10개
    assert sb.parse_input("10", s, expecting="holding_count")["holding_count"] == 10


def test_parse_holding_and_rebalance():
    s = sb.BuilderState()
    assert sb.parse_input("10개", s, expecting="holding_count")["holding_count"] == 10
    assert sb.parse_input("20종목", s, expecting="holding_count")["holding_count"] == 20
    assert sb._parse_rebalance("매주") == "weekly"
    assert sb._parse_rebalance("월간 리밸런싱") == "monthly"
    assert sb._parse_rebalance("분기마다") == "quarterly"
    assert sb._parse_rebalance("안 함") == "none"
    assert sb._parse_rebalance("리밸런싱 안 함") == "none"
    assert sb._parse_rebalance("그대로 보유") == "none"


def test_rebalance_none_option_offered_and_completes():
    """리밸런싱 '안 함'은 정상 옵션으로 제공되고 선택 시 전략을 완성시킨다."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum",
                            lookback_days=63, holding_count=10)
    # 다음 질문(리밸런싱)에 '안 함' 칩이 포함된다.
    _, suggestions = sb.next_question(state)
    assert "안 함" in suggestions
    # '안 함' 선택 → rebalance_cycle="none", 다음은 청산 조건 질문.
    res = _step(state, "안 함")
    assert res.state.rebalance_cycle == "none"
    assert res.status == "collecting"
    assert "청산 조건" in res.reply
    # 청산 조건(필수)을 채우면 confirmed, 합성 프롬프트엔 리밸런싱 문구가 없다.
    done = _step(res.state, "10% 손절")
    assert done.status == "confirmed"
    assert "리밸런싱" not in done.prompt


# ─── 명세 핵심 케이스 1~4 ─────────────────────────────────────────────────────────

def test_case1_kospi_after_entry_no_refusal_and_next_question():
    """Case 1: 빌더 진입 후 '일단 코스피' → universe=KOSPI, 거절 없음, 다음 질문(전략 유형)."""
    res = _step(sb.BuilderState(), "일단 코스피")
    assert res.state.universe == "KOSPI"
    assert res.status == "collecting"
    assert OFFTOPIC_REFUSAL not in res.reply
    assert "현재 질문에는 도움을 드릴 수 없습니다" not in res.reply
    assert "방식" in res.reply  # 전략 유형을 묻는 다음 질문
    assert "모멘텀" in res.suggestions


def test_blank_input_shows_opening_question_without_mutation():
    """빌더 진입 직후 빈 입력 → 상태 변화 없이 첫 질문(시장 선택)을 띄운다.

    후속 입력을 기다리지 않고 빌더의 첫 질문을 능동적으로 보여주는 경로가 의존한다.
    """
    res = _step(sb.BuilderState(), "")
    assert res.status == "collecting"
    assert res.state == sb.BuilderState()  # 아무것도 채우지 않는다
    assert "시장" in res.reply
    assert res.suggestions == ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체"]


def test_blank_input_does_not_complete_partial_risk_state():
    """청산 조건만 남은 상태에서 빈 입력이 risk_done을 켜 전략을 잘못 완성시키지 않는다."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum",
                            lookback_days=63, holding_count=10, rebalance_cycle="weekly")
    res = _step(state, "")
    assert res.status == "collecting"
    assert res.state.risk_done is False
    assert "청산 조건" in res.reply


def test_strategy_type_offers_describe_own_chip_rightmost():
    """전략 유형 질문에 '직접 설명하기' 칩이 가장 오른쪽으로 노출된다."""
    state = sb.BuilderState(universe="KOSPI")
    _, suggestions = sb.next_question(state)
    assert suggestions[-1] == "직접 설명하기"
    assert "모멘텀" in suggestions


def test_describe_own_chip_routes_to_free_text_entry_rule():
    """'직접 설명하기' 선택 → custom 유형 → 칩 없는 진입 조건 질문(프론트가 채팅창 재노출)."""
    state = sb.BuilderState(universe="KOSPI")
    res = _step(state, "직접 설명하기")
    assert res.state.strategy_type == "custom"
    assert res.status == "collecting"
    assert res.suggestions == []  # 칩이 없어 프론트가 채팅창을 다시 보여준다
    assert "매수" in res.reply
    # 이어서 자유 서술 입력은 진입 규칙으로 그대로 저장된다.
    res2 = _step(res.state, "RSI가 30 이하로 떨어지면 매수")
    assert res2.state.entry_rule == "RSI가 30 이하로 떨어지면 매수"


def test_case2_bare_kospi_interpreted_as_universe():
    """Case 2: 시장 선택을 유도한 상태에서 '코스피' → universe로 처리."""
    res = _step(sb.BuilderState(), "코스피")
    assert res.state.universe == "KOSPI"
    assert res.status == "collecting"


def test_case3_three_months_with_momentum():
    """Case 3: strategyType=momentum 상태에서 '3개월' → lookback 처리 후 다음 질문."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum")
    res = _step(state, "3개월")
    assert res.state.lookback_days == 63
    assert res.status == "collecting"
    assert res.state.holding_count is None  # 다음은 보유 수


def test_case4_cancel_resets_to_normal():
    """Case 4: '취소' → 상태 초기화 + exited(일반 모드 복귀)."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum", lookback_days=63)
    res = _step(state, "취소")
    assert res.status == "exited"
    assert res.state == sb.BuilderState()


# ─── 전체 흐름: 진입 → 완성 → 확정 → 합성 ──────────────────────────────────────────

def test_full_momentum_flow_to_confirmation():
    """리밸런싱 다음 청산 조건 단계까지 거친 뒤, 답하면 곧바로 confirmed로 합성된다."""
    state = sb.BuilderState()
    state = _step(state, "코스피").state
    state = _step(state, "모멘텀").state
    state = _step(state, "3개월").state
    state = _step(state, "10개").state
    risk_q = _step(state, "매주")
    assert risk_q.status == "collecting"  # 마지막은 청산 조건 질문
    assert "청산 조건" in risk_q.reply
    confirmed = _step(risk_q.state, "10% 손절")
    assert confirmed.status == "confirmed"
    assert confirmed.prompt
    assert "코스피" in confirmed.prompt
    assert "63일" in confirmed.prompt and "상위 10개" in confirmed.prompt
    assert "매주 리밸런싱" in confirmed.prompt
    assert "10% 손절" in confirmed.prompt


# ─── 시드(빌더 진입 시 원본 메시지 선반영) ──────────────────────────────────────────

def test_seed_state_prefills_recognized_fields():
    """STOCK_PICK 원본 메시지의 인식 가능한 조건을 미리 채운다(빠진 것만 묻기 위함)."""
    state = sb.seed_state(
        "최근 1주일 동안 수익률이 좋았던 종목 10개를 사서 -15%에 손절하고 30%에 익절해줘"
    )
    assert state.strategy_type == "momentum"
    assert state.lookback_days == 5 and state.lookback_label == "1주일"
    assert state.holding_count == 10
    assert state.stop_loss_pct == 15.0
    assert state.take_profit_pct == 30.0
    assert state.risk_done is True
    assert state.universe is None  # 유니버스만 빠짐


def test_seed_state_asks_only_missing_universe_then_rebalance():
    """이미 말한 전략유형·보유수·청산은 다시 묻지 않고 유니버스부터 묻는다."""
    state = sb.seed_state(
        "최근 1주일 동안 수익률이 좋았던 종목 10개를 사서 -15%에 손절하고 30%에 익절해줘"
    )
    first = sb.step(state, "")
    assert first.status == "collecting"
    assert "시장" in first.reply              # 첫 질문은 유니버스
    assert "방식으로 종목" not in first.reply  # 전략유형은 다시 묻지 않음

    after_univ = sb.step(first.state, "코스닥")
    # 직전 답변(유니버스)을 확인해야지, 시드된 보유수를 엉뚱하게 확인하면 안 된다.
    assert "코스닥 시장을 대상으로" in after_univ.reply
    assert "리밸런싱" in after_univ.reply       # 진짜 빠진 다음 질문

    confirmed = sb.step(after_univ.state, "매월")
    assert confirmed.status == "confirmed"
    assert "코스닥" in confirmed.prompt
    assert "상위 10개" in confirmed.prompt
    assert "-15% 손절" in confirmed.prompt and "30% 익절" in confirmed.prompt


def test_is_empty_gates_seeding():
    assert sb.is_empty(sb.BuilderState()) is True
    assert sb.is_empty(sb.BuilderState(universe="KOSPI")) is False


def test_seed_state_remembers_sector_and_leading_stock_phrasing():
    """종목 질문 리다이렉트 뒤 '반도체 주도주로 전략을 만들어줘' — 업종을 기억하고
    주도주=모멘텀으로 인식해, 종목 고르는 질문(전략유형)을 다시 묻지 않는다."""
    state = sb.seed_state("반도체 주도주로 전략을 만들어줘")
    assert state.sector == "반도체"
    assert state.strategy_type == "momentum"

    first = sb.step(state, "")
    assert first.status == "collecting"
    assert "반도체 업종" in first.reply        # 기억한 업종을 도입부에서 확인
    assert "시장" in first.reply               # 첫 질문은 유니버스
    assert "방식으로 종목" not in first.reply  # 전략유형은 다시 묻지 않음


def test_seed_state_sector_with_jungshim_cue_no_type_lock():
    """'반도체 중심으로 전략을 만들어줘' — 업종은 기억하되('중심' 큐), 방식은 말하지
    않았으므로 전략유형 질문은 그대로 진행한다(범위만 좁힘)."""
    state = sb.seed_state("반도체 중심으로 전략을 만들어줘")
    assert state.sector == "반도체"
    assert state.strategy_type is None

    first = sb.step(state, "")
    assert "반도체 업종" in first.reply  # 기억한 업종을 도입부에서 확인


def test_apply_parsed_seed_takes_llm_resolved_fields():
    """빈 전략으로 빌더 전환 시, 파싱 파이프라인(LLM 검증/폴백)이 해석한 결과에서 결정적
    시드가 놓친 필드를 이어받는다 — 긴 꼬리 표현마다 regex를 늘리지 않기 위한 채널."""
    # 시드 regex가 못 잡는 표현이라고 가정(시드 결과에 sector 없음).
    state = sb.seed_state("괜찮은 전략 하나 만들어줘")
    assert state.sector is None

    seeded = sb.apply_parsed_seed(state, {"sector": "반도체", "stop_loss_pct": 10.0})
    assert seeded.sector == "반도체"
    assert seeded.stop_loss_pct == 10.0
    assert seeded.risk_done is True  # 청산 조건을 이어받았으므로 다시 묻지 않는다

    first = sb.step(seeded, "")
    assert "반도체 업종" in first.reply  # 이어받은 업종을 도입부에서 확인


def test_apply_parsed_seed_normalizes_and_rejects_garbage():
    """이어받는 sector는 정본 섹터명으로 정규화하고, 미지원 업종·비정상 입력은 무시한다."""
    empty = sb.BuilderState()
    assert sb.apply_parsed_seed(empty, {"sector": "2차전지"}).sector == "이차전지"
    assert sb.apply_parsed_seed(empty, {"sector": "화성부동산"}).sector is None
    assert sb.apply_parsed_seed(empty, {"stop_loss_pct": -5}).risk_done is False
    assert sb.apply_parsed_seed(empty, None) is empty
    assert sb.apply_parsed_seed(empty, {}) is empty


def test_apply_parsed_seed_does_not_override_deterministic_seed():
    """결정적 시드가 이미 채운 값이 파싱 결과보다 우선한다."""
    state = sb.seed_state("반도체 관련주로 10% 손절 전략")
    assert state.sector == "반도체" and state.stop_loss_pct == 10.0

    seeded = sb.apply_parsed_seed(state, {"sector": "게임", "stop_loss_pct": 99.0})
    assert seeded.sector == "반도체"
    assert seeded.stop_loss_pct == 10.0


def test_sector_flows_into_prompt_and_dsl():
    """시드된 업종이 합성 프롬프트와 직접 구성 DSL(ParsedStrategy.sector)까지 흐른다."""
    state = sb.seed_state("반도체 주도주 전략")
    r = sb.step(state, "")
    for answer in ("코스피", "3개월", "5종목", "매월", "10% 손절"):
        r = sb.step(r.state, answer)
    assert r.status == "confirmed"
    assert "반도체 업종" in r.prompt
    parsed = sb.build_parsed_strategy(r.state)
    assert parsed.sector == "반도체"
    assert parsed.universe == ["KOSPI"]
    assert parsed.ranking_metric == "return"


def test_seed_unsupported_sector_notice_shown_once():
    """[회귀] '로봇주 관련 전략을 만들어보자' — 지원 목록에 없는 업종이 조용히 버려져
    전체 시장으로 백테스트되던 버그. 시드가 언급을 캐치해 안내를 한 번만 보여준다."""
    state = sb.seed_state("로봇주 관련 전략을 만들어보자")
    assert state.sector is None
    assert state.sector_unresolved is True

    first = sb.step(state, "")
    assert "지원 목록에 없어" in first.reply       # 목록 밖 업종 안내
    assert "시장" in first.reply                   # 첫 질문(유니버스)은 그대로 이어진다
    assert first.state.sector_unresolved is False  # 1회 표시 후 소비

    second = sb.step(first.state, "코스피")
    assert "지원 목록에 없어" not in second.reply  # 반복 안내 없음


def test_seed_unsupported_sector_word_order_variants():
    """'관련주' 어순이 아니어도('로봇 관련'·'메타버스 테마') 목록 밖 업종 언급을 캐치한다."""
    assert sb.seed_state("로봇 관련 전략 만들어줘").sector_unresolved is True
    assert sb.seed_state("메타버스 테마 전략").sector_unresolved is True
    # 지원 업종은 정상 시드되고 플래그는 켜지지 않는다.
    supported = sb.seed_state("반도체 관련 전략 만들어줘")
    assert supported.sector == "반도체"
    assert supported.sector_unresolved is False
    # 업종 무관 표현은 목록 밖 언급이 아니다.
    assert sb.seed_state("업종 상관없이 코스피 모멘텀 전략").sector_unresolved is False


def test_midflow_supported_sector_mention_is_captured():
    """안내를 본 사용자가 대화 중 지원 업종을 말하면 캐치해 유니버스 제한으로 반영한다."""
    state = sb.seed_state("로봇주 관련 전략을 만들어보자")
    first = sb.step(state, "")  # 안내 소비 + 유니버스 질문
    r = sb.step(first.state, "그러면 기계/장비 업종으로 해줘")
    assert r.state.sector == "기계/장비"
    assert "기계/장비 업종" in r.reply  # 반영 확인(ack)


def test_unresolved_sector_resolved_by_llm_resolver():
    """[FR] '원자로 관련주 전략을 만들자' — 결정적 정규화가 실패해도 LLM 해석기가 지원
    업종('에너지/원자력')으로 매핑하면 sector로 반영돼 안내 없이 배지까지 관통한다."""
    state = sb.seed_state("원자로 관련주 전략을 만들자")
    assert state.sector is None and state.sector_unresolved is True
    assert state.sector_hint == "원자로 관련주 전략을 만들자"

    calls: list[str] = []

    def resolver(text: str):
        calls.append(text)
        return "에너지/원자력"

    first = sb.step(state, "", sector_resolver=resolver)
    assert calls == ["원자로 관련주 전략을 만들자"]  # 힌트 원문으로 호출
    assert first.state.sector == "에너지/원자력"
    assert first.state.sector_unresolved is False and first.state.sector_hint is None
    assert "지원 목록에 없어" not in first.reply           # 안내 대신 해석 성공
    assert "에너지/원자력 업종 대상" in first.reply        # 이해한 업종을 도입부에서 확인

    # 이후 합성 프롬프트/DSL까지 흐른다.
    r = first
    for answer in ("코스피", "모멘텀", "3개월", "5종목", "매월", "10% 손절"):
        r = sb.step(r.state, answer, sector_resolver=resolver)
    assert r.status == "confirmed"
    assert "에너지/원자력 업종" in r.prompt
    assert sb.build_parsed_strategy(r.state).sector == "에너지/원자력"
    assert len(calls) == 1  # 해석은 한 번만(이후 턴에서 재호출 없음)


def test_unresolved_sector_llm_null_or_error_falls_back_to_notice():
    """LLM이 매핑 불가(null)거나 실패하면 기존 미지원 안내로 폴백한다."""
    state = sb.seed_state("로봇주 관련 전략을 만들어보자")
    first = sb.step(state, "", sector_resolver=lambda _t: None)
    assert "지원 목록에 없어" in first.reply
    assert first.state.sector is None and first.state.sector_unresolved is False

    state2 = sb.seed_state("로봇주 관련 전략을 만들어보자")
    def boom(_t):
        raise RuntimeError("LLM down")
    second = sb.step(state2, "", sector_resolver=boom)
    assert "지원 목록에 없어" in second.reply  # 예외에도 안내로 안전 폴백


def test_unresolved_sector_resolver_output_is_renormalized():
    """해석기 출력은 normalize_sector로 재검증한다 — 목록 밖 이름을 지어내면 무시."""
    state = sb.seed_state("원자로 관련주 전략을 만들자")
    first = sb.step(state, "", sector_resolver=lambda _t: "원자로섹터")
    assert first.state.sector is None
    assert "지원 목록에 없어" in first.reply
    # 동의어('원자력')로 답해도 정본명('에너지/원자력')으로 들어간다.
    state2 = sb.seed_state("원자로 관련주 전략을 만들자")
    second = sb.step(state2, "", sector_resolver=lambda _t: "원자력")
    assert second.state.sector == "에너지/원자력"


def test_midflow_unresolved_mention_resolved_by_llm():
    """대화 중 미지원 표현('원자로 관련주로')도 LLM 해석으로 반영되고 확인 문장이 나온다."""
    state = sb.step(sb.BuilderState(), "").state  # 빈 상태에서 유니버스 질문
    r = sb.step(state, "원자로 관련주로 해줘", sector_resolver=lambda _t: "에너지/원자력")
    assert r.state.sector == "에너지/원자력"
    assert "에너지/원자력 업종" in r.reply  # LLM 해석분도 ack


def test_cancel_control_not_triggered_by_gwan_syllable():
    """[회귀] '관둘?'의 ?가 '둘'에만 붙어 맨 '관'에도 매칭 — '관련주로 해줘'·'관심 업종'이
    취소로 오인돼 빌더가 종료되던 버그."""
    assert sb.detect_control("원자로 관련주로 해줘") is None
    assert sb.detect_control("관심 있는 업종으로") is None
    assert sb.detect_control("관둘래") == "cancel"
    assert sb.detect_control("그냥 관두자") == "cancel"


def test_sector_llm_prompt_carries_convention_glosses():
    """[회귀, 2026-07-12 실측] LLM이 업종 '이름' 연상('전력→유틸리티')으로 '전력설비
    관련주'를 통신/유틸리티(실제: 통신사·한전 등 사업자)에 매핑 — 변압기·전력설비 제조는
    이 분류 체계에서 에너지/원자력이다. 혼동 업종의 관례 주석이 두 프롬프트(빌더 해석기·
    메인 파싱 COMPACT)에 모두 실려야 한다."""
    from engine.nl_parser import COMPACT_SYSTEM_PROMPT
    from engine.universe_pit import sectors_for_llm_prompt

    glossed = sectors_for_llm_prompt()
    assert "전력설비" in glossed          # 에너지/원자력 주석
    assert "사업자" in glossed            # 통신/유틸리티 주석
    assert "전선" in glossed              # IT 하드웨어 주석
    assert glossed in sb._sector_llm_prompt()
    assert glossed in COMPACT_SYSTEM_PROMPT


def test_llm_extract_sector_parses_and_validates():
    assert sb.llm_extract_sector("원자로", lambda *_a, **_k: '{"sector": "에너지/원자력"}') == "에너지/원자력"
    assert sb.llm_extract_sector("원자로", lambda *_a, **_k: '{"sector": "원자력"}') == "에너지/원자력"
    assert sb.llm_extract_sector("로봇", lambda *_a, **_k: '{"sector": null}') is None
    assert sb.llm_extract_sector("로봇", lambda *_a, **_k: "말도 안 되는 출력") is None
    assert sb.llm_extract_sector("로봇", lambda *_a, **_k: '{"sector": "듣도보도못한업종"}') is None


def test_seed_confirmed_with_unresolved_sector_carries_notice():
    """시드만으로 즉시 confirmed되는 경우(모멘텀)에도 안내가 notices 채널로 전달된다."""
    state = sb.seed_state(
        "로봇 관련 모멘텀 전략, 코스피에서 최근 3개월 상위 5종목, 매월 리밸런싱, 10% 손절"
    )
    assert state.sector_unresolved is True
    r = sb.step(state, "")
    assert r.status == "confirmed"
    assert any("지원 목록에 없어" in n for n in r.notices)


def test_parse_strategy_type_recognizes_profit_phrasing():
    assert sb._parse_strategy_type("수익률이 좋았던 종목") == "momentum"
    assert sb._parse_strategy_type("많이 오른 종목") == "momentum"


def test_parse_lookback_weeks():
    assert sb._parse_lookback("최근 1주일")["lookback_days"] == 5
    assert sb._parse_lookback("2주")["lookback_days"] == 10


def test_restart_keeps_builder_and_clears_state():
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum", lookback_days=63)
    res = _step(state, "처음부터")
    assert res.status == "reset"
    assert res.state == sb.BuilderState()
    assert "시장" in res.reply  # 첫 질문(유니버스)


def test_exit_other_question_returns_to_normal():
    state = sb.BuilderState(universe="KOSPI")
    res = _step(state, "다른 질문 할게")
    assert res.status == "exited"


def test_failed_parse_reasks_without_refusal():
    """파싱 실패 시 거절하지 않고 같은 질문을 다시 한다."""
    res = _step(sb.BuilderState(), "음 글쎄요")
    assert res.status == "collecting"
    assert res.state.universe is None
    assert "시장" in res.reply
    assert OFFTOPIC_REFUSAL not in res.reply


# ─── 유형별 합성 프롬프트 ──────────────────────────────────────────────────────────

def test_synthesize_breakout_volume_meanrev():
    bo = sb.BuilderState(universe="KOSDAQ", strategy_type="breakout",
                         lookback_days=60, holding_count=10, rebalance_cycle="weekly")
    assert "신고가를 돌파" in sb.synthesize_prompt(bo)
    assert "코스닥" in sb.synthesize_prompt(bo)

    vol = sb.BuilderState(universe="KOSPI", strategy_type="volume_spike",
                          holding_count=5, rebalance_cycle="monthly")
    assert "거래량 급증(OBV 상승 전환)" in sb.synthesize_prompt(vol)
    assert "매월 리밸런싱" in sb.synthesize_prompt(vol)

    mr = sb.BuilderState(universe="KOSPI", strategy_type="mean_reversion",
                         holding_count=10, rebalance_cycle="weekly")
    assert "RSI가 30 이하" in sb.synthesize_prompt(mr)


def test_synthesize_golden_macd_value():
    gc = sb.BuilderState(universe="KOSPI", strategy_type="golden_cross",
                         holding_count=10, rebalance_cycle="weekly")
    assert "골든크로스" in sb.synthesize_prompt(gc)

    macd = sb.BuilderState(universe="KOSDAQ", strategy_type="macd",
                           holding_count=5, rebalance_cycle="monthly")
    assert "MACD" in sb.synthesize_prompt(macd)
    assert "코스닥" in sb.synthesize_prompt(macd)

    val = sb.BuilderState(universe="KOSPI", strategy_type="value",
                          holding_count=10, rebalance_cycle="quarterly")
    assert "PBR 1 이하" in sb.synthesize_prompt(val)
    assert "ROE 10% 이상" in sb.synthesize_prompt(val)


def test_new_strategy_types_skip_lookback_question():
    # 골든크로스·MACD·가치는 기준기간(lookback) 질문이 없다(모멘텀·돌파만 lookback 필수).
    # 대신 각자의 전략별 파라미터를 먼저 묻는다.
    expected_first = {"golden_cross": "ma_kind", "macd": "macd_mode", "value": "value_params"}
    for stype, first in expected_first.items():
        state = sb.BuilderState(universe="KOSPI", strategy_type=stype)
        step = sb.required_missing(state)
        assert step != "lookback_days"
        assert step == first


@pytest.mark.parametrize("stype", ["golden_cross", "macd", "value"])
def test_new_strategy_types_synthesize_parses_to_buy_criteria(stype):
    # [회귀] 새 전략 유형의 합성 프롬프트는 반드시 매수 기준(진입 신호/재무 필터)으로 파싱돼야 한다.
    # 그렇지 않으면 빈 전략으로 판정돼 다시 빌더로 되돌아가는 무한루프가 생긴다.
    from engine.nl_parser import _extract_fundamental_filters, _extract_technical_signals

    state = sb.BuilderState(universe="KOSPI", strategy_type=stype,
                            holding_count=10, rebalance_cycle="weekly")
    prompt = sb.synthesize_prompt(state)
    buy, _sell = _extract_technical_signals(prompt)
    fund = _extract_fundamental_filters(prompt)
    assert buy or fund, f"{stype} 합성 프롬프트가 매수 기준으로 파싱되지 않음: {prompt}"


def test_custom_flow_captures_entry_rule():
    state = sb.BuilderState(universe="KOSPI")
    state = _step(state, "직접 설명할게").state
    assert state.strategy_type == "custom"
    # 다음 입력은 진입 규칙 서술로 저장된다.
    state = _step(state, "20일선이 60일선을 상향 돌파하면").state
    assert state.entry_rule == "20일선이 60일선을 상향 돌파하면"
    state = _step(state, "10개").state
    state = _step(state, "매주").state  # 청산 조건 질문
    res = _step(state, "10% 손절")
    assert res.status == "confirmed"
    assert "20일선이 60일선을 상향 돌파" in res.prompt


def test_custom_entry_rule_captures_explicit_holding_count():
    """진입 서술에 명시적 종목 수("상위 5개")가 섞여 있으면 보유 수로 함께 잡아 다시 묻지 않는다.

    [회귀] 'custom' 진입 서술 단계가 입력 전체를 entry_rule로만 저장하면서 명시적 "5개"를
    버려, 사용자가 이미 종목 수를 말했는데도 보유 수를 다시 묻던 버그."""
    state = sb.BuilderState(universe="KOSDAQ", strategy_type="custom")
    res = _step(state, "코스닥 시총 상위 5개를 사는 전략")
    assert res.state.entry_rule == "코스닥 시총 상위 5개를 사는 전략"
    assert res.state.holding_count == 5
    # 보유 수가 채워졌으므로 다음 질문은 보유 수가 아니라 리밸런싱이다.
    assert sb.required_missing(res.state) == "rebalance_cycle"
    assert "몇 종목" not in res.reply


def test_custom_entry_rule_does_not_misread_bare_threshold_as_count():
    """진입 서술의 맨숫자(RSI 30)는 보유 수로 오인하지 않는다(명시적 개/종목 접미사만 인정)."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="custom")
    res = _step(state, "RSI가 30 이하로 떨어지면 매수")
    assert res.state.holding_count is None


def test_holding_count_step_offers_free_input_chip_rightmost():
    """보유 수 질문에 '직접 입력' 칩이 가장 오른쪽으로 노출된다(5/10/20 외 종목 수 직접 타이핑)."""
    momentum = sb.BuilderState(universe="KOSPI", strategy_type="momentum", lookback_days=63)
    # 볼린저는 특화 파라미터가 없고 옵션 필터도 물었으면(filters_asked) 보유 종목 수로 넘어간다.
    bollinger = sb.BuilderState(universe="KOSPI", strategy_type="bollinger", filters_asked=True)
    for state in (momentum, bollinger):
        _, suggestions = sb.next_question(state)
        assert sb.required_missing(state) == "holding_count"
        assert suggestions[-1] == "직접 입력"


def test_holding_count_step_free_text_parses_custom_value():
    """'직접 입력' 후 사용자가 타이핑한 임의 종목 수('7개')가 그대로 파싱된다."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="bollinger", filters_asked=True)
    res = _step(state, "7개")
    assert res.state.holding_count == 7


# ─── 청산 조건(손절·익절·트레일링·보유기간) 단계 ─────────────────────────────────────

def _ready_for_risk() -> sb.BuilderState:
    """리밸런싱까지 채워 청산 조건만 남은 상태."""
    return sb.BuilderState(universe="KOSPI", strategy_type="momentum",
                           lookback_days=63, holding_count=10, rebalance_cycle="weekly")


def test_risk_step_offered_after_rebalance():
    """리밸런싱을 채우면 청산 조건 질문이 칩과 함께 제시된다(청산 조건은 필수)."""
    msg, suggestions = sb.next_question(_ready_for_risk())
    assert "청산 조건" in msg
    assert "10% 손절" in suggestions
    # 청산 조건은 필수이므로 '청산 조건 없음' 칩은 제공하지 않는다.
    assert "청산 조건 없음" not in suggestions


def test_risk_step_offers_free_input_chip_rightmost():
    """청산 조건 질문에 '직접 입력' 칩이 가장 오른쪽으로 노출된다(프론트가 채팅창 토글)."""
    _, suggestions = sb.next_question(_ready_for_risk())
    assert suggestions[-1] == "직접 입력"


def test_risk_step_free_text_after_direct_input_parses_custom_value():
    """'직접 입력' 후 사용자가 타이핑한 커스텀 청산 값('15% 손절')이 그대로 파싱된다."""
    r = _step(_ready_for_risk(), "15% 손절")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 15.0
    assert "15% 손절" in r.prompt


def test_risk_step_parses_stop_loss_with_korean_particle():
    """'15%에 손절 30% 익절'처럼 퍼센트와 키워드 사이에 조사(에)가 끼어도 손절을 인식한다."""
    r = _step(_ready_for_risk(), "15%에 손절 30% 익절")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 15.0
    assert r.state.take_profit_pct == 30.0
    assert "15% 손절" in r.prompt and "30% 익절" in r.prompt


def test_risk_step_keyword_first_order_no_misattribution():
    """[회귀] '손절 10% 익절 20%'처럼 키워드가 값보다 먼저 와도 정확히 귀속돼야 한다.
    예전엔 익절 정규식이 앞의 '10%'(손절 값)를 훔쳐가 손절=None·익절=10으로 조용히 틀리던 버그."""
    r = _step(_ready_for_risk(), "손절 10% 익절 20%")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 10.0
    assert r.state.take_profit_pct == 20.0
    assert "10% 손절" in r.prompt and "20% 익절" in r.prompt


def test_risk_step_negated_stop_loss_not_extracted():
    """'손절 없이 익절 20%'는 손절을 뽑지 않고 익절만 20%로 잡아야 한다(부정어 가드)."""
    r = _step(_ready_for_risk(), "손절 없이 익절 20%")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct is None
    assert r.state.take_profit_pct == 20.0


@pytest.mark.parametrize(
    "question, term",
    [
        ("손절이 뭐야?", "손절"),
        ("트레일링 스탑이 무슨 뜻이에요?", "트레일링"),
        ("리밸런싱이 뭔가요?", "리밸런싱"),
        ("모멘텀이 무엇인가요", "모멘텀"),
    ],
)
def test_glossary_question_mid_builder_answers_and_reasks(question, term):
    """[회귀] 빌더 진행 중 용어 질문은 필드 답변으로 오인돼 같은 질문만 반복되던 막다른 길 —
    짧은 정의를 답하고 현재 질문을 이어가며 상태는 바뀌지 않는다."""
    state = _ready_for_risk()
    r = _step(state, question)
    assert r.status == "collecting"
    assert r.state == state  # 상태 불변
    assert term in r.reply.split("\n\n")[0]  # 앞부분이 정의문
    assert "청산 조건" in r.reply  # 뒤에 현재 질문이 이어짐
    assert "10% 손절" in r.suggestions


def test_glossary_does_not_intercept_normal_answers():
    """정의 표지 없는 일반 답변("10% 손절", "모멘텀")은 용어집이 가로채지 않는다."""
    r = _step(_ready_for_risk(), "10% 손절")
    assert r.status == "confirmed"
    st = sb.BuilderState(universe="KOSPI")
    r2 = _step(st, "모멘텀")
    assert r2.state.strategy_type == "momentum"


@pytest.mark.parametrize("answer", ["없음", "청산 조건은 따로 없이 갈래", "필요 없어"])
def test_risk_step_refusal_explains_why_required(answer):
    """[회귀] 청산 조건 거부("없음")에 같은 질문을 그대로 무한 반복하던 침묵 루프 —
    청산 조건이 필수인 이유를 설명하며 되묻는다(필수 설계는 유지, risk_done은 켜지 않음)."""
    r = _step(_ready_for_risk(), answer)
    assert r.status == "collecting"
    assert r.state.risk_done is False
    assert r.reply == sb.RISK_REQUIRED_REPLY
    assert "10% 손절" in r.suggestions


def test_risk_step_llm_recovers_value_regex_missed():
    """정규식이 키워드(손절)는 봤지만 값을 못 뽑으면 LLM 보강 파서로 값을 채운다."""
    calls = []

    def fake_extractor(text: str) -> dict:
        calls.append(text)
        return {"stop_loss_pct": 20.0}

    # '이십프로 손절'은 정규식이 수치를 못 뽑지만 키워드는 있어 LLM 보강이 트리거된다.
    r = sb.step(_ready_for_risk(), "이십프로 손절", fake_extractor)
    assert calls == ["이십프로 손절"]
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 20.0
    assert "20% 손절" in r.prompt


def test_risk_step_regex_match_skips_llm():
    """정규식이 깨끗이 잡으면 LLM 보강 파서를 호출하지 않는다(비용/지연 절감)."""
    calls = []

    def fake_extractor(text: str) -> dict:
        calls.append(text)
        return {}

    r = sb.step(_ready_for_risk(), "10% 손절", fake_extractor)
    assert calls == []  # LLM 미호출
    assert r.state.stop_loss_pct == 10.0


def test_risk_step_regex_takes_priority_over_llm():
    """정규식이 잡은 필드는 LLM 결과로 덮어쓰지 않는다(결정론 우선)."""
    # 손절은 정규식이 잡고(15), 익절은 '삼십프로'라 정규식이 놓쳐 LLM이 채운다(30).
    r = sb.step(
        _ready_for_risk(),
        "15% 손절에 삼십프로 익절",
        lambda _t: {"stop_loss_pct": 99.0, "take_profit_pct": 30.0},
    )
    assert r.state.stop_loss_pct == 15.0  # 정규식 값 유지(LLM 99 무시)
    assert r.state.take_profit_pct == 30.0  # 정규식이 놓친 값만 LLM 보강


def test_risk_step_llm_failure_falls_back_to_regex():
    """LLM 보강이 예외를 던져도 정규식 결과로 안전하게 폴백한다."""
    def boom(_t: str) -> dict:
        raise RuntimeError("LLM down")

    r = sb.step(_ready_for_risk(), "15%에 손절", boom)
    assert r.state.stop_loss_pct == 15.0  # 정규식이 이미 잡음


def test_risk_step_parses_stop_take_trailing_hold():
    state = _ready_for_risk()

    r = _step(state, "10% 손절·20% 익절")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 10.0 and r.state.take_profit_pct == 20.0
    assert "10% 손절" in r.prompt and "20% 익절" in r.prompt

    r2 = _step(state, "최고가 대비 10% 하락 시 청산")
    assert r2.state.trailing_stop_pct == 10.0
    assert "최고가 대비 10% 하락 시 청산" in r2.prompt

    r3 = _step(state, "트레일링 8%")
    assert r3.state.trailing_stop_pct == 8.0

    r4 = _step(state, "20일 보유 후 청산")
    assert r4.state.hold_period_days == 20
    assert "20거래일 보유" in r4.prompt

    r5 = _step(state, "3개월 보유")
    assert r5.state.hold_period_days == 63


def test_risk_step_requires_a_condition_and_reasks_otherwise():
    """청산 조건은 필수 — 인식 가능한 조건이 없으면 완료하지 않고 같은 질문을 다시 한다."""
    r = _step(_ready_for_risk(), "청산 조건 없음")
    assert r.status == "collecting"
    assert r.state.risk_done is False
    assert "청산 조건" in r.reply
    # 그 뒤 유효한 조건을 주면 완료된다.
    done = _step(r.state, "10% 손절")
    assert done.status == "confirmed"
    assert done.state.stop_loss_pct == 10.0


def test_risk_step_cancel_still_exits():
    """청산 조건 단계에서도 '취소'는 빌더를 종료한다."""
    r = _step(_ready_for_risk(), "취소")
    assert r.status == "exited"


# ─── 전략별 특화 빌더(STATE_SPECIFIC_STRATEGY_BUILDER) ──────────────────────────────

from engine.strategy_converter import to_backtest_request  # noqa: E402


def test_specific_type_recognition_rsi_stoch_cci():
    """이름으로 지목한 특화 전략 유형을 인식한다. 'RSI'는 전용 rsi(과매도 반등은 mean_reversion)."""
    assert sb._parse_strategy_type("RSI 전략 만들어줘") == "rsi"
    assert sb._parse_strategy_type("스토캐스틱 전략") == "stochastic"
    assert sb._parse_strategy_type("CCI 전략") == "cci"
    # '과매도 반등'은 여전히 프리셋 mean_reversion(RSI라는 단어가 없음).
    assert sb._parse_strategy_type("과매도 반등 전략") == "mean_reversion"


@pytest.mark.parametrize("seed,stype,first_step", [
    ("RSI 전략을 사용하고 싶어", "rsi", "rsi_period"),
    ("MACD 전략 만들어줘", "macd", "macd_mode"),
    ("골든크로스 전략", "golden_cross", "ma_kind"),
    ("CCI 전략으로 해줘", "cci", "cci_params"),
])
def test_named_strategy_locks_on_and_asks_own_param(seed, stype, first_step):
    """[회귀] 특정 전략을 지목하면 유형이 잠기고, 일반 메뉴 대신 그 전략의 파라미터를 먼저 묻는다."""
    state = sb.seed_state(seed)
    assert state.strategy_type == stype
    after_univ = _step(state, "코스피")
    assert "어떤 방식으로 종목을 고를까요" not in after_univ.reply
    assert sb.required_missing(after_univ.state) == first_step


def test_rsi_full_flow_builds_dsl_with_params():
    """RSI 전용 흐름이 기간·과매도·과매수를 수집해 DSL에 정확히 반영한다."""
    s = sb.seed_state("RSI 전략")
    s = _step(s, "코스피").state
    s = _step(s, "9일").state            # rsi_period
    s = _step(s, "25 / 75").state        # rsi_bounds
    s = _step(s, "없음").state           # 옵션 필터 스텝
    s = _step(s, "10개").state
    s = _step(s, "매월").state
    res = _step(s, "10% 손절 20% 익절")
    assert res.status == "confirmed"
    parsed = sb.build_parsed_strategy(res.state)
    req = to_backtest_request(parsed, resolve_symbols=False)
    entry = req["entry"]["conditions"][0]
    exit_ = req["exit"]["conditions"][0]
    assert entry["id"] == "rsi" and entry["params"]["period"] == 9 and entry["params"]["value"] == 25.0
    assert exit_["id"] == "rsi" and exit_["params"]["value"] == 75.0
    assert req["risk"]["stop_loss_pct"] == 10.0 and req["risk"]["take_profit_pct"] == 20.0


def test_ma_flow_ema_periods_flow_to_dsl():
    """이동평균 전용 흐름이 SMA/EMA와 단기·장기 기간을 DSL에 반영한다."""
    s = sb.seed_state("골든크로스 전략")
    s = _step(s, "코스피").state
    s = _step(s, "지수(EMA)").state       # ma_kind
    s = _step(s, "10일 60일").state       # ma_periods
    s = _step(s, "없음").state           # 옵션 필터 스텝
    s = _step(s, "10개").state
    s = _step(s, "매월").state
    res = _step(s, "10% 손절")
    parsed = sb.build_parsed_strategy(res.state)
    req = to_backtest_request(parsed, resolve_symbols=False)
    entry = req["entry"]["conditions"][0]
    assert entry["id"] == "ema"
    assert entry["params"]["shortPeriod"] == 10 and entry["params"]["longPeriod"] == 60


def test_default_answer_applies_preset():
    """'기본'이라고 답하면 그 스텝의 표준 기본값이 채워진다(초보자 경로)."""
    assert sb._parse_rsi_period("기본") == {"rsi_period": 14}
    assert sb._parse_rsi_bounds("기본값으로") == {"rsi_oversold": 30.0, "rsi_overbought": 70.0}
    assert sb._parse_ma_periods("그냥 기본") == {"ma_short": 5, "ma_long": 20}


@pytest.mark.parametrize("state_kwargs,expect_entry_id,expect_exit_n", [
    (dict(strategy_type="momentum", lookback_days=63), None, 0),        # ranking, 진입신호 없음
    (dict(strategy_type="bollinger"), "bollinger_bands", 1),
    (dict(strategy_type="breakout", lookback_days=30), "breakout", 0),
    (dict(strategy_type="volume_spike", volume_period=20), "volume_spike", 0),
    (dict(strategy_type="cci", cci_period=14, cci_threshold=100.0), "cci", 1),
    (dict(strategy_type="stochastic"), "stochastic", 1),
])
def test_build_parsed_strategy_entry_exit_shapes(state_kwargs, expect_entry_id, expect_exit_n):
    """각 유형이 엔진 지원 진입/청산 신호로 구성된다(빈 전략·미지원 신호 방지)."""
    st = sb.BuilderState(universe="KOSPI", holding_count=10, rebalance_cycle="monthly",
                         stop_loss_pct=10.0, risk_done=True, **state_kwargs)
    parsed = sb.build_parsed_strategy(st)
    req = to_backtest_request(parsed, resolve_symbols=False)
    entry_ids = [c["id"] for c in req["entry"]["conditions"]]
    if expect_entry_id is None:
        assert entry_ids == []
        assert req["risk"]["ranking_metric"] == "return"
    else:
        assert expect_entry_id in entry_ids
    assert len(req["exit"]["conditions"]) == expect_exit_n


def test_value_strategy_builds_fundamental_filters():
    """가치 전략은 PBR·ROE 재무 필터로 구성된다(랭킹·기술신호 없이 스크리닝)."""
    st = sb.BuilderState(universe="KOSPI", strategy_type="value", value_pbr=0.8, value_roe=15.0,
                         holding_count=10, rebalance_cycle="quarterly", stop_loss_pct=10.0, risk_done=True)
    parsed = sb.build_parsed_strategy(st)
    req = to_backtest_request(parsed, resolve_symbols=False)
    filt = {c["id"]: c["params"] for c in req["entry"]["conditions"]}
    assert filt["pbr"]["value"] == 0.8 and filt["pbr"]["operator"] == "<="
    assert filt["roe_or_gpa"]["value"] == 15.0 and filt["roe_or_gpa"]["operator"] == ">="


def test_custom_strategy_has_no_direct_dsl():
    """custom(자유 서술)은 DSL을 만들 수 없어 None(프론트가 prompt 재파싱 폴백)."""
    st = sb.BuilderState(universe="KOSPI", strategy_type="custom", entry_rule="내 규칙",
                         holding_count=10, rebalance_cycle="none", stop_loss_pct=10.0, risk_done=True)
    assert sb.build_parsed_strategy(st) is None


# ─── Tier 2: 옵션 진입 필터(추세·거래대금·RSI 결합) ───────────────────────────────────

def test_filter_step_offered_for_technical_strategies_not_ranking():
    """기술적 진입 전략엔 옵션 필터 스텝이 있고, 모멘텀(랭킹)·가치(스크리닝)엔 없다."""
    for stype, kw in [("bollinger", {}), ("rsi", dict(rsi_period=14, rsi_oversold=30.0, rsi_overbought=70.0)),
                      ("macd", dict(macd_mode="crossover"))]:
        st = sb.BuilderState(universe="KOSPI", strategy_type=stype, **kw)
        assert sb.required_missing(st) == "filters"
    # 모멘텀·가치는 필터 스텝 없이 곧장 다음 단계로.
    mom = sb.BuilderState(universe="KOSPI", strategy_type="momentum", lookback_days=63)
    assert sb.required_missing(mom) == "holding_count"
    val = sb.BuilderState(universe="KOSPI", strategy_type="value", value_pbr=1.0, value_roe=10.0)
    assert sb.required_missing(val) == "holding_count"


def test_filter_none_completes_without_filters():
    """'없음'은 필터 없이 스텝을 완료한다(옵션이라 되묻지 않음)."""
    st = sb.BuilderState(universe="KOSPI", strategy_type="bollinger")
    res = _step(st, "없음")
    assert res.state.filters_asked is True
    assert res.state.trend_filter_ma is None and res.state.liquidity_min is None
    assert sb.required_missing(res.state) == "holding_count"


def test_filter_parses_trend_liquidity_rsi_combo():
    """자유 입력에서 추세·거래대금·RSI 결합을 함께 인식한다."""
    patch = sb._parse_filters("EMA200 위에서만 + 거래대금 100억 이상, RSI 30 이하")
    assert patch["trend_filter_ma"] == 200
    assert patch["liquidity_min"] == 100.0
    assert patch["rsi_filter"] == 30.0
    assert patch["filters_asked"] is True


def test_bollinger_with_trend_filter_builds_entry_filter_dsl():
    """볼린저 + EMA200 추세 필터가 entry_filters(type:filter)로 DSL에 반영된다."""
    st = sb.BuilderState(universe="KOSPI", strategy_type="bollinger", filters_asked=True,
                         trend_filter_ma=200, liquidity_min=100.0, holding_count=10,
                         rebalance_cycle="none", stop_loss_pct=10.0, risk_done=True)
    parsed = sb.build_parsed_strategy(st)
    req = to_backtest_request(parsed, resolve_symbols=False)
    by_type = [(c["type"], c["id"]) for c in req["entry"]["conditions"]]
    assert ("indicator", "bollinger_bands") in by_type
    assert ("filter", "ema") in by_type            # 추세 필터가 AND 게이트로
    assert ("filter", "trading_value") in by_type  # 거래대금 필터
    ema = next(c for c in req["entry"]["conditions"] if c["id"] == "ema")
    assert ema["params"]["mode"] == "above" and ema["params"]["period"] == 200


def test_trend_filter_flow_end_to_end():
    """볼린저 흐름에서 'EMA200 위에서만'을 고르면 trend_filter_ma가 채워진다."""
    s = sb.seed_state("볼린저 전략")
    s = _step(s, "코스피").state
    r = _step(s, "EMA200 위에서만")       # 필터 스텝
    assert r.state.trend_filter_ma == 200 and r.state.filters_asked is True
    s = _step(r.state, "10개").state
    s = _step(s, "리밸런싱 안 함").state
    res = _step(s, "10% 손절")
    assert res.status == "confirmed"
    parsed = sb.build_parsed_strategy(res.state)
    assert any(f.indicator == "ema" and f.mode == "above" for f in parsed.entry_filters)
