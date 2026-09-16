"""Symbol resolver 테스트 — 종목명 추출."""

from __future__ import annotations

import pytest

from stock_analysis.symbol_resolver import find_in_text


def test_sk_hynix_not_confused_with_inix():
    # 이닉스는 SK하이닉스에 substring으로 포함되지만, 단어 경계를 고려해 구분된다.
    refs = find_in_text("SK하이닉스 사도 될까?")
    assert len(refs) == 1
    assert refs[0].symbol == "000660"
    assert refs[0].name == "SK하이닉스"


def test_inix_alone_is_recognized():
    refs = find_in_text("이닉스 관심 있어")
    assert len(refs) == 1
    assert refs[0].symbol == "452400"
    assert refs[0].name == "이닉스"


def test_both_found_when_both_mentioned():
    refs = find_in_text("SK하이닉스와 이닉스 중 뭐가 나아?")
    assert len(refs) == 2
    symbols = {r.symbol for r in refs}
    assert "000660" in symbols  # SK하이닉스
    assert "452400" in symbols  # 이닉스


def test_samsung_electronics_recognized():
    refs = find_in_text("지금 삼성전자 사도 될까?")
    assert len(refs) == 1
    assert refs[0].symbol == "005930"
    assert refs[0].name == "삼성전자"


def test_no_match_returns_empty():
    refs = find_in_text("요즘 시장 어떤 느낌이야?")
    assert len(refs) == 0


def test_numeric_code_matched():
    refs = find_in_text("000660 살까?")
    assert len(refs) == 1
    assert refs[0].symbol == "000660"


def test_case_insensitive_matching():
    # 소문자도 매칭되어야 함
    refs = find_in_text("sk하이닉스는 어떠?")
    assert len(refs) == 1
    assert refs[0].symbol == "000660"
    assert refs[0].name == "SK하이닉스"  # 원본 이름은 대문자


def test_case_insensitive_with_josa():
    # 소문자 + 조사도 매칭
    refs = find_in_text("삼성전자는 어때?")
    assert len(refs) == 1
    assert refs[0].symbol == "005930"


def test_fuzzy_suggests_correct_stock_via_jamo_distance():
    # [FR-STR-068 오타] '삼서전자'(서↔성=종성 ㅇ 차이)는 자모거리로 삼성전자(1)가
    # 삼지전자(2)를 앞서 정답을 고른다 — 문자단위 difflib은 삼지전자를 오선택하던 함정.
    from stock_analysis.symbol_resolver import suggest_similar_stocks
    assert [r.name for r in suggest_similar_stocks("삼서전자")] == ["삼성전자"]
    assert [r.name for r in suggest_similar_stocks("카키오")] == ["카카오"]
    # 통칭(_KOREAN_ALIASES)의 오타도 등록명으로 정정한다('현디차'→현대차→현대자동차).
    assert [r.name for r in suggest_similar_stocks("현디차")] == ["현대자동차"]


def test_fuzzy_rejects_non_typos_and_vocab():
    # 확신 없는 후보는 반환하지 않는다 — 전략 어휘·업종어·짧은 토큰의 오발동 방지.
    from stock_analysis.symbol_resolver import suggest_similar_stocks
    for q in ["전략", "우량주", "저평가", "골든크로스", "모멘텀", "반도체", "포스크", "엘지화학"]:
        assert suggest_similar_stocks(q) == [], q


def test_detect_symbol_typo_clarification_reasks():
    from engine.nl_parser import detect_symbol_typo_clarification, ParsedStrategy
    q, chips = detect_symbol_typo_clarification(ParsedStrategy(description="x"), "삼서전자 전략을 만들자")
    assert q is not None and "삼성전자" in q
    assert chips == ["삼성전자 전략을 만들자"]  # 오타 토큰만 정정한 재제출 프롬프트
    # 조사가 붙은 토큰도 벗겨 매칭하고, 칩은 토큰 전체를 정정한다.
    q2, chips2 = detect_symbol_typo_clarification(ParsedStrategy(description="x"), "카키오로 골든크로스 전략")
    assert chips2 == ["카카오 골든크로스 전략"]


def test_detect_symbol_typo_no_reask_on_valid_input():
    from engine.nl_parser import detect_symbol_typo_clarification, ParsedStrategy
    # 정확 매칭 종목·업종·순수 전략 어휘는 되묻지 않는다.
    for t in ["삼성전자 전략을 만들자", "2차전지 전략을 만들자",
              "골든크로스 전략 만들어줘", "PBR 1 이하 저평가 종목"]:
        q, _ = detect_symbol_typo_clarification(ParsedStrategy(description="x"), t)
        assert q is None, t
    # 이미 종목이 해석된 경우(target_symbols)도 되묻지 않는다.
    q, _ = detect_symbol_typo_clarification(
        ParsedStrategy(description="x", target_symbols=["005930"]), "삼서전자 전략"
    )
    assert q is None


def test_symbol_typo_reask_skipped_for_etf_universe():
    """ETF 유니버스엔 '종목명'이 없다 — 자모 근접 매칭 되묻기는 전부 오발동이다.

    실측 사고(2026-07-27): "배당 ETF 중에서 …20일선을 이탈하면 청산" 요청이 '오아'·'일승'
    종목 오타 되묻기로 빠졌다(테마는 etf_theme로 이미 해석된 상태).
    """
    from engine.nl_parser import ParsedStrategy, detect_symbol_typo_clarification

    prompt = "배당 ETF 중에서 종가가 20일 이동평균선 위에 있는 상품만 4종목 담고 싶어요"
    q_stock, _ = detect_symbol_typo_clarification(
        ParsedStrategy(description="x", universe=["KOSPI"]), "카키오로 골든크로스 전략"
    )
    assert q_stock is not None  # 주식 유니버스에선 기존 동작 유지

    q_etf, chips = detect_symbol_typo_clarification(
        ParsedStrategy(description="x", universe=["ETF"], etf_theme="배당"), prompt
    )
    assert q_etf is None and chips is None


def test_symbol_typo_term_in_only_scans_llm_extracted_names():
    """[회귀 2026-07-29 '박스권 돌파' 사고] 원문 전체 토큰을 마스터에 근접 매칭하면
    일반 어절이 종목명으로 오탐된다 — "20일 고점을 **넘기는** 날"의 '넘기는'이 '삼기',
    "박스 **안으로**"의 '안으로'가 '알트'로 잡혀 사용자 문장을 통째로 오염시킨 칩이 나갔다.
    term-in 경로는 LLM이 종목명이라고 판정한 표현만 후보로 본다."""
    from engine.nl_parser import ParsedStrategy, detect_symbol_typo_clarification

    prompt = ("복잡한 지표는 아직 어려워서 최근 한 달 동안 가격이 갇혀 있던 박스권을 위로 "
              "돌파하는 종목만 사고 싶어요. KOSPI 종목 중 20일 고점을 넘기는 날 매수하고 "
              "다시 박스 안으로 내려오면 매도해 주세요. 최대 8종목, 손절은 -7%로 부탁드립니다.")
    parsed = ParsedStrategy(description="박스권 돌파 전략", universe=["KOSPI"])

    # LLM이 종목명을 뽑지 않았으면(종목 언급이 없는 전략) 되묻지 않는다.
    assert detect_symbol_typo_clarification(parsed, prompt, terms=[]) == (None, None)
    # 레거시 원문 스캔은 같은 입력에서 오탐한다 — 이 경로가 왜 레거시로 밀렸는지의 근거.
    legacy_q, _ = detect_symbol_typo_clarification(parsed, prompt)
    assert legacy_q is not None


def test_symbol_typo_term_in_still_catches_real_typos():
    """term-in으로 좁혀도 진짜 오타는 잡는다 — LLM이 '삼서전자'를 종목명으로 넘긴 경우."""
    from engine.nl_parser import ParsedStrategy, detect_symbol_typo_clarification

    parsed = ParsedStrategy(description="x")
    q, chips = detect_symbol_typo_clarification(
        parsed, "삼서전자 전략을 만들자", terms=["삼서전자"])
    assert q is not None and "삼성전자" in q
    # 칩은 원문에서 오타만 정정한 재제출 프롬프트다.
    assert chips == ["삼성전자 전략을 만들자"]


def test_symbol_typo_term_in_chip_falls_back_to_name_when_absent_from_prompt():
    """LLM이 표기를 다듬어 넘겨 원문에 그 문자열이 없으면, 치환되지 않은 원문을 그대로
    칩으로 내지 않는다(고르면 같은 질문이 반복된다) — 종목명만 낸다."""
    from engine.nl_parser import ParsedStrategy, detect_symbol_typo_clarification

    q, chips = detect_symbol_typo_clarification(
        ParsedStrategy(description="x"), "그 회사로 전략 만들어줘", terms=["삼서전자"])
    assert q is not None
    assert chips == ["삼성전자"]


def test_former_company_name_resolves_to_current_listing():
    """[2026-08-29 회귀] 구 사명 '제이콘텐트리'가 무매칭이라 종목 추가 요청이 통째로
    무시됐다(수정 레인 환각 게이트가 '지어낸 이름'으로 판정). 종목코드는 그대로이므로
    구 사명도 현재 등록 종목(콘텐트리중앙 036420)으로 해석돼야 한다."""
    from stock_analysis.symbol_resolver import find_in_text

    refs = find_in_text("제이콘텐트리 종목을 추가해줘")
    assert [(r.symbol, r.name) for r in refs] == [("036420", "콘텐트리중앙")]


def test_former_names_come_from_collected_history_not_hardcoding():
    """구 사명은 손으로 적지 않고 KRX 스냅샷 대조 산출물에서 온다
    (`scripts/build_stock_name_history.py` → `data/stock-name-history.json`).
    개별 이름을 코드에 박는 방식으로 되돌아가면 이 계약이 깨진다."""
    from stock_analysis.symbol_resolver import _KOREAN_ALIASES, _former_names, known_aliases

    former = _former_names()
    assert former.get("제이콘텐트리") == "036420"
    assert len(former) > 500  # 전수 수집물(한두 개 하드코딩이 아니다)
    assert "제이콘텐트리" not in _KOREAN_ALIASES
    assert known_aliases()["현대차"] == "005380"  # 통칭도 함께 노출


def test_former_name_never_overrides_a_current_listing_name():
    """지금 어느 상장사가 쓰는 이름은 구 사명 별칭이 가로채지 못한다 — 두 데이터 파일이
    따로 갱신되므로 읽는 쪽에서도 막는다(정본은 언제나 현재 등록명)."""
    import json

    from stock_analysis.symbol_resolver import _load_stocks, _former_names

    current = {"".join(str(r["name"]).split()).lower() for r in _load_stocks()}
    clashes = [n for n in _former_names() if "".join(n.split()).lower() in current]
    assert clashes == []


def test_former_name_aliases_are_unambiguous():
    """한 구 사명이 두 종목을 가리키면 등재하지 않는다 — 무매칭이 오해석보다 안전하다."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "stock-name-history.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    bearers: dict[str, set] = {}
    for event in data["renames"]:
        for name in (event["from"], event["to"]):
            bearers.setdefault("".join(name.split()).lower(), set()).add(event["symbol"])
    for name, symbol in data["formerNames"].items():
        key = "".join(name.split()).lower()
        assert bearers[key] == {symbol}, f"{name} → {sorted(bearers[key])}"


def test_renamed_stock_name_is_picked_up_without_restart(tmp_path, monkeypatch):
    """[2026-09-16 회귀] 명부 종목명은 매일 사명 변경을 반영해 제자리 갱신된다
    (`scripts/refresh_stock_names.py`). 해석기 캐시가 프로세스 수명이면 백엔드를 재시작할
    때까지 옛 이름('세기상사')이 유니버스 목록에 나간다 — 파일이 바뀌면 다시 읽어야 한다."""
    import json

    import stock_analysis.symbol_resolver as resolver

    stocks = tmp_path / "korea-stocks.json"
    monkeypatch.setattr(resolver, "_STOCKS_JSON_PATH", stocks)
    monkeypatch.setattr(resolver, "_NAME_HISTORY_PATH", tmp_path / "missing.json")

    stocks.write_text(json.dumps([{"symbol": "002420", "name": "세기상사"}], ensure_ascii=False),
                      encoding="utf-8")
    assert resolver.resolve_by_symbol("002420").name == "세기상사"

    stocks.write_text(json.dumps([{"symbol": "002420", "name": "우양피앤엘"}], ensure_ascii=False),
                      encoding="utf-8")
    assert resolver.resolve_by_symbol("002420").name == "우양피앤엘"
    assert [r.symbol for r in resolver.find_in_text("우양피앤엘 추가해줘")] == ["002420"]
