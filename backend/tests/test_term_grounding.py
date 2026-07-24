"""용어 그라운딩(engine/term_grounding) — 검색 학습·어휘집 캐시·게이트 검증(FR-STR-069).

핵심 계약:
  - 같은 용어를 두 번 검색하지 않는다(성공/매핑불가 모두 어휘집 캐시).
  - 검색 자체가 실패한 경우엔 캐시하지 않는다(복구 후 재시도 가능).
  - LLM 출력 섹터는 normalize_sector 게이트를 통과해야 한다(목록 밖 이름 → None).
"""

from __future__ import annotations

import json

import pytest

from engine.term_grounding import _scan_lexicon, general_facts_block, resolve_sector


class _ChatStub:
    """(system, user, *, max_tokens) 관례의 chat 스텁 — 프롬프트 내용으로 응답을 고른다."""

    def __init__(self, term: str | None, ground: dict | None, edges: list | None = None):
        self.term = term
        self.ground = ground
        self.edges = edges
        self.calls = 0

    def __call__(self, system_prompt: str, user_msg: str, *, max_tokens: int = 400) -> str:
        self.calls += 1
        if "추출하는 도구" in system_prompt:
            return json.dumps({"term": self.term})
        if "관계를 고르는 도구" in system_prompt:
            return json.dumps({"edges": self.edges or []})
        return json.dumps(self.ground or {})


class _SearchStub:
    def __init__(self, results):
        self.results = results
        self.calls = 0

    def __call__(self, term: str):
        self.calls += 1
        return self.results


_SNIPPETS = [
    {"title": "ESS(에너지 저장 시스템)", "description": "전력을 저장했다가 필요할 때 공급하는 시스템",
     "link": "https://example.com/ess"},
]


def test_grounding_learns_term_and_never_searches_twice(tmp_path):
    # 검색 학습 경로 검증이 목적이므로 지식그래프 시드(FR-STR-070)에 없는 용어를 쓴다 —
    # 시드 개념(ESS·SMR 등)은 ①b 그래프 단계가 검색 전에 결정적으로 해석해 버린다.
    lexicon = tmp_path / "lex.json"
    chat = _ChatStub("폐배터리", {"definition": "수명이 다한 배터리 재활용", "sector": "이차전지"})
    search = _SearchStub(_SNIPPETS)

    got = resolve_sector("폐배터리 관련 투자 전략을 만들어 볼까?", chat,
                         search_fn=search, lexicon_path=lexicon)
    assert got == "이차전지"
    assert search.calls == 1
    saved = json.loads(lexicon.read_text(encoding="utf-8"))
    assert saved["폐배터리"]["sector"] == "이차전지"
    assert saved["폐배터리"]["definition"] == "수명이 다한 배터리 재활용"
    assert saved["폐배터리"]["sources"][0]["link"] == "https://example.com/ess"

    # 두 번째 호출 — 어휘집 결정적 히트: 검색은 물론 LLM도 다시 부르지 않는다
    chat2 = _ChatStub(None, None)
    search2 = _SearchStub(_SNIPPETS)
    got2 = resolve_sector("폐배터리로 전략 하나 더", chat2, search_fn=search2, lexicon_path=lexicon)
    assert got2 == "이차전지"
    assert search2.calls == 0
    assert chat2.calls == 0


def test_unmappable_term_cached_and_not_researched(tmp_path):
    lexicon = tmp_path / "lex.json"
    chat = _ChatStub("메타버스", {"definition": "가상 세계 서비스", "sector": None})
    search = _SearchStub(_SNIPPETS)

    assert resolve_sector("메타버스 관련주 전략", chat, search_fn=search,
                          lexicon_path=lexicon) is None
    assert search.calls == 1
    saved = json.loads(lexicon.read_text(encoding="utf-8"))
    assert saved["메타버스"]["sector"] is None

    # 재요청 — 매핑 불가로 판명된 용어는 재검색하지 않는다(③ 분기)
    search2 = _SearchStub(_SNIPPETS)
    assert resolve_sector("메타버스 관련주 전략", _ChatStub(None, None),
                          search_fn=search2, lexicon_path=lexicon) is None
    assert search2.calls == 0


def test_search_failure_is_not_cached(tmp_path):
    lexicon = tmp_path / "lex.json"
    chat = _ChatStub("그린수소", {"definition": "재생에너지로 생산한 수소", "sector": "에너지/원자력"})
    failing = _SearchStub(None)  # None = 검색 실패(빈 결과와 구분)

    assert resolve_sector("그린수소 전략", chat, search_fn=failing, lexicon_path=lexicon) is None
    assert not lexicon.exists()

    # 검색 복구 후 재시도는 다시 검색한다
    ok = _SearchStub(_SNIPPETS)
    assert resolve_sector("그린수소 전략", chat, search_fn=ok,
                          lexicon_path=lexicon) == "에너지/원자력"
    assert ok.calls == 1


def test_off_list_sector_from_llm_is_gated(tmp_path):
    lexicon = tmp_path / "lex.json"
    chat = _ChatStub("폐배터리", {"definition": "배터리 재활용", "sector": "테마주"})  # 목록 밖
    assert resolve_sector("폐배터리 전략", chat, search_fn=_SearchStub(_SNIPPETS),
                          lexicon_path=lexicon) is None
    # 목록 밖 이름은 게이트에서 걸러지되, 검색 결과 자체는 캐시된다(재검색 방지)
    saved = json.loads(lexicon.read_text(encoding="utf-8"))
    assert saved["폐배터리"]["sector"] is None


def test_base_resolver_short_circuits_search(tmp_path):
    lexicon = tmp_path / "lex.json"
    search = _SearchStub(_SNIPPETS)
    got = resolve_sector("2차전지 관련주", _ChatStub(None, None),
                         base_resolver=lambda t: "이차전지",
                         search_fn=search, lexicon_path=lexicon)
    assert got == "이차전지"
    assert search.calls == 0
    assert not lexicon.exists()


def test_lexicon_scan_ascii_boundary():
    lexicon = {"ess": {"term": "ESS", "sector": "이차전지"}}
    # 라틴 문자 연속 내부('process')의 부분 일치는 히트가 아니다
    assert _scan_lexicon("process 개선 전략", lexicon) is None
    assert _scan_lexicon("ESS 관련 전략", lexicon) is not None
    assert _scan_lexicon("ess로 만들어줘", lexicon) is not None


def test_on_search_fires_only_when_grounding_actually_runs(tmp_path):
    """on_search('검색 중...' 표시 신호)는 검색 그라운딩 단계 진입 시에만 1회 호출된다."""
    lexicon = tmp_path / "lex.json"
    fired: list[bool] = []
    chat = _ChatStub("폐배터리", {"definition": "배터리 재활용", "sector": "이차전지"})

    # 그라운딩 실행 → on_search 1회
    resolve_sector("폐배터리 관련 전략", chat, search_fn=_SearchStub(_SNIPPETS),
                   lexicon_path=lexicon, on_search=lambda: fired.append(True))
    assert fired == [True]

    # 어휘집 히트 → on_search 호출 없음
    fired.clear()
    resolve_sector("폐배터리 전략 하나 더", _ChatStub(None, None),
                   search_fn=_SearchStub(_SNIPPETS), lexicon_path=lexicon,
                   on_search=lambda: fired.append(True))
    assert fired == []

    # 내부 지식 LLM(base) 히트 → on_search 호출 없음
    fired.clear()
    resolve_sector("2차전지 관련주", _ChatStub(None, None),
                   base_resolver=lambda t: "이차전지",
                   search_fn=_SearchStub(_SNIPPETS), lexicon_path=tmp_path / "lex2.json",
                   on_search=lambda: fired.append(True))
    assert fired == []


def test_edge_learning_anchors_support_and_auto_verify(tmp_path):
    """관계 엣지 학습(FR-STR-070b) — 앵커는 스니펫에 실제 등장한 시드 개념만(결정적),
    출처 2개 이상 지지는 자동 verified, 1개는 pending, 후보 밖 타깃·미허용 유형은 드롭."""
    lexicon = tmp_path / "lex.json"
    snippets = [
        {"title": "CoWoS 첨단 패키징", "description": "HBM 적층 패키징 기술",
         "link": "https://a.example/1"},
        {"title": "CoWoS 수요 확대", "description": "HBM과 GPU를 결합하는 공정",
         "link": "https://b.example/2"},
    ]
    chat = _ChatStub(
        "CoWoS",
        {"definition": "첨단 반도체 패키징 기술", "sector": "반도체"},
        edges=[
            {"target": "hbm", "type": "related_to"},      # 출처 2개 → 자동 verified
            {"target": "gpu", "type": "used_in"},         # 미허용 유형 → 드롭
            {"target": "gpu", "type": "uses"},            # 출처 1개 → pending
            {"target": "lithium", "type": "uses"},        # 스니펫 미등장 → 드롭
        ],
    )
    resolve_sector("CoWoS 관련 전략", chat, search_fn=_SearchStub(snippets),
                   lexicon_path=lexicon)
    saved = json.loads(lexicon.read_text(encoding="utf-8"))["cowos"]
    edges = {(e["target"], e["type"]): e for e in saved["edges"]}
    assert set(edges) == {("hbm", "related_to"), ("gpu", "uses")}
    hbm = edges[("hbm", "related_to")]
    assert hbm["status"] == "verified" and hbm["support"] == 2
    assert len(hbm["evidence"]) == 2
    gpu = edges[("gpu", "uses")]
    assert gpu["status"] == "pending" and gpu["support"] == 1


def test_edge_learning_no_anchor_skips_edge_llm(tmp_path):
    """스니펫에 시드 개념이 없으면 엣지 LLM 호출 없이 빈 edges로 저장된다."""
    neutral = [{"title": "신조어 사전", "description": "새로 등장한 단어의 뜻풀이",
                "link": "https://a.example/1"}]
    chat = _ChatStub("신조어", {"definition": "정의", "sector": None},
                     edges=[{"target": "hbm", "type": "related_to"}])
    resolve_sector("신조어 관련 전략", chat, search_fn=_SearchStub(neutral),
                   lexicon_path=tmp_path / "lex.json")
    saved = json.loads((tmp_path / "lex.json").read_text(encoding="utf-8"))["신조어"]
    assert saved["edges"] == []
    # 용어 추출 + 그라운딩 2회만(엣지 선택 LLM 미호출 — 앵커 없음)
    assert chat.calls == 2


def test_general_facts_block_kg_seed_is_deterministic(tmp_path):
    """지식그래프 시드 개념(ESS)은 검색·LLM 없이 정의 사실 블록으로 나온다 —
    일반 지식 답변이 ESS를 '에너지 효율성'으로 환각하던 사고(스크린샷) 방지."""
    chat = _ChatStub(None, None)
    block = general_facts_block("ess 관련 투자", chat, search_fn=_SearchStub(_SNIPPETS),
                                lexicon_path=tmp_path / "lex.json")
    assert block is not None
    assert "ESS" in block and "에너지 저장" in block
    assert "모순되는 서술 금지" in block
    assert chat.calls == 0  # 결정적 — 용어 추출 LLM도 부르지 않는다


def test_general_facts_block_grounds_unknown_term_and_caches(tmp_path):
    lexicon = tmp_path / "lex.json"
    chat = _ChatStub("폐배터리", {"definition": "수명이 다한 배터리 재활용 산업", "sector": "이차전지"})
    search = _SearchStub(_SNIPPETS)

    block = general_facts_block("폐배터리가 뭐야?", chat, search_fn=search, lexicon_path=lexicon)
    assert block is not None and "배터리 재활용" in block and "이차전지" in block
    assert search.calls == 1
    # 재질문 — 어휘집 스캔 히트로 검색·LLM 없이 동일 블록
    search2 = _SearchStub(_SNIPPETS)
    chat2 = _ChatStub(None, None)
    block2 = general_facts_block("폐배터리 산업 설명해줘", chat2, search_fn=search2,
                                 lexicon_path=lexicon)
    assert block2 is not None and "배터리 재활용" in block2
    assert search2.calls == 0 and chat2.calls == 0


def test_general_facts_block_skips_search_for_known_or_no_term(tmp_path):
    # KG 시드 개념(금리)이 있는 질문 → 검색 없이 결정적 블록(시드가 커버)
    chat0 = _ChatStub(None, None)
    search0 = _SearchStub(_SNIPPETS)
    block = general_facts_block("금리가 오르면 주가는 어떻게 돼?", chat0, search_fn=search0,
                                lexicon_path=tmp_path / "lex.json")
    assert block is not None and "금리" in block
    assert search0.calls == 0 and chat0.calls == 0
    # 용어 추출이 null(테마 용어 없음) → 검색 없이 None
    chat = _ChatStub(None, None)
    search = _SearchStub(_SNIPPETS)
    assert general_facts_block("분산 투자가 왜 중요해?", chat, search_fn=search,
                               lexicon_path=tmp_path / "lex.json") is None
    assert search.calls == 0
    # 정본 섹터로 해석되는 용어(반도체) → LLM이 아는 개념이라 검색하지 않는다
    chat2 = _ChatStub("반도체", None)
    search2 = _SearchStub(_SNIPPETS)
    assert general_facts_block("반도체 사이클 설명해줘", chat2, search_fn=search2,
                               lexicon_path=tmp_path / "lex.json") is None
    assert search2.calls == 0
    # allow_search=False(기초 용어 질문) → 용어 추출 LLM조차 부르지 않는다
    chat3 = _ChatStub("폐배터리", None)
    assert general_facts_block("PER이 뭐야?", chat3, search_fn=_SearchStub(_SNIPPETS),
                               lexicon_path=tmp_path / "lex.json", allow_search=False) is None
    assert chat3.calls == 0


def test_no_search_credentials_returns_base_only(tmp_path, monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    chat = _ChatStub("폐배터리", {"definition": "x", "sector": "이차전지"})
    # search_fn 미주입 + 자격증명 없음 → 검색 단계 진입 없이 None(용어 추출 LLM도 안 부른다)
    assert resolve_sector("폐배터리 전략", chat, lexicon_path=tmp_path / "lex.json") is None
    assert chat.calls == 0


def test_learn_sector_term_grounds_unknown_theme_for_parse_path(tmp_path, monkeypatch):
    """파싱 경로 사전 학습(FR-STR-069) — '마운자로 관련주'가 검색 없이 미지원 처리되던 사고 재현.

    어휘 밖 테마+업종 큐면 검색 그라운딩으로 학습하고, 학습 후에는 파싱의 결정적 섹터
    추출(_extract_sector→지식그래프)이 같은 문장을 그대로 해석해야 한다."""
    import engine.knowledge_graph as kg
    from engine.term_grounding import learn_sector_term

    lexicon = tmp_path / "lex.json"
    # 읽기 경로 통합: _extract_sector는 그래프 단일 경로(스캔 인덱스에 학습 노드 포함)
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)

    chat = _ChatStub("마운자로", {"definition": "당뇨·비만 치료제", "sector": "바이오/제약"})
    search = _SearchStub([
        {"title": "마운자로", "description": "일라이 릴리가 개발한 당뇨·비만 치료제",
         "link": "https://example.com/mounjaro"},
    ])
    got = learn_sector_term(
        "마운자로 관련주 전략을 만들어보자", chat, search_fn=search, lexicon_path=lexicon
    )
    assert got == "바이오/제약"
    assert search.calls == 1
    saved = json.loads(lexicon.read_text(encoding="utf-8"))
    assert saved["마운자로"]["sector"] == "바이오/제약"

    # 학습 후: 결정적 추출이 지식그래프(어휘집 합성)로 같은 문장을 즉시 해석한다
    from engine.nl_parser import _extract_sector, mentions_unresolved_sector
    assert _extract_sector("마운자로 관련주 전략을 만들어보자") == "바이오/제약"
    # 해석되므로 게이트도 닫힌다 — 같은 용어를 다시 학습(검색)하지 않는다
    assert mentions_unresolved_sector("마운자로 관련주 전략을 만들어보자") is False
    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_learn_sector_term_gate_skips_known_vocab_and_cueless(tmp_path):
    """게이트: 지원 어휘(반도체)나 업종 큐 없는 입력은 검색·LLM에 진입하지 않는다."""
    from engine.term_grounding import learn_sector_term

    chat = _ChatStub(None, None)
    search = _SearchStub(_SNIPPETS)
    lexicon = tmp_path / "lex.json"
    assert learn_sector_term("반도체 관련주 전략 만들어줘", chat,
                             search_fn=search, lexicon_path=lexicon) is None
    assert learn_sector_term("PER 10 이하면 매수하는 전략", chat,
                             search_fn=search, lexicon_path=lexicon) is None
    assert search.calls == 0
    assert chat.calls == 0


# ─── 관련 기업 엣지 학습 + 테마 유니버스 되묻기(FR-STR-071) ────────────────────────

def test_company_edges_learned_from_snippets_with_first_known_date(tmp_path, monkeypatch):
    """스니펫에 함께 언급된 상장사가 related_company 엣지로 학습된다(결정적, LLM 무관여).

    출처 2건 교차지지 → verified, 1건 → pending. first_known_date는 뉴스 보도일 최솟값."""
    import engine.knowledge_graph as kg

    lexicon = tmp_path / "lex.json"
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)
    snippets = [
        {"title": "위고비 국내 시장 동향", "description": "삼성전자, 카카오 언급 기사",
         "link": "https://a.com/1", "date": "2024-03-05"},
        {"title": "위고비 산업 분석", "description": "삼성전자 협력 현황",
         "link": "https://b.com/2", "date": None},
    ]
    chat = _ChatStub("위고비", {"definition": "주사형 비만 치료제", "sector": "바이오/제약"})
    got = resolve_sector("위고비 관련주 전략을 만들어줘", chat,
                         search_fn=_SearchStub(snippets), lexicon_path=lexicon)
    assert got == "바이오/제약"

    saved = json.loads(lexicon.read_text(encoding="utf-8"))["위고비"]
    by_target = {e["target"]: e for e in saved["edges"] if e["type"] == "related_company"}
    assert by_target["company:005930"]["status"] == "verified"
    assert by_target["company:005930"]["support"] == 2
    assert by_target["company:005930"]["first_known_date"] == "2024-03-05"
    assert by_target["company:005930"]["target_name"] == "삼성전자"
    assert by_target["company:035720"]["status"] == "pending"

    # 검증(verified) 기업만 테마 유니버스 후보로 나온다 — pending은 콘솔 검토 대기.
    # 읽기 경로 통합: 조회는 그래프 단일 경로(어휘집 별도 스캔 없음).
    from engine.knowledge_graph import theme_listed_companies
    theme = theme_listed_companies("위고비 관련해서 백테스트")
    assert theme is not None
    assert theme["term"] == "위고비"
    assert [c["symbol"] for c in theme["companies"]] == ["005930"]
    assert theme["first_known_date"] == "2024-03-05"
    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_theme_universe_clarification_chip_roundtrip(tmp_path, monkeypatch):
    """테마 관련 상장사 되묻기(FR-STR-071) — 질문·칩 구성과 칩 왕복 재해석 계약.

    종목 칩은 '종목 전체를 함께'(모호성 되묻기 억제)+'YYYY년부터'(시점 편향 가드)를
    포함해야 하고, 지정 종목·시작일로 결정적으로 재해석돼야 한다."""
    import engine.knowledge_graph as kg

    lexicon = tmp_path / "lex.json"
    lexicon.write_text(json.dumps({
        "위고비": {
            "term": "위고비", "definition": "주사형 비만 치료제", "sector": "바이오/제약",
            "sources": [], "searched_at": "2026-07-25T00:00:00+00:00",
            "edges": [
                {"type": "related_company", "target": "company:005930", "target_name": "삼성전자",
                 "support": 2, "status": "verified", "evidence": [], "first_known_date": "2024-03-05"},
                {"type": "related_company", "target": "company:035720", "target_name": "카카오",
                 "support": 2, "status": "verified", "evidence": [], "first_known_date": None},
                {"type": "related_company", "target": "company:000660", "target_name": "SK하이닉스",
                 "support": 1, "status": "pending", "evidence": [], "first_known_date": None},
            ],
        }
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)

    from engine.nl_parser import (
        ParsedStrategy,
        _extract_backtest_dates,
        _extract_target_symbols,
        detect_symbol_ambiguity,
        detect_theme_universe_clarification,
    )

    parsed = ParsedStrategy.model_validate({
        "description": "위고비 관련주 전략", "universe": ["KOSPI", "KOSDAQ"],
        "sector": "바이오/제약",
    })
    question, chips = detect_theme_universe_clarification(parsed, "위고비 관련주 전략을 만들어보자")
    assert question is not None and "2024-03-05" in question  # 시점 편향 경고 포함
    assert chips is not None and len(chips) == 2
    assert "삼성전자, 카카오" in chips[0] and "2024년부터" in chips[0]
    assert "SK하이닉스" not in chips[0]  # pending 제외
    assert "바이오/제약 업종 전체로" in chips[1]

    # 칩 왕복 ①: 종목 칩 → 지정 종목 + 명시적 시작일로 결정적 재해석
    refs = _extract_target_symbols(chips[0])
    assert refs is not None and {r.symbol for r in refs} == {"005930", "035720"}
    start, end = _extract_backtest_dates(chips[0])
    assert start == "2024-01-01" and end is None

    # 칩 왕복 ②: '전체를 함께' 집합 의도 발화는 다종목 모호성 되묻기를 억제
    multi = parsed.model_copy(update={"target_symbols": ["005930", "035720"]})
    assert detect_symbol_ambiguity(multi, chips[0]) == (None, None)
    # 집합 의도 없는 다종목 발화는 기존대로 되묻는다(FR-STR-068 계약 유지)
    q_ambig, _ = detect_symbol_ambiguity(multi, "삼성전자 카카오 백테스트")
    assert q_ambig is not None

    # 게이트: 테마 큐 없는 발화·이미 종목이 지정된 경우엔 침묵
    assert detect_theme_universe_clarification(parsed, "PER 10 이하 매수") == (None, None)
    assert detect_theme_universe_clarification(multi, "위고비 관련주") == (None, None)
    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록
