"""잔여 미지원 안내 — 내부 필드명을 담은 보고는 안내하지 않는다(2026-09-20).

실측: 120B는 설정 값을 **정확히 채워 놓고도** 같은 문구를 unsupported_features에 넣는다.
그 문장에는 대개 자기가 쓴 칸 이름이 들어 있다:

  "편도 거래비용 15bp 적용 (수수료는 fee_rate 로 처리되나 편도/이중 구분 미지원)"
  "섹터별 비중 상한 25% (max_sector_weight_percent 로 처리되나, 섹터 분류 기준이 …)"

그대로 내보내면 ① 이미 반영된 설정에 "지원하지 않아 반영하지 못했어요"가 붙고
② 내부 식별자가 사용자 화면에 노출된다(레드팀 QA 20-5). 점 있는 경로(`technical.beta`)는
이미 걸러지고 있었으므로, 점 없는 밑줄 식별자를 같은 취지로 함께 건다.

프롬프트로 고치려던 시도(설정 반영 인용 채널)는 **실측에서 기각**됐다: LLM이 그 채널을
3회 모두 빈 배열로 냈고, 형태 키가 늘어난 대가로 '편입 시점은 익일 시가'가
`current_close`로 뒤집히는 회귀만 남겼다(A/B 5회로 원인 확정).
"""

from __future__ import annotations

import pytest

from strategy_conversation import primary


@pytest.mark.parametrize("feature", [
    "편도 거래비용 15bp 적용 (수수료는 fee_rate 로 처리되나 편도/이중 구분 미지원)",
    "섹터별 비중 상한 25% (max_sector_weight_percent 로 처리되나, 섹터 분류 기준이 명시되지 않음)",
    "실적 발표일 전후 초과수익률 (entry_delay_days 로만 근사)",
])
def test_reports_naming_internal_fields_are_not_announced(feature):
    assert primary.field_name_matcher().search(feature)


@pytest.mark.parametrize("feature", [
    "공매도로 헤지한다",
    "달러 중립 포트폴리오",
    "윈저라이즈 처리",
    "레버리지 2배",
])
def test_plain_korean_reports_are_still_announced(feature):
    """내부 이름이 없는 진짜 미지원 보고는 그대로 안내된다(조용한 소실 금지)."""
    assert not primary.field_name_matcher().search(feature)


def test_single_english_word_is_not_treated_as_a_field_name():
    """밑줄이 없는 평범한 영단어는 식별자가 아니다."""
    assert not primary.field_name_matcher().search("Winsorize 처리는 지원하지 않습니다")
