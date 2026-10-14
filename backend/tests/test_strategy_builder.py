"""Strategy Builder Mode 상태 머신 테스트.

[규제 안전] 열린 종목 추천 전환 직후 빌더 대화가 짧은 답변을 전략 필드로 누적하고,
완성 시 요약·확정·합성까지 거절 없이 이어지는지 검증한다(명세 핵심 케이스 1~4 포함).
"""

from __future__ import annotations

import pytest

from engine import strategy_slots
from intent import strategy_builder as sb
from intent.scope import OFFTOPIC_REFUSAL

# 질문 문구의 정본은 engine.strategy_slots 하나다(2026-08-16) — 테스트도 문구를 베끼지
# 않고 정본에서 가져온다. 문구 안의 낱말("청산 조건")로 어느 질문인지 판정하면 정본이
# 표현을 바꾸는 순간 단정이 조용히 헛돈다.
_RISK_QUESTION = strategy_slots.builder_question("risk")[0]
_REBALANCE_QUESTION = strategy_slots.slot_question(strategy_slots.REBALANCING)[0]
_ENTRY_QUESTION = strategy_slots.slot_question(strategy_slots.ENTRY)[0]


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


# ─── 명세 핵심 케이스 1~4 ─────────────────────────────────────────────────────────


def test_blank_input_shows_opening_question_without_mutation():
    """빌더 진입 직후 빈 입력 → 상태 변화 없이 첫 질문(시장 선택)을 띄운다.

    후속 입력을 기다리지 않고 빌더의 첫 질문을 능동적으로 보여주는 경로가 의존한다.
    """
    res = _step(sb.BuilderState(), "")
    assert res.status == "collecting"
    assert res.state == sb.BuilderState()  # 아무것도 채우지 않는다
    assert "시장" in res.reply
    assert res.suggestions == ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체", "ETF"]


def test_blank_input_does_not_complete_partial_risk_state():
    """청산 조건만 남은 상태에서 빈 입력이 risk_done을 켜 전략을 잘못 완성시키지 않는다."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum",
                            lookback_days=63, holding_count=10, rebalance_cycle="weekly")
    res = _step(state, "")
    assert res.status == "collecting"
    assert res.state.risk_done is False
    assert res.reply.endswith(_RISK_QUESTION)


def test_entry_step_uses_canonical_chips_bound_to_values():
    """매수 조건 단계의 칩은 정본 목록 그대로이고, 클릭은 결속된 값으로 적용된다.

    [2026-08-16] 예전에는 빌더가 전략 유형 이름 칩('모멘텀'·'골든크로스')을 따로 냈고
    클릭을 원문처럼 다시 해석했다 — 표기가 겹쳐 'MACD 골든크로스 매수'가 골든크로스로,
    '골든크로스(5일/20일)'의 5가 모멘텀 기준 기간으로 새고, 재무 칩은 아무 유형에도 안
    걸려 같은 질문이 반복됐다. 결속표는 그 재해석을 없앤다.
    """
    state = sb.BuilderState(universe="KOSPI")
    _, suggestions = sb.next_question(state)
    assert suggestions == strategy_slots.entry_chips(["KOSPI"])

    expected = {
        "골든크로스(5일/20일) 발생 시 매수": ("golden_cross", {"ma_short": 5, "ma_long": 20}),
        "MACD 골든크로스 매수": ("macd", {"macd_mode": "crossover"}),
        "RSI 30 이하에서 매수": ("rsi", {"rsi_oversold": 30.0, "rsi_overbought": 70.0}),
        "20일 고점 돌파 시 매수": ("breakout", {"lookback_days": 20}),
        "최근 3개월 수익률 상위 매수": ("momentum", {"lookback_days": 63}),
        # 빌더 상태가 표현할 수 없는 재무 조건은 자유 서술로 넘겨 파서 레인이 처리한다 —
        # 예전처럼 아무것도 못 받고 같은 질문을 반복하지 않는다.
        "PER 10 이하": ("custom", {"entry_rule": "PER 10 이하"}),
        "ROE 15% 이상": ("custom", {"entry_rule": "ROE 15% 이상"}),
    }
    for chip, (stype, fields) in expected.items():
        result = _step(sb.BuilderState(universe="KOSPI"), chip)
        assert result.state.strategy_type == stype, chip
        for name, value in fields.items():
            assert getattr(result.state, name) == value, f"{chip} / {name}"


def test_entry_step_excludes_chips_the_strategy_cannot_express():
    """성립하지 않는 선택지만 정본에서 뺀다 — 목록을 따로 만들지 않는다."""
    etf = sb.next_question(sb.BuilderState(universe="ETF"))[1]
    assert "PER 10 이하" not in etf and "ROE 15% 이상" not in etf   # ETF엔 기업 재무제표가 없다
    assert "골든크로스(5일/20일) 발생 시 매수" in etf


# ─── 전체 흐름: 진입 → 완성 → 확정 → 합성 ──────────────────────────────────────────


# ─── 시드(빌더 진입 시 원본 메시지 선반영) ──────────────────────────────────────────


def test_is_empty_gates_seeding():
    assert sb.is_empty(sb.BuilderState()) is True
    assert sb.is_empty(sb.BuilderState(universe="KOSPI")) is False


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


def test_sector_llm_prompt_instructs_typo_correction():
    """LLM 섹터 프롬프트가 명백한 오타를 교정하도록 지시한다(재약주→제약주 예시 포함)."""
    prompt = sb._sector_llm_prompt()
    assert "오타" in prompt and "재약주" in prompt


def test_sector_reask_optout_proceeds_without_notice():
    """되묻기에 '업종 상관없음'으로 답하면 안내 없이 업종 제한 없이 진행한다."""
    state = sb.seed_state("메타버스주 관련 전략을 만들어보자")
    first = sb.step(state, "", sector_resolver=lambda _t: None)
    second = sb.step(first.state, "업종 상관없음", sector_resolver=lambda _t: None)
    assert second.state.sector is None
    assert second.state.sector_unresolved is False
    assert "지원 목록에 없어" not in second.reply  # 명시적 opt-out엔 강등 안내 생략


# ─── 복합 테마구·테마 유니버스(FR-STR-071) ────────────────────────────────────────


def test_weak_hint_failure_clears_silently():
    """약한 힌트는 해석 실패 시 되묻기·안내 없이 조용히 해제된다(오탐 UX 가드)."""
    state = sb.seed_state("소부장 전략을 만들자")
    r = sb.step(state, "", sector_resolver=lambda _t: None)
    assert r.state.sector_unresolved is False and r.state.sector_hint is None
    assert "다시 알려주시겠어요" not in r.reply
    assert "지원 목록에 없어" not in r.reply
    assert "어떤 시장" in r.reply  # 곧바로 일반 질문 진행


@pytest.fixture
def learned_theme_graph(tmp_path, monkeypatch):
    """'반도체 소부장'이 관련 상장사(verified)와 함께 학습된 어휘집으로 지식그래프를 구성한다."""
    import json as _json

    from engine import knowledge_graph as kg

    lexicon = tmp_path / "term_lexicon.json"
    lexicon.write_text(_json.dumps({
        "반도체소부장": {
            "term": "반도체 소부장",
            "definition": "반도체 소재·부품·장비 산업",
            "sector": "반도체",
            "sources": [], "searched_at": "2026-07-25T00:00:00+00:00",
            "edges": [
                {"type": "related_company", "target": "company:005290",
                 "target_name": "동진쎄미켐", "support": 2, "status": "verified",
                 "evidence": [], "first_known_date": "2020-03-01"},
                {"type": "related_company", "target": "company:240810",
                 "target_name": "원익IPS", "support": 2, "status": "verified",
                 "evidence": [], "first_known_date": "2021-05-02"},
            ],
        }
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    kg._CACHED = None
    yield lexicon
    kg._CACHED = None


def test_theme_patch_uses_all_companies_without_truncation():
    """[회귀 2026-07-28 '비만치료 관련주' 사고] 빌더 레인도 관련 상장사를 종수 상한으로
    자르지 않는다 — theme_symbols는 전체, theme_label은 synthesize_prompt 재파싱이
    종목명 나열로 다시 잡으므로 전체 이름이어야 한다."""
    companies = [{"symbol": f"{i:06d}", "name": f"종목{i}"} for i in range(36)]
    patch = sb._theme_patch(
        {"term": "비만치료", "companies": companies, "first_known_date": None}
    )
    assert patch["theme_symbols"] == [c["symbol"] for c in companies]
    assert patch["theme_label"] == ", ".join(c["name"] for c in companies)
    assert len(patch["theme_candidates"]) == 36


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


def test_parse_strategy_type_recognizes_profit_phrasing():
    assert sb._parse_strategy_type("수익률이 좋았던 종목") == "momentum"
    assert sb._parse_strategy_type("많이 오른 종목") == "momentum"


def test_parse_lookback_weeks():
    assert sb._parse_lookback("최근 1주일")["lookback_days"] == 5
    assert sb._parse_lookback("2주")["lookback_days"] == 10


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


def test_custom_entry_rule_does_not_misread_bare_threshold_as_count():
    """진입 서술의 맨숫자(RSI 30)는 보유 수로 오인하지 않는다(명시적 개/종목 접미사만 인정)."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="custom")
    res = _step(state, "RSI가 30 이하로 떨어지면 매수")
    assert res.state.holding_count is None


def test_holding_count_step_offers_only_answer_chips():
    """보유 수 질문의 칩은 **답**만이다 — '직접 입력'은 채팅창을 다시 여는 UI 토글이라
    프론트(withBuilderNavigationSuggestions)가 붙인다. 백엔드 정본 표에 넣으면 프론트가
    한 번 걷어내고 다시 붙이는 왕복이 되고, 표의 뜻도 '답의 목록'에서 흐려진다."""
    momentum = sb.BuilderState(universe="KOSPI", strategy_type="momentum", lookback_days=63)
    # 볼린저는 특화 파라미터가 없고 옵션 필터도 물었으면(filters_asked) 보유 종목 수로 넘어간다.
    bollinger = sb.BuilderState(universe="KOSPI", strategy_type="bollinger", filters_asked=True)
    for state in (momentum, bollinger):
        _, suggestions = sb.next_question(state)
        assert sb.required_missing(state) == "holding_count"
        assert "직접 입력" not in suggestions
        assert all("종목" in chip for chip in suggestions)


# ─── 청산 조건(손절·익절·트레일링·보유기간) 단계 ─────────────────────────────────────

def _ready_for_risk() -> sb.BuilderState:
    """리밸런싱까지 채워 청산 조건만 남은 상태."""
    return sb.BuilderState(universe="KOSPI", strategy_type="momentum",
                           lookback_days=63, holding_count=10, rebalance_cycle="weekly")


def test_risk_step_offered_after_rebalance():
    """리밸런싱을 채우면 청산 조건 질문이 칩과 함께 제시된다(청산 조건은 필수)."""
    from engine import strategy_slots

    msg, suggestions = sb.next_question(_ready_for_risk())
    assert msg.endswith(strategy_slots.builder_question("risk")[0])
    assert "-10% 손절" in suggestions
    # 청산 조건은 필수이므로 '청산 조건 없음' 칩은 제공하지 않는다.
    assert "청산 조건 없음" not in suggestions


def test_risk_step_offers_only_answer_chips():
    """청산 조건 질문의 칩도 답만이다 — '직접 입력'은 프론트가 붙이는 UI 토글이다."""
    _, suggestions = sb.next_question(_ready_for_risk())
    assert "직접 입력" not in suggestions
    assert suggestions[-1] == "최고가 대비 10% 하락 시 청산"


# ─── 전략별 특화 빌더(STATE_SPECIFIC_STRATEGY_BUILDER) ──────────────────────────────

from engine.strategy_converter import to_backtest_request  # noqa: E402


def test_specific_type_recognition_rsi_stoch_cci():
    """이름으로 지목한 특화 전략 유형을 인식한다. 'RSI'는 전용 rsi(과매도 반등은 mean_reversion)."""
    assert sb._parse_strategy_type("RSI 전략 만들어줘") == "rsi"
    assert sb._parse_strategy_type("스토캐스틱 전략") == "stochastic"
    assert sb._parse_strategy_type("CCI 전략") == "cci"
    # '과매도 반등'은 여전히 프리셋 mean_reversion(RSI라는 단어가 없음).
    assert sb._parse_strategy_type("과매도 반등 전략") == "mean_reversion"


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


# ─── ETF 유니버스 (2026-07-19) ────────────────────────────────────────────────


def test_parse_universe_etf_takes_priority_over_market():
    assert sb._parse_universe("ETF로 할게") == "ETF"
    # 상품 유형이 시장 언급보다 우선 — "코스피 ETF"도 ETF 유니버스.
    assert sb._parse_universe("코스피 ETF") == "ETF"


def test_etf_universe_hides_value_strategy_option():
    state = sb.BuilderState(universe="ETF")
    msg, chips = sb.next_question(state)
    assert "가치 전략" not in msg
    assert "저평가 가치주" not in chips


def test_etf_value_type_not_applied():
    # 가치 전략을 답해도 채우지 않고 같은 질문을 다시 한다(ETF엔 재무지표 없음).
    state = sb.BuilderState(universe="ETF")
    patch = sb.parse_input("저평가 가치주", state, "strategy_type")
    assert patch.get("strategy_type") is None
    # 주식 유니버스에서는 정상 인식된다(가드가 과확장되지 않음).
    stock_state = sb.BuilderState(universe="KOSPI")
    patch2 = sb.parse_input("저평가 가치주", stock_state, "strategy_type")
    assert patch2.get("strategy_type") == "value"


def test_etf_builder_dsl_universe():
    state = sb.BuilderState(
        universe="ETF", strategy_type="golden_cross",
        ma_kind="sma", ma_short=5, ma_long=20,
        holding_count=5, rebalance_cycle="monthly",
        stop_loss_pct=10.0, risk_done=True, filters_asked=True,
    )
    parsed = sb.build_parsed_strategy(state)
    assert parsed is not None
    assert parsed.universe == ["ETF"]
    assert parsed.sector is None


# ─── 퍼징 QA(2026-07-24, docs/builder_fuzz_qa_report.md BF-01~18) 회귀 ────────────

def _full_state(**kw) -> sb.BuilderState:
    base = dict(universe="KOSPI", strategy_type="momentum", lookback_days=63,
                lookback_label="3개월", holding_count=10, rebalance_cycle="monthly")
    base.update(kw)
    return sb.BuilderState(**base)


def test_bf02_negated_cancel_not_cancelled():
    """[BF-02] '취소하지 말고 계속해'는 취소가 아니다. 순수 취소어는 여전히 취소."""
    assert sb.detect_control("취소하지 말고 계속해") is None
    assert sb.detect_control("취소") == "cancel"
    assert sb.detect_control("그만할래") == "cancel"
    assert sb.detect_control("그냥 관두자") == "cancel"


def test_bf13_korean_percent_notation_deterministic():
    """[BF-13] '10프로'·'10퍼센트'·'10퍼'를 LLM 없이 결정적으로 인식한다."""
    assert sb._parse_risk("손절 10프로").get("stop_loss_pct") == 10.0
    patch = sb._parse_risk("손절 10퍼센트 익절 20퍼")
    assert patch.get("stop_loss_pct") == 10.0 and patch.get("take_profit_pct") == 20.0


# ─── 신규 상장(IPO) 유니버스 (FR-STR-073) ─────────────────────────────────────
# 실측 사고(2026-07-29): "2026년 신규 상장 종목 투자 전략"이 빌더로 넘어가면서 제한이
# 통째로 사라져 코스피·코스닥 전 종목(삼양홀딩스·CJ대한통운 등)이 매매됐다. 빌더는
# LLM 인터프리터의 해석을 BuilderState로 이어받아 최종 DSL까지 실어야 한다.

def test_apply_parsed_seed_inherits_listing_window():
    state = sb.apply_parsed_seed(sb.BuilderState(), {
        "new_listing_only": True, "listing_from": "2026-01-01", "listing_to": "2026-12-31",
    })
    assert state.new_listing_only is True
    assert (state.listing_from, state.listing_to) == ("2026-01-01", "2026-12-31")


def test_apply_parsed_seed_keeps_concept_when_period_pending():
    # 대상 시기를 되묻는 중이면 구간 없이 개념만 이어받는다 — 여기서 버리면 다음 턴에 증발한다.
    state = sb.apply_parsed_seed(sb.BuilderState(), {"new_listing_only": True})
    assert state.new_listing_only is True
    assert state.listing_from is None


def test_builder_asks_listing_period_after_universe():
    state = sb.BuilderState(new_listing_only=True, universe="KOSPI_KOSDAQ")
    assert sb.required_missing(state) == "listing_period"
    question, chips = sb.next_question(state, just_filled={"universe"})
    assert "어느 시기" in question
    assert any("년 상장" in chip for chip in chips)


def test_parse_listing_period_year_cohort():
    assert sb._parse_listing_period("2026년 상장") == {
        "listing_from": "2026-01-01", "listing_to": "2026-12-31",
    }
    # '이후/부터'가 붙으면 상한이 없다.
    assert sb._parse_listing_period("2025년 이후 상장") == {
        "listing_from": "2025-01-01", "listing_to": None,
    }


def test_parse_listing_period_relative_window():
    from datetime import date, timedelta

    result = sb._parse_listing_period("최근 1년 내 상장")
    assert result["listing_to"] is None
    assert result["listing_from"] == (date.today() - timedelta(days=365)).isoformat()


def test_parse_listing_period_rejects_unrecognized_and_future():
    from datetime import date

    assert sb._parse_listing_period("아무거나") is None
    assert sb._parse_listing_period("0개월") is None
    # 맨숫자는 연도인지 기간인지 모호해 해석하지 않는다.
    assert sb._parse_listing_period("2026") is None
    # 아직 오지 않은 해엔 상장 종목이 존재할 수 없다.
    assert sb._parse_listing_period(f"{date.today().year + 1}년 상장") is None


def test_build_parsed_strategy_carries_listing_window():
    state = sb.BuilderState(
        universe="KOSPI_KOSDAQ", new_listing_only=True,
        listing_from="2026-01-01", listing_to="2026-12-31",
        strategy_type="golden_cross", ma_kind="sma", ma_short=5, ma_long=20,
        holding_count=10, rebalance_cycle="none", risk_done=True,
    )
    parsed = sb.build_parsed_strategy(state)
    assert parsed.new_listing_only is True
    assert (parsed.listing_from, parsed.listing_to) == ("2026-01-01", "2026-12-31")
    # custom 유형은 이 문장이 다시 파싱되므로 제한이 문장에도 남아야 한다.
    assert "신규 상장" in parsed.description and "2026년 상장" in parsed.description


def test_new_listing_not_applied_to_designated_symbols():
    # 지정 종목/테마 목록 모드는 사용자가 종목을 직접 고른 것이라 상장 시기로 거르지 않는다.
    state = sb.BuilderState(
        single_symbol="005930", single_label="삼성전자",
        new_listing_only=True, listing_from="2026-01-01", listing_to="2026-12-31",
        strategy_type="golden_cross", ma_kind="sma", ma_short=5, ma_long=20, risk_done=True,
    )
    parsed = sb.build_parsed_strategy(state)
    assert parsed.new_listing_only is False
    assert parsed.listing_from is None


def test_etf_universe_skips_listing_period_question():
    # ETF엔 상장일 기반 판정이 없다 — 묻지도 않고 DSL에도 싣지 않는다.
    state = sb.BuilderState(new_listing_only=True, universe="ETF")
    assert sb.required_missing(state) == "strategy_type"
    state = state.model_copy(update={
        "strategy_type": "golden_cross", "ma_kind": "sma", "ma_short": 5, "ma_long": 20,
        "holding_count": 5, "rebalance_cycle": "none", "risk_done": True,
    })
    parsed = sb.build_parsed_strategy(state)
    assert parsed.new_listing_only is False
    assert parsed.listing_from is None


# ── /us 빌더: 미국 유니버스 칩·조립·영어 확인 문장 (2026-09-03) ────────────────────

def test_builder_us_lane_offers_us_universes_and_english_acks():
    """/us(en)에서 빌더는 미국 유니버스 6종을 묻고 S&P500 기본값으로 조립하며, 확인 문장은
    영어다(질문 문단은 정본 한국어 — 프론트가 문단 단위 t()로 옮긴다). 종전엔 코스피 칩과
    KOSPI 기본값으로 한국 전략을 조립했다."""
    import ui_language
    from intent import strategy_builder as sb

    with ui_language.bind("en"):
        first = sb.step(sb.BuilderState(), "")
        assert first.suggestions == ["S&P500", "나스닥100", "나스닥", "다우30", "미국 전체", "미국 ETF"]
        after = sb.step(first.state, "S&P500")
        assert after.state.universe == "SP500"
        assert after.reply.startswith("Great. I'll target S&P 500.")
        parsed = sb.build_parsed_strategy(sb.BuilderState(strategy_type="golden_cross", ma_short=5, ma_long=20,
                                                          holding_count=10, stop_loss_pct=10, risk_done=True))
        assert parsed is not None and parsed.universe == ["SP500"]


def test_rsi_full_flow_builds_dsl_with_params():
    """RSI 전용 상태(기간·과매도·과매수 수집 완료)가 DSL에 정확히 반영된다."""
    state = sb.BuilderState(
        universe="KOSPI", strategy_type="rsi", rsi_period=9, rsi_oversold=25.0, rsi_overbought=75.0,
        filters_asked=True, holding_count=10, rebalance_cycle="monthly",
        stop_loss_pct=10.0, take_profit_pct=20.0, risk_done=True,
    )
    assert sb.required_missing(state) is None
    parsed = sb.build_parsed_strategy(state)
    req = to_backtest_request(parsed, resolve_symbols=False)
    entry = req["entry"]["conditions"][0]
    exit_ = req["exit"]["conditions"][0]
    assert entry["id"] == "rsi" and entry["params"]["period"] == 9 and entry["params"]["value"] == 25.0
    assert exit_["id"] == "rsi" and exit_["params"]["value"] == 75.0
    assert req["risk"]["stop_loss_pct"] == 10.0 and req["risk"]["take_profit_pct"] == 20.0
