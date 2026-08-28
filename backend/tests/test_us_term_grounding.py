"""US 공시 검색 그라운딩 — 카탈로그 밖 테마어 학습(EDGAR 전문검색 → 정본 조인 → LLM 심사).

2026-08-26 사고: /us "mRNA 관련주"가 되묻기로 끝났다 — KR은 네이버 테마 명부(285종)와
검색 그라운딩으로 13종목을 세우는데, US는 카탈로그 25종 밖이면 찾아볼 경로 자체가
없었다(시장 격리로 KR 체인을 끊어 둔 자리에 US 판이 없었음).

검색은 전부 주입(search_fn)이다 — 테스트는 네트워크를 타지 않는다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest

from engine import us_term_grounding as grounding
from engine.us_knowledge_graph import normalize_theme_term, theme_term_candidates

_ROOT = Path(__file__).resolve().parents[2]
_OHLCV = _ROOT / "data" / "ohlcv-us"

needs_data = pytest.mark.skipif(not _OHLCV.exists(), reason="미국 파케이 미러 없음")

# 정본(us-stocks.json)의 실제 CIK — 조인이 정본을 실제로 타는지 보려면 실값이어야 한다
_CIK = {
    # 헬스케어(같은 섹터로 몰리는 테마) — mRNA·암 계열 실측 종목
    "MRNA": "0001682852", "ARCT": "0001768224", "ALNY": "0001178670",
    "IONS": "0000874015", "VRTX": "0000875320", "STOK": "0001623526",
    # 섹터가 흩어지는 후보(상투어 판정용) — 소매·에너지·금융·산업재·소재·정보기술
    "TSCO": "0000916365", "XOM": "0002115436", "JPM": "0000019617",
    "BA": "0000012927", "NEM": "0001164727", "NVDA": "0001045810",
}


def _filing(symbol: str, n: int, score: float = 10.0) -> dict:
    return {
        "cik": _CIK[symbol], "adsh": f"{_CIK[symbol]}-2{n}-00001",
        "doc": f"{symbol.lower()}-2024123{n}.htm", "file_date": f"202{n}-02-21",
        "score": score,
    }


def _filings(spec: dict[str, int]) -> list[dict]:
    """{티커: 공시 건수} → 공시 목록(같은 기업의 서로 다른 문서)."""
    return [_filing(sym, i) for sym, count in spec.items() for i in range(1, count + 1)]


def _found(spec: dict[str, int], total: Optional[int] = None) -> dict:
    """search_fn 반환 계약({total, filings})."""
    filings = _filings(spec)
    return {"total": len(filings) if total is None else total, "filings": filings}


def entry_term(lexicon_path) -> str:
    """원장에 남은 표기(표시 라벨과 갈리는지 보기 위한 헬퍼)."""
    return grounding.company_related_entry("NVDA", lexicon_path=lexicon_path)["term"]


def _chat_picking(symbols: list[str]):
    def chat(_system: str, _user: str, **_kw) -> str:
        return json.dumps({"symbols": symbols})
    return chat


# ── 한정어 정규화 ───────────────────────────────────────────────────────────

def test_normalize_theme_term_strips_category_suffix():
    # 화면에 나갔던 표현 그대로 — 'mrna-Related'가 질의어·학습 테마명이 되면 안 된다
    assert normalize_theme_term("mrna-Related") == "mrna"
    assert normalize_theme_term("US cloud software stocks") == "cloud software"
    assert normalize_theme_term("미국 빅테크 관련주") == "빅테크"
    assert normalize_theme_term("") == ""
    # 조회 후보 목록의 첫 항목은 언제나 원표기(정확 일치 우선 순서 보존)
    assert theme_term_candidates("mrna-Related")[0] == "mrna-Related"


# ── 정본 조인·지지 집계 ─────────────────────────────────────────────────────

@needs_data
def test_candidates_join_registry_and_count_distinct_filings():
    filings = _filings({"MRNA": 3, "ARCT": 1})
    filings.append({"cik": "0009999999", "adsh": "x-1", "doc": "x.htm"})  # 정본 밖
    filings.append(_filing("MRNA", 1))  # 같은 문서 재등장 — 지지가 부풀면 안 된다
    rows = grounding._candidates(filings)
    by_symbol = {r["symbol"]: r for r in rows}
    assert set(by_symbol) == {"MRNA", "ARCT"}
    assert by_symbol["MRNA"]["support"] == 3
    assert by_symbol["ARCT"]["support"] == 1
    assert rows[0]["symbol"] == "MRNA"  # 지지 건수 내림차순
    assert by_symbol["MRNA"]["industry"] == "Biotechnology"
    assert by_symbol["MRNA"]["evidence"][0].startswith(
        "https://www.sec.gov/Archives/edgar/data/1682852/")


@needs_data
def test_candidates_rank_by_relevance_not_filing_count():
    """순위 정본은 검색 관련도다 — 공시 건수로 줄 세우면 3년치 낸 회사가 모두 동점이 돼
    사실상 알파벳순이 된다(실측 2026-08-26: 'cybersecurity' 상위가 가구·은행 회사)."""
    filings = [_filing("ALNY", 1, score=3.0), _filing("ALNY", 2, score=3.0),
               _filing("ALNY", 3, score=3.0), _filing("MRNA", 1, score=15.9)]
    rows = grounding._candidates(filings)
    assert [r["symbol"] for r in rows] == ["MRNA", "ALNY"]
    assert rows[0]["score"] == 15.9 and rows[1]["support"] == 3


@needs_data
def test_boilerplate_term_is_not_learned(tmp_path):
    """흔하면서(①) 상위 후보 업종이 흩어지면(②) 상투어 — 학습하지 않는다.

    'climate change'를 학습시키면 셸·EOG·BHP·금광이 확정 15곳으로 나온다(실측) —
    기후 테마 기업이 아니라 기후 위험을 공시해야 하는 배출 기업이다."""
    spread = {"XOM": 2, "JPM": 2, "BA": 2, "NEM": 2, "NVDA": 2, "TSCO": 2}
    result = grounding.ground_us_theme(
        "climate change", _chat_picking(list(spread)),
        search_fn=lambda _t: _found(spread, total=10_000),
        lexicon_path=tmp_path / "lex.json",
    )
    assert result is None
    assert not (tmp_path / "lex.json").exists()  # 부정 캐시로도 남기지 않는다


@needs_data
def test_common_but_coherent_term_is_learned(tmp_path):
    """흔해도 상위 후보가 한 업종에 몰리면 상투어가 아니다 — 학습한다.

    실측 사고(2026-08-27): 'cancer'는 공시 4,261건이라 종전 건수 상한(2,000)에 막혔는데,
    상위 후보는 전부 항암 기업(섹터 집중도 95%)이었다 — 관련도 순위가 이미 정리한
    경우까지 건수만으로 막으면 멀쩡한 테마가 되묻기로 끝난다."""
    health = {"MRNA": 2, "ARCT": 2, "ALNY": 2, "IONS": 2, "VRTX": 2, "STOK": 2}
    result = grounding.ground_us_theme(
        "cancer", _chat_picking(list(health)),
        search_fn=lambda _t: _found(health, total=4_261),
        lexicon_path=tmp_path / "lex.json",
    )
    assert result is not None and len(result[1]) == 6


@needs_data
def test_rare_but_spread_term_is_learned(tmp_path):
    """희소 표현은 업종이 흩어져도 학습한다 — 흩어짐이 곧 상투어를 뜻하지 않는다.

    실측: 'data center power'는 공시 83건이고 섹터 집중도 35%(정보기술 7·산업재 6)다.
    집중도만으로 판정하면 이런 실제 테마가 막힌다."""
    spread = {"NVDA": 2, "BA": 2, "XOM": 2, "JPM": 2}
    result = grounding.ground_us_theme(
        "data center power", _chat_picking(list(spread)),
        search_fn=lambda _t: _found(spread, total=83),
        lexicon_path=tmp_path / "lex.json",
    )
    assert result is not None and len(result[1]) == 4


@needs_data
def test_judge_drops_symbols_outside_candidate_list():
    candidates = grounding._candidates(_filings({"MRNA": 2, "ARCT": 2}))
    picked = grounding._judge_members(
        "mrna", candidates, _chat_picking(["MRNA", "NVDA", "MRNA"]))
    assert picked == ["MRNA"]  # 목록 밖(NVDA)·중복은 드롭 — 환각 차단


# ── 학습 본체 ───────────────────────────────────────────────────────────────

def test_judge_splits_into_batches_and_unions():
    """심사는 10곳씩 나눠 묻고 합집합을 만든다 — 한 번에 40곳을 물으면 9B가 앞머리
    2~9곳만 고르고 나머지를 흘린다(2026-08-26 E2E 사고: mRNA 확정 2곳으로 게이트 탈락).
    묶음 밖 티커는 여기서도 드롭된다(닫힌 세계 계약은 묶음 단위로 유지)."""
    rows = [
        {"symbol": f"T{i:02d}", "name": f"Company {i}", "industry": "Biotechnology",
         "score": 10.0, "support": 2, "evidence": []}
        for i in range(25)
    ]
    seen_batches: list[list[str]] = []

    def chat(_system: str, user: str, **_kw) -> str:
        symbols = [line.split(". ", 1)[1].split(" | ")[0]
                   for line in user.splitlines() if line[:1].isdigit()]
        seen_batches.append(symbols)
        return json.dumps({"symbols": symbols[:1] + ["NVDA"]})  # 묶음 밖 티커 섞기

    picked = grounding._judge_members("mrna", rows, chat)
    assert [len(b) for b in seen_batches] == [10, 10, 5]
    assert picked == ["T00", "T10", "T20"]  # 묶음별 선택의 합집합, 순서 보존
    assert "NVDA" not in picked             # 묶음 밖 티커는 드롭


@needs_data
def test_ground_learns_theme_and_returns_verified_members(tmp_path):
    # ARCT는 공시 1건 → pending(콘솔 승인 대기)이라 유니버스에 서지 않는다
    filings = _filings({"MRNA": 3, "ALNY": 2, "IONS": 2, "VRTX": 2, "ARCT": 1})
    result = grounding.ground_us_theme(
        "mrna-Related", _chat_picking(["MRNA", "ALNY", "IONS", "VRTX", "ARCT"]),
        search_fn=lambda _t: {"total": len(filings), "filings": filings},
        lexicon_path=tmp_path / "lex.json",
    )
    assert result is not None
    name, symbols = result
    assert name == "mrna"  # 한정어를 벗긴 표기로 학습한다
    assert symbols == ["MRNA", "ALNY", "IONS", "VRTX"]
    entry = grounding.lexicon_entry("mrna", lexicon_path=tmp_path / "lex.json")
    assert entry["source"] == "edgar:fts"
    statuses = {m["symbol"]: m["status"] for m in entry["members"]}
    assert statuses["MRNA"] == "verified" and statuses["ARCT"] == "pending"


@needs_data
def test_ground_holds_back_when_members_below_minimum(tmp_path):
    """구성 미달은 테마 미성립 — 조용히 축소 반영하지 않고 되묻기로 넘긴다."""
    lex = tmp_path / "lex.json"
    result = grounding.ground_us_theme(
        "mrna", _chat_picking(["MRNA", "ALNY"]),
        search_fn=lambda _t: _found({"MRNA": 2, "ALNY": 2}), lexicon_path=lex,
    )
    assert result is None
    # 학습 자체는 저장된다 — 같은 표현을 다시 검색하지 않기 위해(부정 캐시)
    assert grounding.lexicon_entry("mrna", lexicon_path=lex) is not None


@needs_data
def test_learned_term_is_not_researched_twice(tmp_path):
    lex = tmp_path / "lex.json"
    calls = {"n": 0}

    def search(_term):
        calls["n"] += 1
        return _found({"MRNA": 2, "ALNY": 2, "IONS": 2, "VRTX": 2})

    picks = _chat_picking(["MRNA", "ALNY", "IONS", "VRTX"])
    first = grounding.ground_us_theme("mrna", picks, search_fn=search, lexicon_path=lex)
    second = grounding.ground_us_theme("mrna", picks, search_fn=search, lexicon_path=lex)
    assert first == second and calls["n"] == 1


def _age_entry(lexicon_path, key: str, days: float) -> None:
    """원장 항목의 검색 시각을 과거로 돌린다(경과 시간 의존 없는 TTL 검사)."""
    data = json.loads(lexicon_path.read_text())
    data[key]["searched_at"] = (
        datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    lexicon_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@needs_data
def test_under_minimum_entry_is_retried_sooner_than_success(tmp_path):
    """[회귀] 2026-08-27 — 미달 학습이 90일간 재시도를 막아 상류를 고쳐도 증상이 남았다.

    실측 오염: 하이픈 정규화 누락으로 카탈로그를 빗나간 테마 3건이 빈 원장 항목
    (verified 0곳)으로 굳어, 정규화를 고친 뒤에도 그 표현은 계속 되묻기로 끝났다.
    미달은 '테마가 아니다'라는 결론이 아니라 '이번 검색이 세우지 못했다'는 잠정
    상태이므로 짧은 주기(기본 3일)로 다시 찾아본다. 성공분은 종전 TTL(90일) 그대로다."""
    lex = tmp_path / "lex.json"
    calls = {"n": 0}

    def search_short(_term):
        calls["n"] += 1
        return _found({"MRNA": 2, "ALNY": 2})  # 확정 2곳 — 최소 구성 4곳 미달

    picks = _chat_picking(["MRNA", "ALNY"])
    assert grounding.ground_us_theme(
        "mrna", picks, search_fn=search_short, lexicon_path=lex) is None
    assert calls["n"] == 1

    # 미달 TTL 안(1일 경과)에서는 다시 찾지 않는다 — 매 턴 20초짜리 검색 반복 금지
    _age_entry(lex, "mrna", days=1)
    assert grounding.ground_us_theme(
        "mrna", picks, search_fn=search_short, lexicon_path=lex) is None
    assert calls["n"] == 1

    # 미달 TTL(3일)을 넘기면 다시 찾아본다 — 이번엔 구성이 차서 테마가 선다
    _age_entry(lex, "mrna", days=5)

    def search_full(_term):
        calls["n"] += 1
        return _found({"MRNA": 2, "ALNY": 2, "IONS": 2, "VRTX": 2})

    out = grounding.ground_us_theme(
        "mrna", _chat_picking(["MRNA", "ALNY", "IONS", "VRTX"]),
        search_fn=search_full, lexicon_path=lex)
    assert calls["n"] == 2 and out is not None and len(out[1]) == 4

    # 성공분은 짧은 TTL의 대상이 아니다 — 같은 5일 경과에도 다시 찾지 않는다
    _age_entry(lex, "mrna", days=5)
    assert grounding.ground_us_theme(
        "mrna", picks, search_fn=search_full, lexicon_path=lex) is not None
    assert calls["n"] == 2


def test_english_singular_plural_variants_resolve():
    """[회귀] 2026-08-27 — 정본은 복수, 입력은 단수라 한 글자 차이로 테마가 샜다.

    "US GLP-1 obesity-drug stocks"는 범주 접미('stocks')를 벗기면 단수가 되는데
    카탈로그 정본은 'GLP-1 obesity drugs'(복수)다. 이 미스로 카탈로그에 있는 테마가
    공시 학습으로 흘러 되묻기로 끝났다(게이트 88번). 분류 registry가 이미 허용하는
    단·복수 계약을 테마 축에도 맞춘다."""
    from engine.us_knowledge_graph import resolve_theme

    for spelling in ("obesity drugs", "obesity drug",
                     "GLP-1 obesity-drug", "US GLP-1 obesity-drug stocks"):
        resolved = resolve_theme(spelling)
        assert resolved is not None, spelling
        assert resolved[0] == "GLP-1 비만치료제", spelling
    # 변형은 후보를 더 만들 뿐이라 기존 해석은 그대로다
    assert resolve_theme("AI 반도체")[0] == "AI 반도체"
    assert resolve_theme("crypto-related stocks")[0] == "크립토 관련주"
    assert resolve_theme("cloud software")[0] == "클라우드 소프트웨어"


@needs_data
def test_us_etf_universe_does_not_take_industry_filter():
    """[회귀] 2026-08-27 — ETF × 업종 필터는 항상 공집합이라 조용히 0종목이 된다.

    ETF는 여러 기업을 묶은 **상품**이라 GICS 분류가 없다(정본이 us-etf-master.json).
    실측: US_ETF 31종 × 'Aerospace & Defense' → 0종목. 종전에는 산업명이 축 가드를
    빠져나가 테마로 학습되면서 이 조합을 가리고 있었고, 가드를 복구하자 드러났다.
    검증기는 ETF일 때 sectors를 etf_theme로 승격하며 비우므로 필터를 붙일 수 있는
    자리는 해석 체인뿐이다 — 거기서 적용하지 않고 미해결로 남긴다."""
    import ui_language
    from engine.nl_parser import ParsedStrategy
    from engine.universe_pit import filter_by_us_industry, resolve_us_symbols
    from strategy_conversation import primary

    # 전제: 교집합이 실제로 비어 있다(가드의 근거)
    assert filter_by_us_industry(resolve_us_symbols("us_etf"), "Aerospace & Defense") == []

    with ui_language.bind("en"):
        etf = ParsedStrategy(description="t", universe=["US_ETF"])
        assert primary._apply_us_industry(etf, "aerospace and defense") is False
        assert etf.us_industry is None            # 조용한 공집합을 만들지 않는다

        # 주식 유니버스에서는 종전대로 성립한다(가드가 과잉 차단하지 않는다)
        stocks = ParsedStrategy(description="t", universe=["US"])
        assert primary._apply_us_industry(stocks, "aerospace and defense") is True
        assert stocks.us_industry == "Aerospace & Defense"


def test_ampersand_and_and_are_the_same_classification(tmp_path):
    """[회귀] 2026-08-27 — '&'와 'and'가 갈려 GICS 산업명이 축 가드를 빠져나갔다.

    _token_key는 'and'를 무시하는데 조회 키(_norm)는 '&'를 그대로 둬서 정본
    'Aerospace & Defense'와 입력 'aerospace and defense'가 다른 키가 됐다. 그 결과
    산업명이 **테마로 학습**돼(양방향 축 가드 무력화) /us "On ITA, the US aerospace and
    defense ETF …"가 ETF 상품 대신 방산주 10곳 포트폴리오로 조립됐다(게이트 #81)."""
    from engine.us_industry_registry import classification_label
    from engine.us_knowledge_graph import resolve_theme

    for spelling in ("Aerospace & Defense", "aerospace and defense",
                     "Aerospace and Defense"):
        assert classification_label(spelling) == "Aerospace & Defense", spelling
    # 분류 라벨이면 테마 축에 서지 않는다(읽기 가드) — 학습도 막힌다(쓰기 가드)
    assert resolve_theme("aerospace and defense") is None

    def search(_term):
        raise AssertionError("분류 표현으로 공시 검색을 하면 안 된다")

    assert grounding.ground_us_theme(
        "aerospace and defense", _chat_picking([]), search_fn=search,
        lexicon_path=tmp_path / "lex.json") is None


def test_hyphen_is_a_word_separator_in_alias_keys():
    """[회귀] 2026-08-27 — 영어 레인의 하이픈 복합어가 카탈로그를 빗나갔다.

    /us 영어 게이트에서 테마 6건이 이 이유로 미해석 → 공시 학습으로 새고, 실패분이
    원장에 굳었다. 하이픈은 공백과 같은 낱말 구분자로 본다(정규화이지 해석이 아니다 —
    정본 별칭과 조회어가 같은 규칙을 통과하므로 짝이 어긋나지 않는다)."""
    from engine.us_knowledge_graph import _norm_key, resolve_theme

    assert _norm_key("humanoid-robotics") == _norm_key("humanoid robotics")
    assert _norm_key("data-center power") == _norm_key("data center power")
    for spelling in ("humanoid robotics", "humanoid-robotics"):
        assert resolve_theme(spelling)[0] == "휴머노이드 로봇", spelling
    for spelling in ("data center power", "data-center power infrastructure"):
        assert resolve_theme(spelling)[0] == "데이터센터 전력 인프라", spelling
    # 하이픈이 정체성인 표기도 그대로 잡힌다(양쪽이 같은 규칙을 통과하므로)
    assert resolve_theme("GLP-1")[0] == "GLP-1 비만치료제"
    assert resolve_theme("e-commerce")[0] == "이커머스"


def test_search_failure_is_not_persisted(tmp_path):
    """검색 실패(네트워크·차단)는 저장하지 않는다 — 복구 후 재시도할 수 있어야 한다."""
    lex = tmp_path / "lex.json"
    assert grounding.ground_us_theme(
        "mrna", _chat_picking([]), search_fn=lambda _t: None, lexicon_path=lex) is None
    assert not lex.exists()


@needs_data
def test_company_name_is_not_learned_as_theme(tmp_path):
    """개별 상장사 이름·티커는 테마가 아니다 — 검색 자체를 하지 않는다."""
    def search(_term):
        raise AssertionError("개별 기업명으로 검색하면 안 된다")

    for term in ("Moderna", "MRNA"):
        assert grounding.ground_us_theme(
            term, _chat_picking([]), search_fn=search,
            lexicon_path=tmp_path / "lex.json") is None


@needs_data
def test_classification_term_is_not_learned_as_theme(tmp_path):
    """[축 구분] 분류(GICS 섹터·산업) 표현은 테마로 학습하지 않는다 — 검색도 하지 않는다.

    실측 오염(2026-08-27): 축 판정이 없던 QA 실행에서 'healthcare'가 공시 학습으로
    21곳짜리 테마가 돼 그래프에 올라갔고, 업종 필터 미지원 계약 테스트가 깨졌다.
    분류는 정본(us_industry_registry)이지 관측 집합이 아니다."""
    def search(_term):
        raise AssertionError("분류 표현으로 공시 검색을 하면 안 된다")

    for term in ("healthcare", "Airlines", "US semiconductor stocks"):
        assert grounding.ground_us_theme(
            term, _chat_picking([]), search_fn=search,
            lexicon_path=tmp_path / "lex.json") is None


@needs_data
def test_learned_theme_carries_first_known_date(tmp_path):
    """테마는 시점을 가진 관측이다 — 소속 최초 공시일과 관측 창 시작일을 함께 남긴다.

    창(observed_from)을 함께 두지 않으면 "3년 전 생긴 테마"로 오독된다 — 검색 창이
    3년이라 모든 테마의 최초 관측일이 그 뒤에 몰리기 때문이다."""
    lex = tmp_path / "lex.json"
    found = _found({"MRNA": 2, "ALNY": 2, "IONS": 2, "VRTX": 2})
    for i, filing in enumerate(found["filings"]):
        filing["file_date"] = "2023-03-05" if i == 0 else "2024-06-01"
    found["observed_from"] = "2023-01-01"
    grounding.ground_us_theme(
        "mrna", _chat_picking(["MRNA", "ALNY", "IONS", "VRTX"]),
        search_fn=lambda _t: found, lexicon_path=lex,
    )
    entry = grounding.lexicon_entry("mrna", lexicon_path=lex)
    assert entry["first_known_date"] == "2023-03-05"
    assert entry["observed_from"] == "2023-01-01"
    assert all(m["first_known_date"] for m in entry["members"])


def test_kill_switch_blocks_grounding(tmp_path, monkeypatch):
    monkeypatch.setenv("US_TERM_GROUNDING", "off")
    assert grounding.ground_us_theme(
        "mrna", _chat_picking(["MRNA"]),
        search_fn=lambda _t: _found({"MRNA": 2}),
        lexicon_path=tmp_path / "lex.json") is None


# ── 지식그래프 학습 오버레이 ────────────────────────────────────────────────

@needs_data
def test_learned_overlay_resolves_in_knowledge_graph(tmp_path, monkeypatch):
    """학습된 테마는 다음 턴부터 검색 없이 그래프가 결정론으로 해석한다(verified만)."""
    from engine import us_knowledge_graph as kg

    lex = tmp_path / "us-term-lexicon.json"
    lex.write_text(json.dumps({"mrna": {
        "term": "mrna", "source": "edgar:fts", "searched_at": "2026-08-26T00:00:00+00:00",
        "members": [
            {"symbol": "MRNA", "name": "Moderna", "support": 3, "status": "verified"},
            {"symbol": "ALNY", "name": "Alnylam", "support": 2, "status": "verified"},
            {"symbol": "ARCT", "name": "Arcturus", "support": 1, "status": "pending"},
        ],
    }}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lex)
    monkeypatch.setattr(kg, "_CACHED", None)
    monkeypatch.setattr(kg, "_CACHED_MTIMES", None)

    resolved = kg.resolve_theme("mrna-Related")
    assert resolved is not None
    name, symbols = resolved
    assert name == "mrna"
    assert symbols == ["MRNA", "ALNY"]  # pending(ARCT)은 그래프에 서지 않는다
    # 큐레이션 정본은 학습분보다 우선한다(시드 > 카탈로그 > 학습)
    assert kg.resolve_theme("AI 반도체")[0] == "AI 반도체"


# ── 회사 앵커 축: 'X 관련주'(2026-08-27) ────────────────────────────────────

def test_group_suffix_is_a_notation_judgement():
    """범주 접미 판정은 어미 표기뿐 — 시장 접두는 범주를 바꾸지 않는다."""
    from engine.us_knowledge_graph import has_group_suffix

    assert has_group_suffix("nvidia Related Stock")
    assert has_group_suffix("엔비디아 관련주")
    assert has_group_suffix("crypto-related stocks")
    assert not has_group_suffix("애플")
    assert not has_group_suffix("미국 애플")   # 접두는 정체성만 좁힌다
    assert not has_group_suffix("AI 반도체")
    assert not has_group_suffix(None)


@needs_data
def test_bare_company_name_is_not_a_related_set(tmp_path):
    """접미 없는 회사명은 단일 종목 지정 소관 — 관련주 학습이 가로채지 않는다."""
    def search(_term):
        raise AssertionError("접미 없는 회사명으로 검색하면 안 된다")

    for term in ("Nvidia", "NVDA"):
        assert grounding.ground_us_company_related(
            term, _chat_picking([]), search_fn=search,
            lexicon_path=tmp_path / "lex.json") is None


@needs_data
def test_non_company_anchor_is_not_a_related_set(tmp_path):
    """앵커가 정본 상장사가 아니면 이 축이 아니다 — 테마 학습 소관으로 넘긴다."""
    def search(_term):
        raise AssertionError("테마어를 회사 앵커로 검색하면 안 된다")

    assert grounding.ground_us_company_related(
        "quantum computing stocks", _chat_picking([]), search_fn=search,
        lexicon_path=tmp_path / "lex.json") is None


@needs_data
def test_company_related_learns_relations_and_keeps_anchor(tmp_path):
    """'Nvidia 관련주' → 앵커 이름으로 검색하고 관계 기업을 학습한다(앵커 자신 포함).

    [회귀] 2026-08-27 사고: 회사명은 테마 색인에서 제외돼 있고 테마 학습도 회사명을
    막으므로, 이 축이 없으면 'nvidia 관련주'는 갈 곳이 없어 표현이 통째로 사라졌다."""
    lex = tmp_path / "lex.json"
    queried: list[str] = []

    def search(term):
        queried.append(term)
        return _found({"NVDA": 2, "VRTX": 2, "JPM": 2, "BA": 2}, total=500)

    # 심사가 앵커를 빠뜨려도 앵커는 관계 집합에 남는다(가장 직접적인 종목)
    out = grounding.ground_us_company_related(
        "nvidia Related Stock", _chat_picking(["VRTX", "JPM", "BA"]),
        search_fn=search, lexicon_path=lex,
    )
    assert queried == ["Nvidia"]            # 질의어는 접미를 벗긴 정본 회사명
    assert out is not None
    label, symbols = out
    assert label == "Nvidia 관련주"          # 표시 라벨(요청 언어 ko 기본)
    assert entry_term(lex) == "Nvidia 관련주"  # 원장 표기는 언어와 무관한 한국어 정본
    assert symbols[0] == "NVDA" and set(symbols) == {"NVDA", "VRTX", "JPM", "BA"}
    entry = grounding.company_related_entry("NVDA", lexicon_path=lex)
    assert entry["kind"] == "company_related" and entry["anchor"] == "NVDA"


@needs_data
def test_company_related_overlay_resolves_by_anchor_not_spelling(tmp_path, monkeypatch):
    """학습된 관계 집합의 조회 키는 **앵커 티커**다 — 한국어/영어 표기 차가 미스를
    만들면 안 된다. 그래서 테마 색인에는 넣지 않는다(별칭 경쟁 없음)."""
    from engine import us_knowledge_graph as kg

    lex = tmp_path / "us-term-lexicon.json"
    lex.write_text(json.dumps({"related:NVDA": {
        "term": "Nvidia 관련주", "kind": "company_related", "anchor": "NVDA",
        "source": "edgar:fts", "searched_at": "2026-08-27T00:00:00+00:00",
        "members": [
            {"symbol": "NVDA", "name": "Nvidia", "support": 3, "status": "verified"},
            {"symbol": "VRTX", "name": "Vertex", "support": 2, "status": "verified"},
            {"symbol": "ARCT", "name": "Arcturus", "support": 1, "status": "pending"},
        ],
    }}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lex)
    monkeypatch.setattr(kg, "_CACHED", None)
    monkeypatch.setattr(kg, "_CACHED_MTIMES", None)

    for spelling in ("nvidia Related Stock", "엔비디아 관련주", "NVDA related stocks"):
        resolved = kg.resolve_company_related(spelling)
        assert resolved is not None, spelling
        assert resolved == ("Nvidia 관련주", ["NVDA", "VRTX"])  # pending은 서지 않는다
    # 접미 없는 표기는 이 축이 아니고, 테마 색인도 오염되지 않는다
    assert kg.resolve_company_related("Nvidia") is None
    assert kg.resolve_theme("Nvidia 관련주") is None
    assert kg.resolve_theme("Nvidia") is None


# ── 분류 축: 필터 승격(FR-STR-074 ⑩) ────────────────────────────────────────

@needs_data
def test_industry_becomes_filter_not_symbol_list():
    """분류는 유니버스 **필터**다 — 종목 목록으로 전개하면 지수와 조합할 수 없다.

    실측 근거: 'airline'을 테마로 학습하면 보잉·에어캡이 섞인 22곳이 되고, 명부로
    전개하면 지수 선택과 교집합할 수 없으며 섹터 단위(1,000곳)는 세울 수조차 없다.
    """
    import ui_language
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.interpreter.models import (
        StrategyCondition, StrategyIntent, StrategySpec, UniverseSpec, ValidationReport,
    )
    from strategy_conversation.validation.capability_validator import validate_capability

    def _intent(markets, sectors):
        return StrategyIntent(intent="CREATE_STRATEGY", strategy=StrategySpec(
            universe=UniverseSpec(markets=markets, sectors=sectors),
            entry_conditions=[
                StrategyCondition(factor="technical.rsi", operator="<=", value=30.0)],
        ))

    ready = ValidationReport(is_valid=True, status="READY")
    with ui_language.bind("en"):
        # 시장 미언급 + 업종 → 미국 전체가 기본(S&P500이면 지수 안 3~4곳으로 조용히 좁혀진다)
        intent = _intent([], ["airline"])
        errors, _w, unsupported, _f = validate_capability(intent)
        parsed = compile_strategy(intent, ready, "airline stocks")
        assert errors == [] and unsupported == []
        assert parsed.universe == ["US"] and parsed.us_industry == "Airlines"
        assert not parsed.target_symbols  # 명부 전개가 아니다

        # 지수를 명시하면 교집합
        intent2 = _intent(["SP500"], ["airline"])
        validate_capability(intent2)
        parsed2 = compile_strategy(intent2, ready, "S&P 500 airline stocks")
        assert parsed2.universe == ["SP500"] and parsed2.us_industry == "Airlines"

        # 섹터 단위(명부 1,000곳 이상)도 필터로는 정상이다 — 종전에는 미지원 안내였다
        intent3 = _intent([], ["healthcare"])
        errors3, _w3, _u3, _f3 = validate_capability(intent3)
        parsed3 = compile_strategy(intent3, ready, "healthcare stocks")
        assert errors3 == [] and parsed3.us_industry == "Health Care"

        # 분류도 테마도 아닌 표현은 종전대로 미지원 안내
        intent4 = _intent([], ["화성테마"])
        errors4, _w4, unsupported4, _f4 = validate_capability(intent4)
        assert errors4 and unsupported4

    # 한국 요청은 불변 — 미국 분류 라벨이 한국 섹터 정본을 밀어내지 않는다
    intent_kr = _intent(["KOSPI"], ["반도체"])
    validate_capability(intent_kr)
    parsed_kr = compile_strategy(intent_kr, ready, "반도체 종목")
    assert parsed_kr.sector == "반도체" and parsed_kr.us_industry is None


@needs_data
def test_industry_filter_reaches_engine_request():
    """us_industry가 canonical DSL·백테스트 요청까지 실린다 — 스키마 미선언이면
    model_dump가 조용히 버려 필터가 사라진다(ranking_metric 0거래 사고와 같은 함정)."""
    from engine.nl_parser import ParsedStrategy
    from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl

    parsed = ParsedStrategy(description="t", universe=["US"], us_industry="Airlines")
    assert to_canonical_strategy_dsl(parsed)["us_industry"] == "Airlines"
    assert to_backtest_request(parsed, resolve_symbols=False)["us_industry"] == "Airlines"
    # 필터 없는 기존 전략의 해시는 변하지 않는다(None은 DSL에서 제거)
    assert "us_industry" not in to_canonical_strategy_dsl(ParsedStrategy(description="t"))


@needs_data
def test_axis_order_classification_beats_curated_theme():
    """축 순서: 분류(정본) → 카탈로그·시드 테마 → 공시 학습.

    실측(2026-08-27): 시드의 산업형 테마는 표본 수준이라 'airlines' 4곳 vs 분류 18곳,
    'restaurants' 5곳 vs 54곳이다 — 업종 이름에는 업종 분류가 답해야 한다. 분류가
    표현할 수 없는 특화 테마(AI 반도체)는 그대로 카탈로그가 잡는다."""
    import ui_language
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.primary import _resolve_sector_terms_us

    with ui_language.bind("en"):
        for term, expect_industry in (("airlines", "Airlines"),
                                      ("semiconductors", "Semiconductors")):
            parsed = ParsedStrategy(description="t", universe=["US"])
            question, _chips = _resolve_sector_terms_us(parsed, [term])
            assert question is None
            assert parsed.us_industry == expect_industry
            assert not parsed.target_symbols   # 필터이지 명부 전개가 아니다
            assert parsed.universe_source == "industry"

        # 분류에 없는 특화 테마는 카탈로그가 잡는다(지정 종목 + 테마 출처 표기)
        parsed = ParsedStrategy(description="t", universe=["US"])
        assert _resolve_sector_terms_us(parsed, ["AI 반도체"])[0] is None
        assert parsed.theme_universe == "AI 반도체" and parsed.target_symbols
        assert parsed.universe_source == "theme_catalog" and parsed.us_industry is None


@needs_data
def test_us_modify_lane_uses_us_axis_chain():
    """[시장 격리] 수정 턴의 유니버스 교체도 미국 축 체인을 탄다 — 한국 기계 금지.

    생성 레인에서 막아 둔 구멍이 수정 레인에 남아 있었다(2026-08-27 발견): /us에서
    테마·업종을 바꾸면 한국 카탈로그·네이버 검색 그라운딩이 불렸다."""
    import inspect

    import ui_language
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation import primary

    with ui_language.bind("en"):
        # 업종 → 업종 교체
        parsed = ParsedStrategy(description="t", universe=["US"], us_industry="Airlines",
                                universe_source="industry")
        assert primary._resolve_us_universe_change(parsed, "restaurants", []) is None
        assert parsed.us_industry == "Restaurants"

        # 업종 → 테마 교체(이전 축의 흔적이 남지 않는다)
        parsed2 = ParsedStrategy(description="t", universe=["SP500"], us_industry="Airlines")
        assert primary._resolve_us_universe_change(parsed2, "AI 반도체", []) is None
        assert parsed2.us_industry is None and parsed2.theme_universe == "AI 반도체"

        # 해석 못 한 표현은 전략을 바꾸지 않고 되묻는다
        parsed3 = ParsedStrategy(description="t", universe=["SP500"],
                                 theme_universe="AI 반도체", target_symbols=["NVDA"])
        ask = primary._resolve_us_universe_change(parsed3, "화성테마", [])
        assert ask is not None and "화성테마" in ask[0]

    # 배선 회귀 가드 — 수정 레인 호출부가 시장 문맥으로 갈라지는지
    source = inspect.getsource(primary)
    assert "_resolve_us_universe_change(parsed, theme_terms[0]" in source


@needs_data
def test_industry_aliases_are_consistent_across_spellings():
    """한 단어는 한 축에만 닿는다(2026-08-27 시드 정리).

    종전에는 영문 별칭('airlines')은 분류로, 한글 이름('항공사')은 시드 테마(4곳)로
    갈렸다 — 같은 뜻인데 축이 갈리면 결과 종목 수부터 달라진다. 산업명 중복 테마 11종을
    시드에서 걷어내고 별칭을 분류 registry로 옮겼다."""
    from engine.us_industry_registry import classification_label
    from engine.us_knowledge_graph import resolve_theme

    for kr, en, label in (("항공사", "airlines", "Airlines"),
                          ("태양광주", "solar", "Solar"),
                          ("외식", "restaurants", "Restaurants"),
                          ("의료기기", "medical devices", "Medical Devices")):
        assert classification_label(kr) == label
        assert classification_label(en) == label
        assert resolve_theme(kr) is None and resolve_theme(en) is None

    # 개념 앵커(반도체 산업)는 구조가 붙어 있어 노드로 남지만, 표현은 분류로 통일된다
    assert classification_label("반도체") == "Semiconductors"
    assert classification_label("semiconductor") == "Semiconductors"


@needs_data
def test_company_related_expression_survives_the_us_chain(tmp_path, monkeypatch):
    """[회귀] 2026-08-27 사고 전수 — 'nvidia 관련주'가 유니버스로 서고, 못 서면 되묻는다.

    사고 당시에는 셋 다 실패했다: ① 분류기가 문구 속 회사명만 보고 SINGLE_STOCK으로
    접었고 ② 상류가 그것을 '해석 완료'로 도장 찍었고 ③ 회사 앵커 축이 없어 체인에
    도달해도 갈 곳이 없었다. 결과는 되묻기도 안내도 없는 미국 전체 유니버스였다."""
    import ui_language
    from engine import us_knowledge_graph as kg
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation import primary
    from strategy_conversation.tools.catalog import (
        ClassifyUniverseIn, _classify_universe,
    )

    # ① 분류: 범주 접미가 붙은 표현은 단일 종목이 아니다(접미 없는 표기는 그대로 종목)
    assert _classify_universe(
        ClassifyUniverseIn(text="nvidia Related Stock")).universe_type == "CONCEPT"
    single = _classify_universe(ClassifyUniverseIn(text="nvidia"))
    assert (single.universe_type, single.canonical) == ("SINGLE_STOCK", "NVDA")

    lex = tmp_path / "us-term-lexicon.json"
    lex.write_text(json.dumps({"related:NVDA": {
        "term": "Nvidia 관련주", "kind": "company_related", "anchor": "NVDA",
        "source": "edgar:fts", "searched_at": "2026-08-27T00:00:00+00:00",
        "members": [
            {"symbol": s, "name": s, "support": 2, "status": "verified"}
            for s in ("NVDA", "VRTX", "JPM", "BA")
        ],
    }}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lex)
    monkeypatch.setattr(kg, "_CACHED", None)
    monkeypatch.setattr(kg, "_CACHED_MTIMES", None)

    with ui_language.bind("en"):
        # ③ 체인: 학습된 관계 집합이 지정 종목으로 전개된다(출처는 회사 앵커 축)
        parsed = ParsedStrategy(description="t", universe=["US"])
        assert primary._resolve_sector_terms_us(
            parsed, ["nvidia Related Stock"]) == (None, None)
        # /us(en)에서는 표시 라벨도 영어다 — 요약 카드에 한국어가 섞이면 안 된다
        assert parsed.theme_universe == "Nvidia-related stocks"
        assert set(parsed.target_symbols) == {"NVDA", "VRTX", "JPM", "BA"}
        assert parsed.universe_source == "company_related"

        # 학습 이력이 없는 앵커는 조용히 넘어가지 않는다 — 되묻기로 표면화한다
        # (그라운딩은 네트워크 검색이므로 여기서는 차단하고 되묻기까지만 확인)
        monkeypatch.setenv("US_TERM_GROUNDING", "off")
        parsed2 = ParsedStrategy(description="t", universe=["US"])
        question, _chips = primary._resolve_sector_terms_us(
            parsed2, ["Tesla related stocks"])
        assert question is not None and "Tesla related stocks" in question
        assert not parsed2.target_symbols
