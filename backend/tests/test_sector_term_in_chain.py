"""§ 11-3 (1c′) — 미해결 업종/테마 표현의 term-in 해석 체인 (2026-07-26).

원칙: KG·검색 그라운딩은 § 3-2의 정당한 지식 조회 계층이지만, 입력은 사용자 원문이
아니라 LLM이 universe.sectors로 뽑은 짧은 표현이어야 한다. primary 초기 파스 레인은
원문 스캔(apply_theme_universe·detect_unresolved_sector_clarification·파싱 전 어휘집
학습)을 타지 않고, 이 체인이 테마 상장사 적용→검색 학습→되묻기를 담당한다.
"""

import pytest

from engine.nl_parser import (
    ParsedStrategy,
    SECTOR_REASK_QUESTION,
    THEME_NOT_FOUND_QUESTION,
)
from strategy_conversation import primary


def _theme_hit(term="bts"):
    return {
        "term": term,
        "companies": [
            {"symbol": "035900", "name": "JYP Ent."},
            {"symbol": "352820", "name": "하이브"},
        ],
        "first_known_date": None,
    }


def test_theme_companies_applied_from_term(monkeypatch):
    import engine.knowledge_graph as kg

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: _theme_hit(text))
    parsed = ParsedStrategy(description="bts 관련주 전략")
    notices: list = []

    q, s = primary._resolve_sector_terms_term_in(parsed, ["bts"], notices)

    assert q is None and s is None
    assert parsed.target_symbols == ["035900", "352820"]
    assert parsed.sector is None
    assert notices and "'bts' 관련으로 확인된 상장사" in notices[0]


def test_grounded_sector_merged_when_no_theme(monkeypatch):
    import engine.knowledge_graph as kg

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    monkeypatch.setattr(primary, "_ground_sector_term", lambda term, on_stage=None: "바이오/제약")
    parsed = ParsedStrategy(description="마운자로 관련주 전략")
    notices: list = []

    q, s = primary._resolve_sector_terms_term_in(parsed, ["마운자로"], notices)

    assert q is None
    assert parsed.sector == "바이오/제약"
    assert notices and "인터넷 검색으로 확인해" in notices[0]


def test_unresolved_term_reasks_with_sector_question(monkeypatch):
    import engine.knowledge_graph as kg
    import engine.term_grounding as tg

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    monkeypatch.setattr(primary, "_ground_sector_term", lambda term, on_stage=None: None)
    monkeypatch.setattr(tg, "lexicon_entry", lambda text, lexicon_path=None: None)
    parsed = ParsedStrategy(description="재약주 전략")
    notices: list = []

    q, s = primary._resolve_sector_terms_term_in(parsed, ["재약주"], notices)

    assert q == SECTOR_REASK_QUESTION
    assert s


def test_search_exhausted_term_gets_terminal_notice(monkeypatch):
    import engine.knowledge_graph as kg
    import engine.term_grounding as tg

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    monkeypatch.setattr(primary, "_ground_sector_term", lambda term, on_stage=None: None)
    monkeypatch.setattr(
        tg, "lexicon_entry",
        lambda text, lexicon_path=None: {"term": "리센즈", "searched_at": "2026-07-26", "sector": None},
    )
    parsed = ParsedStrategy(description="리센즈 관련주 전략")

    q, s = primary._resolve_sector_terms_term_in(parsed, ["리센즈"], [])

    assert q == THEME_NOT_FOUND_QUESTION.format(term="리센즈")
    assert s


def test_merge_learned_sector_respects_field_contract():
    parsed = ParsedStrategy(description="x")
    primary._merge_learned_sector(parsed, "반도체")
    assert parsed.sector == "반도체"
    primary._merge_learned_sector(parsed, "반도체")  # 중복 병합 없음
    assert parsed.sector == "반도체"
    primary._merge_learned_sector(parsed, "로봇")
    assert parsed.sector == ["반도체", "로봇"]
    primary._merge_learned_sector(parsed, "로봇")
    assert parsed.sector == ["반도체", "로봇"]


def test_ground_sector_term_silent_without_search_credentials(monkeypatch):
    import engine.term_grounding as tg

    monkeypatch.setattr(tg, "search_available", lambda: False)
    assert primary._ground_sector_term("마운자로") is None


def test_apply_primary_meta_carries_sector_priority():
    result = {"runtime": {}}
    primary.apply_primary_meta(result, {
        "clarification_question": SECTOR_REASK_QUESTION,
        "clarification_suggestions": ["반도체"],
        "clarification_priority": "sector_unresolved",
        "notices": [],
        "interpreter": {"mode": "primary"},
    })
    assert result["clarification_priority"] == "sector_unresolved"
    assert result["clarification_question"] == SECTOR_REASK_QUESTION


def test_interpretation_failure_result_skips_prompt_theme_scan(monkeypatch):
    """실패 보고에 원문 테마 스캔이 전략을 만들어 붙이면 실패 의미가 왜곡된다."""
    import engine.nl_parser as nl
    import main
    from main import NLParseRequest

    def _boom(parsed, user_prompt=""):
        raise AssertionError("실패 보고 경로에서 원문 테마 스캔이 호출되면 안 된다")

    monkeypatch.setattr(nl, "apply_theme_universe", _boom)
    monkeypatch.setattr(nl, "detect_unresolved_sector_clarification", _boom)

    result = main._interpretation_failure_result(
        NLParseRequest(prompt="bts 관련주 전략"), "ollama", 0.0
    )
    assert result is not None
    assert result["clarification_priority"] == "interpretation_failed"
    assert not result["parsed"]["target_symbols"]


def test_gate_uses_validator_criterion_not_kg_resolution():
    """'LCD 부품' 사고 2차(2026-07-27) 회귀 — 게이트 판정 기준은 검증기와 동일해야 한다.

    검증기(capability_validator)는 normalize_sector만 알아 'LCD 부품'을 sectors에서
    제거하는데, 게이트가 resolve_sectors(KG 층 포함)로 '해석 성공' 판정하면 그 표현이
    체인(테마 상장사 적용)에 도달하지 못하고 KG 해석값도 버려져 유니버스가 통째로
    소실된다. 정본 사전이 못 푸는 표현은 KG가 섹터를 해석할 수 있어도 체인으로 가야
    한다(테마 상장사 적용이 섹터 근사보다 우선 — FR-STR-071c)."""
    terms = primary._sector_terms_for_chain(["LCD 부품", "반도체", " ", "LCD 부품"])
    assert terms == ["LCD 부품"]  # 정본 사전 해석분(반도체)·공백·중복 제외
