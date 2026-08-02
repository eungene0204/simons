"""테마 유니버스 자동 적용 — 파싱 경로 계약(FR-STR-071 ④ 개정, 사용자 결정 2026-07-25).

종전 '이 종목들로만 vs 업종 전체' 되묻기(+Phase 2 공급망 확장 칩)를 폐지하고, 테마
관련 검증 상장사를 되묻기 없이 target_symbols로 자동 설정한다. 계약:
  - 테마 큐(관련/테마 또는 복합 테마구) + 그래프가 아는 개념 + 검증 상장사 존재 시 적용.
  - 업종 근사(sector)는 해제 — 관련 종목엔 타업종이 섞여 sector 필터가 남으면
    방금 설정한 종목을 도로 걸러낸다.
  - 무엇이 어떤 근거로 설정됐는지 요약 문구를 반환한다 — 단 사용자 notices에는 싣지
    않는다(2026-08-02 사용자 지시: 요약 카드가 유니버스 종목을 이미 표시. 반환 문구는
    적용 신호·진단용으로 유지되며 이 파일이 그 구성을 검증한다).
  - 시작일은 자르지 않는다(조용한 기간 축소 방지).
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


# ── § 16 검증 상태 노출 (2026-07-31) ────────────────────────────────────────────
# kg_research 관계 원장이 있는 종목만 direct/verified 구분이 가능하다. 원장이 없는
# 종목(카탈로그·시드)은 기존 문구 그대로 — 새 판정을 추가하지 않는다.

def _company(symbol, name, relation=None):
    return {"symbol": symbol, "name": name, "support": 1,
            "first_known_date": None, "relation": relation}


def test_notice_discloses_the_split_between_direct_and_thematic_evidence(monkeypatch):
    """직접·교차검증 종목과 간접·미검증 종목이 섞이면 그 구성을 밝힌다."""
    import engine.knowledge_graph as kg

    companies = [
        _company("000001", "직접공급사",
                 relation={"direct": True, "verified": True}),
        _company("000002", "테마관련사",
                 relation={"direct": False, "verified": True}),
    ]
    monkeypatch.setattr(
        kg, "theme_backtest_companies",
        lambda text: {"term": "테스트테마", "companies": companies, "first_known_date": None},
    )
    parsed = _parsed()
    notice = apply_theme_universe(parsed, "테스트테마 관련주 전략")
    assert notice is not None
    assert "사업 관계가 확인된 1곳" in notice
    assert "간접 연관이거나 근거가 아직 검증되지 않은 1곳" in notice


def test_notice_stays_unchanged_when_no_relation_ledger_exists(monkeypatch):
    """관계 원장이 없는 종목(카탈로그·시드)뿐이면 문구를 바꾸지 않는다."""
    import engine.knowledge_graph as kg

    companies = [_company("000001", "카탈로그종목")]  # relation=None
    monkeypatch.setattr(
        kg, "theme_backtest_companies",
        lambda text: {"term": "테스트테마", "companies": companies, "first_known_date": None},
    )
    parsed = _parsed()
    notice = apply_theme_universe(parsed, "테스트테마 관련주 전략")
    assert notice is not None
    assert "이 중" not in notice


def test_notice_stays_unchanged_when_all_relations_are_direct_and_verified(monkeypatch):
    """전부 직접·교차검증이면 구분해서 얻을 정보가 없다 — 문구를 늘리지 않는다."""
    import engine.knowledge_graph as kg

    companies = [
        _company("000001", "공급사1", relation={"direct": True, "verified": True}),
        _company("000002", "공급사2", relation={"direct": True, "verified": True}),
    ]
    monkeypatch.setattr(
        kg, "theme_backtest_companies",
        lambda text: {"term": "테스트테마", "companies": companies, "first_known_date": None},
    )
    parsed = _parsed()
    notice = apply_theme_universe(parsed, "테스트테마 관련주 전략")
    assert notice is not None
    assert "이 중" not in notice


def test_relation_evidence_disclosure_is_a_pure_text_helper():
    """판정을 새로 하지 않는다 — kg_research가 이미 계산한 direct/verified를 읽기만 한다."""
    from engine.nl_parser import _relation_evidence_disclosure

    assert _relation_evidence_disclosure([]) is None
    assert _relation_evidence_disclosure([_company("1", "a")]) is None
    result = _relation_evidence_disclosure([
        _company("1", "a", relation={"direct": True, "verified": True}),
        _company("2", "b", relation={"direct": True, "verified": False}),
    ])
    assert result == "사업 관계가 확인된 1곳 · 테마 성격의 간접 연관이거나 근거가 아직 검증되지 않은 1곳"


# ── 시장 제약 필터 (2026-08-02) ─────────────────────────────────────────────────
# 지정 종목 모드는 universe 시장이 실행에 반영되지 않는다(변환기가 target_symbols
# 우선) — "코스피에만 속한 종목으로 변경" 요청이 무변경으로 끝나던 사고. 테마 유래
# 종목만 종목 마스터(korea-stocks.json) 정본 조회로 결정론 필터링한다.

def _theme_parsed(**overrides) -> ParsedStrategy:
    base = dict(
        description="HBM 관련주 전략",
        universe=["KOSPI"],
        # 삼성전자(005930)=KOSPI, 고영(098460)=KOSDAQ — 정본 시장 소속 고정 표본
        target_symbols=["005930", "098460"],
        theme_universe="HBM",
    )
    base.update(overrides)
    return ParsedStrategy(**base)


def test_market_filter_keeps_only_members_of_single_market():
    from engine.nl_parser import filter_target_symbols_by_market

    parsed = _theme_parsed()
    note = filter_target_symbols_by_market(parsed)
    assert note is not None and "KOSPI" in note
    assert parsed.target_symbols == ["005930"]
    assert parsed.theme_universe == "HBM"  # 출처 표기는 보존된다(테마 교체 판정 근거)


def test_market_filter_never_touches_user_specified_symbols():
    """직접 지목 종목(theme_universe=None)은 시장 제약보다 우선한다."""
    from engine.nl_parser import filter_target_symbols_by_market

    parsed = _theme_parsed(theme_universe=None)
    assert filter_target_symbols_by_market(parsed) is None
    assert parsed.target_symbols == ["005930", "098460"]


def test_market_filter_noop_when_universe_covers_both_markets():
    from engine.nl_parser import filter_target_symbols_by_market

    parsed = _theme_parsed(universe=["KOSPI", "KOSDAQ"])
    assert filter_target_symbols_by_market(parsed) is None
    assert parsed.target_symbols == ["005930", "098460"]


def test_market_filter_refalls_back_to_full_theme_on_market_switch(monkeypatch):
    """[회귀 2026-08-02 2차 — "미안해 코피닥 종목만"] 코스피로 좁힌 목록에서 코스닥으로
    바꾸면 현재 목록엔 코스닥이 0곳이다 — 목록의 출처인 테마 전체 구성으로 되돌아가
    다시 좁힌다(시장 전환이 단방향 손실이 되지 않게)."""
    import engine.knowledge_graph as kg
    from engine.nl_parser import filter_target_symbols_by_market

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: {
        "term": "HBM",
        "companies": [
            {"symbol": "005930", "name": "삼성전자", "support": 1, "first_known_date": None},
            {"symbol": "098460", "name": "고영", "support": 1, "first_known_date": None},
        ],
        "first_known_date": None,
    })
    parsed = _theme_parsed(universe=["KOSDAQ"], target_symbols=["005930"])
    note = filter_target_symbols_by_market(parsed)
    assert note is not None and "KOSDAQ" in note
    assert parsed.target_symbols == ["098460"]  # 테마 전체에서 코스닥만


def test_market_filter_does_not_requery_when_current_list_has_members():
    """현재 목록에 해당 시장 종목이 남아 있으면 테마 재조회 없이 현재 목록만 좁힌다 —
    사용자가 수동으로 줄인 목록을 필터가 도로 되살리지 않는다."""
    from engine.nl_parser import filter_target_symbols_by_market

    parsed = _theme_parsed()  # 005930(KOSPI)·098460(KOSDAQ), universe=["KOSPI"]
    filter_target_symbols_by_market(parsed)
    # 실파일 HBM 테마의 다른 KOSPI 종목(SK하이닉스 등)이 되살아나면 안 된다
    assert parsed.target_symbols == ["005930"]


def test_market_filter_refuses_to_empty_the_list(monkeypatch):
    """테마 전체에도 해당 시장 종목이 없으면 적용하지 않는다 — 조용한 빈 전략 방지.
    반영 불가 판정은 unapplied_market_constraint가 답한다(호출자가 전략 유지+안내)."""
    import engine.knowledge_graph as kg
    from engine.nl_parser import filter_target_symbols_by_market, unapplied_market_constraint

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: {
        "term": "HBM",
        "companies": [
            {"symbol": "005930", "name": "삼성전자", "support": 1, "first_known_date": None},
        ],
        "first_known_date": None,
    })
    parsed = _theme_parsed(universe=["KOSDAQ"], target_symbols=["005930"])
    assert filter_target_symbols_by_market(parsed) is None
    assert parsed.target_symbols == ["005930"]
    assert unapplied_market_constraint(parsed) == "KOSDAQ"
    # 적용 가능한 상태에서는 미반영 판정이 나오면 안 된다
    applied = _theme_parsed()
    assert unapplied_market_constraint(applied) is None


def test_theme_apply_respects_single_market_universe(monkeypatch):
    """생성 경로 — "코스피에 상장된 HBM 관련주"는 테마 적용 시점에 시장이 좁혀진다."""
    import engine.knowledge_graph as kg

    companies = [
        {"symbol": "005930", "name": "삼성전자", "support": 1, "first_known_date": None},
        {"symbol": "098460", "name": "고영", "support": 1, "first_known_date": None},
    ]
    monkeypatch.setattr(
        kg, "theme_backtest_companies",
        lambda text: {"term": "HBM", "companies": companies, "first_known_date": None},
    )
    parsed = ParsedStrategy(description="테스트", universe=["KOSPI"])
    notice = apply_theme_universe(parsed, "HBM 관련주 전략 만들어줘")
    assert notice is not None
    assert parsed.target_symbols == ["005930"]
