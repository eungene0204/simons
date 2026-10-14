"""전략 빌더 조건 수정 규칙(FR-SA-002e) — 진행 중 삭제(REMOVE)·선행 설정(SET-ahead)·
값 없는 변경(MODIFY 되묻기) 테스트.

빌더는 선형 설문이 아니라 편집 과정이다: 어느 단계에서든 이미 결정된 조건을
삭제("손절 빼줘")·추가("손절 10% 걸어줘")·변경("시장 바꿔줘")할 수 있어야 한다.
"""

from __future__ import annotations

from intent import strategy_builder as sb


def _mid_state(**overrides) -> sb.BuilderState:
    """골든크로스 파라미터까지 채워 보유 종목 수 질문 단계에 있는 상태."""
    base = dict(
        universe="KOSPI", strategy_type="golden_cross",
        ma_kind="sma", ma_short=5, ma_long=20, filters_asked=True,
    )
    base.update(overrides)
    return sb.BuilderState(**base)


# ─── REMOVE: 채워진 조건 삭제 ────────────────────────────────────────────────────


# ─── SET-ahead: 다른 단계에서 미리 말한 조건 캡처 ─────────────────────────────────


# ─── 값 없는 변경(MODIFY): 필드를 비워 그 질문으로 자연 복귀 ──────────────────────


# ─── 호환성 검토 ────────────────────────────────────────────────────────────────


def test_sector_change_cue_overwrites_existing_sector():
    patch = sb.parse_input("업종을 반도체로 바꿔줘", _mid_state(sector="로봇"), "holding_count")
    assert patch.get("sector") is not None
    assert patch["sector"] != "로봇"
