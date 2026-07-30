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

    def __init__(self, term: str | None, ground: dict | None, edges: list | None = None,
                 groups: list | None = None):
        self.term = term
        self.ground = ground
        self.edges = edges
        self.groups = groups
        self.calls = 0

    def __call__(self, system_prompt: str, user_msg: str, *, max_tokens: int = 400) -> str:
        self.calls += 1
        if "추출하는 도구" in system_prompt:
            return json.dumps({"term": self.term})
        if "관계를 고르는 도구" in system_prompt:
            return json.dumps({"edges": self.edges or []})
        if "판별하는 도구" in system_prompt:
            return json.dumps({"industry": True})
        if "대조하는 도구" in system_prompt:
            return json.dumps({"groups": self.groups or []})
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


def test_on_kg_lookup_fires_at_chain_entry(tmp_path):
    """on_kg_lookup('개념 확인 중...' 표시 신호)은 해석 체인 진입 시 1회 호출된다.

    검색 그라운딩까지 가면 on_search가 뒤이어 호출돼 표시가 교체되고,
    콜백 예외는 해석 결과를 깨지 않는다."""
    lexicon = tmp_path / "lex.json"
    stages: list[str] = []
    chat = _ChatStub("폐배터리", {"definition": "배터리 재활용", "sector": "이차전지"})

    # 검색까지 진행 → kg_lookup 1회 후 searching이 뒤따른다(표시 교체 순서)
    got = resolve_sector("폐배터리 관련 전략", chat, search_fn=_SearchStub(_SNIPPETS),
                         lexicon_path=lexicon,
                         on_search=lambda: stages.append("searching"),
                         on_kg_lookup=lambda: stages.append("kg_lookup"))
    assert got == "이차전지"
    assert stages == ["kg_lookup", "searching"]

    # 어휘집 히트(즉시 해석)여도 체인 진입 신호는 1회 온다
    stages.clear()
    resolve_sector("폐배터리 전략 하나 더", _ChatStub(None, None),
                   search_fn=_SearchStub(_SNIPPETS), lexicon_path=lexicon,
                   on_search=lambda: stages.append("searching"),
                   on_kg_lookup=lambda: stages.append("kg_lookup"))
    assert stages == ["kg_lookup"]

    # 콜백 예외는 무시되고 해석은 정상 진행된다
    def boom():
        raise RuntimeError("표시 실패")

    got3 = resolve_sector("폐배터리 전략", _ChatStub(None, None),
                          search_fn=_SearchStub(_SNIPPETS), lexicon_path=lexicon,
                          on_kg_lookup=boom)
    assert got3 == "이차전지"


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


def test_compound_theme_prefers_search_learning_over_llm(tmp_path, monkeypatch):
    """복합 테마구('반도체 소부장')는 내부 지식 LLM보다 검색 학습을 먼저 시도한다 —
    LLM이 머리 테마어(반도체)로 근사해 버리면 하위 테마(정의·관련 상장사)가 영영
    학습되지 않던 공백(FR-STR-071, 실측 사고 2026-07-25).

    ①b 지식그래프 단계는 전역 어휘집(learned 오버레이)을 읽으므로, 런타임 학습으로
    실제 data/term_lexicon.json에 '반도체소부장'이 저장되면 검색 학습 경로가 선점돼
    테스트가 깨진다 — tmp 어휘집으로 그래프도 격리한다(실측 2026-07-25)."""
    import engine.knowledge_graph as kg

    lexicon = tmp_path / "lex.json"
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)
    base_calls: list[str] = []

    def base(text: str):
        base_calls.append(text)
        return "반도체"

    chat = _ChatStub("반도체 소부장", {"definition": "반도체 소재·부품·장비 산업",
                                       "sector": "반도체"})
    search = _SearchStub(_SNIPPETS)
    got = resolve_sector("반도체 소부장 전략을 만들자", chat, base_resolver=base,
                         search_fn=search, lexicon_path=lexicon)
    assert got == "반도체"
    assert search.calls == 1          # 검색 학습이 실제로 수행됐다
    assert base_calls == []           # 내부 지식 LLM은 호출되지 않았다(검색 성공)
    saved = json.loads(lexicon.read_text(encoding="utf-8"))
    assert saved["반도체소부장"]["definition"] == "반도체 소재·부품·장비 산업"
    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_compound_theme_falls_back_to_llm_when_unmappable(tmp_path, monkeypatch):
    """검색 학습이 업종 매핑에 실패해도 내부 지식 LLM 폴백으로 근사할 수 있다."""
    import engine.knowledge_graph as kg

    lexicon = tmp_path / "lex.json"
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)
    chat = _ChatStub("반도체 소부장", {"definition": "정의", "sector": None})
    got = resolve_sector("반도체 소부장 전략을 만들자", chat,
                         base_resolver=lambda _t: "반도체",
                         search_fn=_SearchStub(_SNIPPETS), lexicon_path=lexicon)
    assert got == "반도체"  # 폴백 성공
    # 학습 자체는 저장돼 재검색하지 않는다(매핑 불가 캐시).
    saved = json.loads(lexicon.read_text(encoding="utf-8"))
    assert saved["반도체소부장"]["sector"] is None
    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_extracted_known_sector_term_is_not_learned(tmp_path):
    """용어 추출 LLM이 정본 섹터 용어(반도체)를 내면 검색·학습 없이 그 섹터로 해석한다 —
    '반도체' 항목이 어휘집에 학습되면 이후 모든 반도체 언급이 어휘집 히트로 오염된다."""
    lexicon = tmp_path / "lex.json"
    chat = _ChatStub("반도체", {"definition": "정의", "sector": "반도체"})
    search = _SearchStub(_SNIPPETS)
    got = resolve_sector("반도체 소부장 전략", chat, search_fn=search, lexicon_path=lexicon)
    assert got == "반도체"
    assert search.calls == 0          # 검색하지 않는다
    assert not lexicon.exists()       # 학습(저장)하지 않는다


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

def test_company_edges_from_naver_groups_auto_verified(tmp_path, monkeypatch):
    """관련 기업 엣지는 뉴스 동시언급이 아니라 네이버 금융 분류로 만든다(FR-STR-071 개정
    2026-07-27, 사용자 지시 — 뉴스 노이즈 폐기·자동 등록).

    LLM은 분류 이름 닫힌 목록에서만 고르고(목록 밖 이름·스코프 제외 분류는 드롭),
    종목은 그 분류의 수록 목록에서 결정적으로 수집해 자동 verified로 등록한다(콘솔
    사후 반려 가능). 뉴스 스니펫에 상장사가 함께 언급돼도 기업 엣지는 생기지 않는다."""
    import engine.knowledge_graph as kg
    import engine.naver_theme_live as ntl
    import engine.term_grounding as tg

    lexicon = tmp_path / "lex.json"
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)
    groups = [
        {"no": 901, "name": "비만치료제", "kind": "theme"},
        {"no": 902, "name": "건강기능식품", "kind": "theme"},
        {"no": 903, "name": "정치인 인맥", "kind": "theme"},  # 스코프 제외 가드
    ]
    monkeypatch.setattr(tg, "_naver_groups_for_learning", lambda **k: groups)
    stocks_by_no = {
        901: [{"symbol": "005930", "name": "삼성전자"}],
        902: [{"symbol": "005930", "name": "삼성전자"}, {"symbol": "035720", "name": "카카오"}],
        903: [{"symbol": "000660", "name": "SK하이닉스"}],
    }
    monkeypatch.setattr(ntl, "fetch_group_stocks",
                        lambda group, fetch=None: stocks_by_no.get(group["no"], []))

    snippets = [
        {"title": "위고비 국내 시장 동향", "description": "신한지주, SK하이닉스 언급 기사",
         "link": "https://a.com/1", "date": "2024-03-05"},
    ]
    # LLM이 스코프 제외('정치인 인맥')·목록 밖('없는분류') 이름을 답해도 드롭된다
    chat = _ChatStub("위고비", {"definition": "주사형 비만 치료제", "sector": "바이오/제약"},
                     groups=["비만치료제", "건강기능식품", "정치인 인맥", "없는분류"])
    got = resolve_sector("위고비 관련주 전략을 만들어줘", chat,
                         search_fn=_SearchStub(snippets), lexicon_path=lexicon)
    assert got == "바이오/제약"

    saved = json.loads(lexicon.read_text(encoding="utf-8"))["위고비"]
    by_target = {e["target"]: e for e in saved["edges"] if e["type"] == "related_company"}
    # 뉴스 동시언급(신한지주·SK하이닉스)은 미편입 — 분류 수록 종목만
    assert set(by_target) == {"company:005930", "company:035720"}
    assert all(e["status"] == "verified" for e in by_target.values())  # 자동 등록
    assert by_target["company:005930"]["support"] == 2  # 두 분류에 수록 → 출처 2
    assert by_target["company:005930"]["target_name"] == "삼성전자"
    assert by_target["company:035720"]["support"] == 1

    # 자동 verified 기업이 즉시 테마 유니버스 후보로 나온다.
    # 읽기 경로 통합: 조회는 그래프 단일 경로(어휘집 별도 스캔 없음).
    from engine.knowledge_graph import theme_listed_companies
    theme = theme_listed_companies("위고비 관련해서 백테스트")
    assert theme is not None
    assert theme["term"] == "위고비"
    assert {c["symbol"] for c in theme["companies"]} == {"005930", "035720"}
    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_naver_company_edges_blocks_listed_company_term():
    """개별 상장사 이름은 테마가 아니다 — LLM 호출 전에 결정적으로 차단한다.

    '삼성전자'가 학습 용어로 들어와 '반도체 대표주' 분류 종목으로 확장되던 사고 가드
    (마이그레이션 dry-run 실측). 인물·그룹명은 프롬프트 규칙이 막는다(LLM 소관)."""
    from engine.term_grounding import _naver_company_edges

    def chat_must_not_run(*a, **k):
        raise AssertionError("상장사명 용어는 LLM 매핑에 도달하면 안 된다")

    groups = [{"no": 901, "name": "반도체 대표주(생산)", "kind": "theme"}]
    assert _naver_company_edges("삼성전자", "반도체 제조 기업", groups, chat_must_not_run) == []


def test_naver_company_edges_industry_gate_blocks_non_industry_terms():
    """산업 분야 아님(인물·연예 그룹 등) LLM 판별이 false면 분류 매핑 없이 빈 목록 —
    'BTS'·'리센느'가 엔터/조선 전체 종목으로 확장되던 실측 차단(단일 과제 판별 분리)."""
    from engine.term_grounding import _naver_company_edges

    def chat(system_prompt: str, user_msg: str, *, max_tokens: int = 400) -> str:
        if "판별하는 도구" in system_prompt:
            return json.dumps({"industry": False})
        raise AssertionError("판별 false면 분류 매핑 LLM에 도달하면 안 된다")

    groups = [{"no": 901, "name": "엔터테인먼트", "kind": "theme"}]
    assert _naver_company_edges("리센느", "걸그룹 이름", groups, chat) == []


def test_theme_universe_auto_applied_with_notice(tmp_path, monkeypatch):
    """테마 관련 검증 상장사 자동 적용(FR-STR-071 ④ 개정, 사용자 결정 2026-07-25).

    되묻기 없이 target_symbols를 설정하고 업종 근사를 해제하며, 목록·근거·시점 정보를
    notice로 돌려준다. pending 엣지는 불참, 테마 큐 없음·종목 기지정 시 침묵."""
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

    from engine.nl_parser import ParsedStrategy, apply_theme_universe

    parsed = ParsedStrategy.model_validate({
        "description": "위고비 관련주 전략", "universe": ["KOSPI", "KOSDAQ"],
        "sector": "바이오/제약",
    })
    notice = apply_theme_universe(parsed, "위고비 관련주 전략을 만들어보자")
    assert notice is not None
    assert "대상 종목으로 설정했어요" in notice
    assert "2024-03-05" in notice  # 시점 편향 고지(비차단)
    assert set(parsed.target_symbols) == {"005930", "035720"}  # pending(SK하이닉스) 불참
    assert parsed.sector is None  # 업종 근사 해제(대상=종목 목록)

    # 게이트: 테마 큐 없는 발화·이미 종목이 지정된 경우엔 침묵(미적용)
    fresh = ParsedStrategy.model_validate({
        "description": "전략", "universe": ["KOSPI"], "sector": "바이오/제약",
    })
    assert apply_theme_universe(fresh, "PER 10 이하 매수") is None
    assert fresh.target_symbols == [] and fresh.sector == "바이오/제약"
    already = fresh.model_copy(update={"target_symbols": ["005930"]})
    assert apply_theme_universe(already, "위고비 관련주") is None
    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_relink_scan_proposes_pending_edges_for_new_nodes(tmp_path):
    """재연결 감사(FR-STR-070b ⑥) — 학습 이후 편입된 노드가 저장 텍스트(정의·출처 제목)에
    등장하면 pending related_to 후보를 추가한다. rejected 이력은 부활하지 않고, 두 번
    돌려도 결과가 같다(멱등). 'bts 관련주' 사고의 역방향 공백 보정."""
    from engine.term_grounding import relink_lexicon

    lexicon = tmp_path / "lex.json"
    lexicon.write_text(json.dumps({
        "신조어테마": {
            "term": "신조어테마",
            "definition": "HBM 공급 부족과 함께 언급되는 신조어 테마",
            "sector": None,
            "sources": [{"title": "GPU 서버 수요 급증", "link": "https://example.com/gpu"}],
            "searched_at": "2026-07-25T00:00:00+00:00",
            "edges": [{"type": "related_to", "target": "hbm",
                       "status": "rejected", "support": 2}],
        },
    }, ensure_ascii=False), encoding="utf-8")

    report = relink_lexicon(lexicon_path=lexicon)
    assert report["terms_updated"] == 1
    saved = json.loads(lexicon.read_text(encoding="utf-8"))["신조어테마"]
    by_target = {e["target"]: e for e in saved["edges"]}
    # 출처 제목의 GPU → pending 제안(자동 verified 금지, 콘솔 승인 대상)
    assert by_target["gpu"]["status"] == "pending"
    assert by_target["gpu"]["proposed_by"] == "relink-scan"
    assert by_target["gpu"]["evidence"] == ["https://example.com/gpu"]
    # 정의의 HBM은 rejected 이력 — 부활하지 않고 그대로 보존
    assert by_target["hbm"]["status"] == "rejected"

    # 멱등: 재실행 시 새 제안 없음(이미 제안된 타깃 재제안 금지)
    report2 = relink_lexicon(lexicon_path=lexicon)
    assert report2["terms_updated"] == 0


def test_stale_entry_regrounds_and_merges(tmp_path, monkeypatch):
    """TTL 재검토(FR-STR-069 ⑦) — searched_at이 TTL을 넘긴 미해결 항목은 재언급 시
    재검색을 허용하되, 재학습은 병합이라 기존 엣지의 검토 상태(rejected)를 보존한다.
    TTL=0이면 기존 영구 캐시 계약 그대로(재검색 없음)."""
    entry = {
        "term": "메타버스", "definition": "가상 세계 서비스", "sector": None,
        "sources": [], "searched_at": "2026-01-01T00:00:00+00:00",  # 200일 이상 경과
        "edges": [{"type": "related_to", "target": "hbm",
                   "status": "rejected", "support": 2}],
    }
    lexicon = tmp_path / "lex.json"
    lexicon.write_text(json.dumps({"메타버스": entry}, ensure_ascii=False), encoding="utf-8")

    # TTL 비활성(0) — 경과했어도 재검색하지 않는다(기존 계약)
    monkeypatch.setenv("TERM_REGROUND_TTL_DAYS", "0")
    search0 = _SearchStub(_SNIPPETS)
    assert resolve_sector("메타버스 관련주 전략", _ChatStub(None, None),
                          search_fn=search0, lexicon_path=lexicon) is None
    assert search0.calls == 0

    # TTL 90일 — 경과 항목은 재검색·병합(이번엔 업종 매핑 성공 시나리오)
    monkeypatch.setenv("TERM_REGROUND_TTL_DAYS", "90")
    chat = _ChatStub("메타버스", {"definition": "가상 세계 플랫폼 산업",
                               "sector": "소프트웨어"})
    search = _SearchStub(_SNIPPETS)
    got = resolve_sector("메타버스 관련주 전략", chat, search_fn=search, lexicon_path=lexicon)
    assert got == "소프트웨어"
    assert search.calls == 1
    saved = json.loads(lexicon.read_text(encoding="utf-8"))["메타버스"]
    assert saved["sector"] == "소프트웨어"
    assert saved["searched_at"] != entry["searched_at"]  # 재학습 시각 갱신
    # rejected 엣지 보존(부활·강등 없음)
    assert {(e["target"], e["status"]) for e in saved["edges"]} >= {("hbm", "rejected")}

    # 갱신 직후(신선) — 다시 캐시 히트, 재검색 없음
    search2 = _SearchStub(_SNIPPETS)
    got2 = resolve_sector("메타버스 관련주 전략", _ChatStub(None, None),
                          search_fn=search2, lexicon_path=lexicon)
    assert got2 == "소프트웨어"
    assert search2.calls == 0


def test_snippet_dedupe_by_link():
    """'관련주'+'수혜주' 이중 뉴스 쿼리(리콜 개선) — 같은 기사가 두 쿼리에 잡혀도
    링크 dedupe로 출처 교차지지가 부풀지 않는다."""
    from engine.term_grounding import _dedupe_snippets

    snippets = [
        {"title": "A", "link": "https://x/1"},
        {"title": "B", "link": "https://x/2"},
        {"title": "A(중복)", "link": "https://x/1"},
        {"title": "무링크"}, {"title": "무링크"},
    ]
    deduped = _dedupe_snippets(snippets)
    assert [s["title"] for s in deduped] == ["A", "B", "무링크"]
