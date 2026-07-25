"""테마 유니버스 공급망 확장 되묻기 — KG Phase 2 파서 경로 배선(FR-STR-070 Phase 2).

계약:
  - related_universe 깊이 2가 직접 관련 종목 밖의 상장사(공급망·인프라)에 닿으면
    detect_theme_universe_clarification이 세 번째 칩(확장 종목 전체 나열)을 추가한다.
  - 확장이 없는 개념(직접 연결이 전부)은 기존 2칩 그대로 — 불필요한 선택지를 늘리지 않는다.
  - 질문 본문에 관계 근거(via의 중간 개념)를 요약 표시한다(객관적 관계 데이터, 추천 아님).
  - 확장 칩은 FR-STR-071 칩 프로토콜을 지킨다: 종목명 나열 + '종목 전체를 함께'
    ('관련주/테마' 단어 금지 — TARGET 가드), symbol_resolver로 전량 재파싱된다.
"""

from __future__ import annotations

from engine.nl_parser import (
    ParsedStrategy,
    _via_hop_label,
    detect_theme_universe_clarification,
)


def _parsed() -> ParsedStrategy:
    return ParsedStrategy(description="테스트")


def test_expansion_chip_added_for_multi_industry_theme():
    """데이터센터(직접 2사)는 깊이 2에서 전력기기·전선 등 공급망에 닿아 확장 칩이 붙는다."""
    question, chips = detect_theme_universe_clarification(
        _parsed(), "데이터센터 관련주로 전략 만들어줘"
    )
    assert question is not None and chips is not None
    assert len(chips) == 3
    # 질문 본문에 관계 근거(중간 개념) 요약이 표시된다
    assert "공급망" in question and "전력기기" in question
    # 확장 칩은 직접 관련 종목 + 공급망 종목을 모두 나열한다
    assert "삼성에스디에스" in chips[2] and "HD현대일렉트릭" in chips[2]
    assert chips[2].endswith("종목 전체를 함께 백테스트")
    # 칩 프로토콜 — TARGET 가드 단어 금지
    assert "관련주" not in chips[2] and "테마" not in chips[2]


def test_expansion_chip_round_trips_through_symbol_extraction():
    """확장 칩 텍스트는 종목명 전량이 symbol_resolver로 재파싱된다(칩 왕복 계약)."""
    from stock_analysis.symbol_resolver import find_in_text

    _, chips = detect_theme_universe_clarification(
        _parsed(), "데이터센터 관련주로 전략 만들어줘"
    )
    assert chips is not None and len(chips) == 3
    name_count = chips[2].split(" 종목 전체")[0].count(",") + 1
    assert len(find_in_text(chips[2])) == name_count


def test_no_expansion_chip_when_depth2_adds_nothing():
    """직접 연결이 전부인 개념(HBM·전고체)은 확장 칩 없이 기존 2칩을 유지한다."""
    for prompt in ("HBM 관련주 전략", "전고체 배터리 관련주"):
        question, chips = detect_theme_universe_clarification(_parsed(), prompt)
        assert question is not None and chips is not None
        assert len(chips) == 2, prompt
        assert "공급망" not in question


def test_via_hop_label_extracts_middle_concepts():
    assert _via_hop_label("데이터센터 –requires→ 전력기기 –produced_by→ HD현대일렉트릭") == "전력기기"
    assert _via_hop_label("HBM –produced_by→ SK하이닉스") == ""  # 직접 연결은 빈 라벨
    assert _via_hop_label("") == ""
