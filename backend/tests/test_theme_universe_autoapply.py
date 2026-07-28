"""테마 유니버스 자동 적용 — 파싱 경로 계약(FR-STR-071 ④ 개정, 사용자 결정 2026-07-25).

종전 '이 종목들로만 vs 업종 전체' 되묻기(+Phase 2 공급망 확장 칩)를 폐지하고, 테마
관련 검증 상장사를 되묻기 없이 target_symbols로 자동 설정한다. 계약:
  - 테마 큐(관련/테마 또는 복합 테마구) + 그래프가 아는 개념 + 검증 상장사 존재 시 적용.
  - 업종 근사(sector)는 해제 — 관련 종목엔 타업종이 섞여 sector 필터가 남으면
    방금 설정한 종목을 도로 걸러낸다.
  - 무엇이 어떤 근거로 설정됐는지 notice로 투명하게 알린다(침묵 적용 방지 — 규제 안전).
  - 시작일은 자르지 않는다(시점 편향은 notice 고지만 — 조용한 기간 축소 방지).
"""

from __future__ import annotations

from engine.nl_parser import ParsedStrategy, apply_theme_universe


def _parsed() -> ParsedStrategy:
    return ParsedStrategy(description="테스트")


def test_seed_theme_auto_applies_direct_companies():
    """시드 개념(HBM)은 직접 검증 상장사가 되묻기 없이 대상 종목으로 설정된다."""
    parsed = _parsed()
    notice = apply_theme_universe(parsed, "HBM 관련주로 전략 만들어줘")
    assert notice is not None and "대상 종목으로 설정했어요" in notice
    assert {"000660", "005930", "042700"} <= set(parsed.target_symbols)
    assert parsed.backtest_start_date is None  # 시작일 클램프 없음
    # 시드 개념(수동 큐레이션)은 시점 편향 고지가 붙지 않는다(first_known_date 없음)
    assert "시점 편향" not in notice


def test_no_apply_without_theme_cue_or_unknown_concept():
    parsed = _parsed()
    assert apply_theme_universe(parsed, "PER 10 이하 저평가 매수") is None
    assert apply_theme_universe(parsed, "존재하지않는신조어 관련주") is None
    assert parsed.target_symbols == []


def test_all_theme_companies_applied_without_truncation(monkeypatch):
    """[회귀 2026-07-28 '비만치료 관련주' 사고] 관련 상장사 36곳 중 심볼 앞 10곳만
    유니버스가 되던 절단 — target_symbols는 전체, 안내문 나열만 축약(외 N곳)."""
    companies = [
        {"symbol": f"{i:06d}", "name": f"종목{i}", "support": 1, "first_known_date": None}
        for i in range(36)
    ]
    # apply_theme_companies는 함수 내부에서 kg 모듈을 import한다 — 그 지점을 patch
    import engine.knowledge_graph as kg

    monkeypatch.setattr(
        kg, "theme_backtest_companies",
        lambda text: {"term": "비만치료", "companies": companies, "first_known_date": None},
    )
    parsed = _parsed()
    notice = apply_theme_universe(parsed, "비만치료 관련주 전략 만들어줘")
    assert notice is not None and "36곳" in notice and "외 26곳" in notice
    assert parsed.target_symbols == [c["symbol"] for c in companies]
