"""업종·테마 소속 목록 레인 — 추천 요청과 분리하는 안전 계약(FR-SA-002c-11).

`STOCK_PICK` 라벨 하나가 "뭐 살까?"(추천 요청, 거절)와 "어떤 회사들이 있어?"(소속
질문, 분류 사실)를 같은 거절로 묶던 것을 `list_scope` 직교 축으로 갈랐다.

안전 근거는 fact_metric(FR-SA-002c-9)과 같다 — LLM은 범위 표기만 추출하고 목록은
정본 데이터(섹터 지도·지식그래프)에서 결정론으로 만든다. 축이 오판해도 최악은
'소속 목록을 보여준다'이지 '이걸 사라고 말한다'가 아니다.
"""

from __future__ import annotations

import pytest

from intent import classifier, interpreter, stock_lists
from intent.schemas import QueryIntent, WorkflowStatus


def _interp(intent=QueryIntent.STOCK_PICK, **kwargs) -> interpreter.IntentInterpretation:
    return interpreter.IntentInterpretation(intent=intent, **kwargs)


# ── 정본 해석 ─────────────────────────────────────────────────────────────

def test_sector_listing_resolves_canonical_members():
    listing = stock_lists.resolve_listing("반도체")
    if listing is None:
        pytest.skip("로컬에 stock-master/섹터 지도가 없다")

    assert listing.kind == "업종"
    assert listing.scope == "반도체"
    assert len(listing.companies) > 10
    # 가나다순 — 시총·수익률순은 '위가 더 좋다'는 암시를 만든다.
    names = [name for name, _ in listing.companies]
    assert names == sorted(names)


def test_synonym_maps_to_canonical_sector():
    """'2차전지' 표기 변형도 정본('이차전지')으로 붙는다 — universe_resolver와 같은 사전."""
    listing = stock_lists.resolve_listing("2차전지")
    if listing is None:
        pytest.skip("로컬에 stock-master/섹터 지도가 없다")

    assert listing.scope == "이차전지"


@pytest.mark.parametrize("term", ["없는테마xyz", "", "   ", None, 123])
def test_unresolvable_terms_return_none(term):
    """미해석은 None — 목록을 지어내지 않는다."""
    assert stock_lists.resolve_listing(term) is None


def test_market_and_index_listings_resolve():
    """시장·지수도 소속 정본이다 — '코스피 200 지수는 약 403개' 환각(2026-08-11 실측,
    실제 200)의 결정론 대체. 표기 변형(공백·대소문자)도 흡수한다."""
    listing = stock_lists.resolve_listing("코스피200")
    if listing is None:
        pytest.skip("로컬에 kospi200-cache/stock-master가 없다")

    assert listing.kind == "지수"
    assert len(listing.companies) == 200
    for variant in ("코스피 200", "KOSPI200"):
        assert stock_lists.resolve_listing(variant).scope == "코스피200"

    kosdaq = stock_lists.resolve_listing("코스닥")
    assert kosdaq.kind == "시장"
    assert len(kosdaq.companies) > 1000


def test_prompt_output_shape_includes_market_scope():
    """출력 형식 줄에 시장/지수가 명시돼야 한다 — 규칙에 있어도 출력 형식이 '업종/테마'로
    좁으면 9B가 시장 표기를 채우지 않는다(출력 형태가 규칙보다 강하다, 2026-08-11 재확인:
    '코스피200에 몇 종목' 추출 실패가 이 줄 하나로 고쳐졌다)."""
    assert "업종/테마/시장/지수 표기" in interpreter.SYSTEM_PROMPT


# ── 게이트 성립 조건 ──────────────────────────────────────────────────────

def test_listing_requires_allowed_label():
    """STRATEGY_ADVICE에서 열면 스크리닝 조건이 목록 표시로 샌다."""
    metric, answer = classifier._resolve_stock_listing(
        _interp(intent=QueryIntent.STRATEGY_ADVICE, list_scope="반도체")
    )

    assert metric is None and answer is None


def test_listing_blocked_on_regulatory_labels():
    """규제 거절 라벨에서 열면 정형 안내가 목록으로 우회된다."""
    for intent in (QueryIntent.PERSONAL_ADVICE, QueryIntent.LIVE_TRADING):
        assert classifier._resolve_stock_listing(
            _interp(intent=intent, list_scope="반도체")
        ) == (None, None)


def test_listing_requires_a_scope():
    assert classifier._resolve_stock_listing(_interp(list_scope=None)) == (None, None)


def test_unknown_label_can_carry_a_listing():
    """'코스피200에 몇 종목?'은 라벨이 마땅치 않아 UNKNOWN으로 떨어진다 — 축은 라벨과
    별개로 성립한다(정본 매핑 + 결정론 목록이라 오판의 최악은 '소속 목록 표시')."""
    scope, answer = classifier._resolve_stock_listing(
        _interp(intent=QueryIntent.UNKNOWN, list_scope="코스피200")
    )
    if scope is None:
        pytest.skip("로컬에 kospi200-cache/stock-master가 없다")

    assert scope == "코스피200"
    assert "총 200곳" in answer


def test_unresolved_scope_keeps_existing_redirect():
    """LLM이 범위를 추출했어도 정본에 없으면 기존 열린 추천 안내 그대로다."""
    result = classifier._apply_domain_policy(
        _interp(list_scope="없는테마xyz"),
        last_symbol=None,
        query="없는테마xyz 종목 목록 보여줘",
        active_strategy=False,
        workflow_status=WorkflowStatus.IDLE,
    )

    assert result.list_scope is None
    assert "전략" in (result.suggested_reply or "")  # 기존 빌더 전환 안내


def test_open_pick_still_gets_the_redirect():
    """범위 없는 열린 추천("뭐 살까?")은 종전대로 거절 + 빌더 전환이다."""
    result = classifier._apply_domain_policy(
        _interp(),
        last_symbol=None,
        query="뭐 사야 돼?",
        active_strategy=False,
        workflow_status=WorkflowStatus.IDLE,
    )

    assert result.list_scope is None
    assert result.suggested_reply is not None


# ── 답변 문장 계약 ────────────────────────────────────────────────────────

def test_listing_answer_states_facts_without_evaluation():
    """목록 문장은 소속 사실에서 끝난다 — 선별·평가·권유 어휘가 없다."""
    listing = stock_lists.Listing(
        scope="반도체", kind="업종",
        companies=[("가나전자", "000001"), ("다라반도체", "000002")],
    )

    answer = stock_lists.listing_answer(listing)

    assert "총 2곳" in answer
    assert "가나전자(000001)" in answer
    assert "매수 추천이 아닙니다" in answer
    for banned in ("유망", "추천합니다", "주도주", "대장주", "좋은", "사세요"):
        assert banned not in answer


def test_count_only_answer_omits_the_name_list():
    """'몇 종목?'에는 종수만 답한다 — 1,800곳 시장에 40개 이름을 붙이면 소음이다.
    사실(총원·거절 문구)은 목록 답변과 동일하다."""
    companies = [(f"회사{i:03d}", f"{i:06d}") for i in range(60)]
    listing = stock_lists.Listing(scope="코스닥", kind="시장", companies=companies)

    answer = stock_lists.listing_answer(listing, count_only=True)

    assert "총 60곳" in answer
    assert "회사000" not in answer          # 이름 나열 없음
    assert "매수 추천이 아닙니다" in answer   # 거절 문구는 유지


def test_count_only_axis_flows_from_interpretation():
    """LLM이 종수 질문으로 판정하면(list_count_only) 답변도 종수형이어야 한다."""
    scope, answer = classifier._resolve_stock_listing(
        _interp(intent=QueryIntent.UNKNOWN, list_scope="코스피200", list_count_only=True)
    )
    if scope is None:
        pytest.skip("로컬에 kospi200-cache/stock-master가 없다")

    assert "총 200곳" in answer
    assert "(" not in answer.split("\n")[0].replace("(플랫폼", "")  # 종목코드 나열 없음


def test_prompt_output_shape_includes_count_flag():
    """출력 형식 줄에 list_count_only가 있어야 9B가 채운다(출력 형태가 규칙보다 강하다)."""
    assert "list_count_only" in interpreter.SYSTEM_PROMPT
    assert "21." in interpreter.SYSTEM_PROMPT


def test_listing_answer_caps_display_but_reports_total():
    """표시는 상한(40곳)으로 자르되 총원은 항상 밝힌다."""
    companies = [(f"회사{i:03d}", f"{i:06d}") for i in range(60)]
    listing = stock_lists.Listing(scope="반도체", kind="업종", companies=companies)

    answer = stock_lists.listing_answer(listing)

    assert "총 60곳" in answer
    assert "외 20곳" in answer
    assert "회사039" in answer and "회사040" not in answer


# ── 프롬프트 계약 ─────────────────────────────────────────────────────────

def test_prompt_separates_membership_from_recommendation():
    """규칙 19(소속만)·20(조건은 전략)이 게이트 누수를 막는 유일한 장치다."""
    prompt = interpreter.SYSTEM_PROMPT

    assert "list_scope" in prompt
    assert "19." in prompt and "20." in prompt
    assert "살 만한" in prompt  # 추천 혼합 배제 예시
