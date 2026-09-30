"""학습 어휘집 저장소(engine/lexicon_store) — 공유 DB가 정본이라 환경 간 해석이 갈리지 않는다.

2026-09-30 사고: 'bts 관련주 투자 전략'이 로컬에선 테마 상장사 13곳, 프로덕션에선 업종
'미디어/엔터'로 풀렸다. 인터프리터 출력은 양쪽 모두 universe.sectors=["bts"]로 같았고,
갈린 곳은 git 밖 파일 어휘집(data/term_lexicon.json)이었다 — 로컬은 07-25 학습분(K-팝
기획사 관계 verified), 프로덕션은 첫 검색 출처 1건이라 pending으로 저장돼 굳었다.
"""

import json

import pytest

import engine.knowledge_graph as kg
from engine import lexicon_store
from engine.lexicon_store import DEFAULT_PATH, merge_entry

# 프로덕션 파일 어휘집에 실제로 저장돼 있던 'bts' 항목(2026-09-30 00:41 UTC 학습분)
_PROD_BTS = {
    "term": "bts", "definition": "방탄소년단(BTS)", "sector": "미디어/엔터",
    "searched_at": "2026-09-30T00:41:03+00:00",
    "edges": [
        {"type": "related_to", "target": "kpop-agency", "target_name": "K-팝 기획사",
         "support": 1, "status": "pending", "evidence": ["https://a.example/1"]},
    ],
}
# 로컬 파일 어휘집의 'bts' 관계(07-25 학습분, 출처 4건)
_LOCAL_BTS = {
    "term": "BTS", "definition": "K-POP 그룹", "sector": "미디어/엔터",
    "edges": [
        {"type": "related_to", "target": "kpop-agency", "target_name": "K-팝 기획사",
         "support": 4, "status": "verified", "evidence": ["https://b.example/1"]},
    ],
}


@pytest.fixture
def db_store(app_db, monkeypatch):
    conn = app_db
    if not conn.execute("SELECT to_regclass('public.\"TermLexiconEntry\"')").fetchone()[0]:
        pytest.skip("simons_test에 TermLexiconEntry 마이그레이션 미적용")
    monkeypatch.setenv("TERM_LEXICON_STORE", "db")
    monkeypatch.setattr(lexicon_store, "_DB_CACHE", None)
    monkeypatch.setattr(kg, "_LEXICON_PATH", DEFAULT_PATH)
    monkeypatch.setattr(kg, "_CACHED", None)
    yield conn
    lexicon_store._DB_CACHE = None
    kg._CACHED = None


def test_default_path_goes_to_db_other_paths_to_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TERM_LEXICON_STORE", "db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x@localhost/y")
    assert lexicon_store.uses_db(DEFAULT_PATH)
    assert not lexicon_store.uses_db(tmp_path / "term_lexicon.json")
    monkeypatch.setenv("TERM_LEXICON_STORE", "file")
    assert not lexicon_store.uses_db(DEFAULT_PATH)


def test_file_store_roundtrip(tmp_path):
    path = tmp_path / "lex.json"
    lexicon_store.save_entry(path, "a", {"term": "A"})
    lexicon_store.save_entry(path, "b", {"term": "B"})
    assert list(lexicon_store.snapshot(path)) == ["a", "b"]
    copy = lexicon_store.load(path)
    copy["a"]["term"] = "changed"
    assert lexicon_store.snapshot(path)["a"]["term"] == "A"  # 사본 수정이 캐시를 오염시키지 않는다


def test_db_write_is_visible_to_another_environment(db_store):
    """한 환경(프로세스)이 저장한 항목을 다른 환경이 캐시 만료 후 그대로 읽는다."""
    lexicon_store.save_entry(DEFAULT_PATH, "bts", _LOCAL_BTS)
    v1 = lexicon_store.version()
    assert lexicon_store.snapshot()["bts"]["term"] == "BTS"

    lexicon_store._DB_CACHE = None  # 다른 환경 = 캐시가 없는 새 프로세스
    assert lexicon_store.snapshot()["bts"] == _LOCAL_BTS
    lexicon_store.save_entry(DEFAULT_PATH, "bts", _PROD_BTS)
    assert lexicon_store.version() != v1
    rows = db_store.execute('SELECT count(*) FROM "TermLexiconEntry"').fetchone()[0]
    assert rows == 1  # 키 단위 upsert


def test_db_lexicon_drives_theme_companies(db_store):
    """사고 재현: pending만 있으면 테마 상장사가 없고(업종 근사로 빠짐), 같은 DB 항목이
    verified로 합쳐지면 모든 환경이 같은 테마 상장사를 본다."""
    lexicon_store.save_entry(DEFAULT_PATH, "bts", _PROD_BTS)
    assert kg.theme_backtest_companies("bts") is None

    merged = merge_entry(lexicon_store.snapshot()["bts"], _LOCAL_BTS)
    lexicon_store.save_entry(DEFAULT_PATH, "bts", merged)
    kg._CACHED = None
    theme = kg.theme_backtest_companies("bts")
    assert theme is not None
    assert {"352820", "035900", "041510"} <= {c["symbol"] for c in theme["companies"]}


def test_db_read_failure_keeps_last_snapshot(db_store, monkeypatch):
    lexicon_store.save_entry(DEFAULT_PATH, "bts", _LOCAL_BTS)
    lexicon_store._DB_CACHE = None
    assert "bts" in lexicon_store.snapshot()
    monkeypatch.setattr(lexicon_store, "_DB_TTL_S", 0.0)

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(lexicon_store, "_db_fetch", boom)
    assert "bts" in lexicon_store.snapshot()


def test_merge_entry_upgrades_only_pending_edges():
    existing = {"term": "t", "sector": None, "edges": [
        {"type": "related_to", "target": "a", "status": "pending"},
        {"type": "related_to", "target": "b", "status": "rejected"},
    ]}
    incoming = {"term": "t", "sector": "반도체", "edges": [
        {"type": "related_to", "target": "a", "status": "verified"},
        {"type": "related_to", "target": "b", "status": "verified"},
        {"type": "related_to", "target": "c", "status": "verified"},
    ]}
    merged = merge_entry(existing, incoming)
    status = {e["target"]: e["status"] for e in merged["edges"]}
    # 운영 콘솔의 반려(rejected)는 가져오기가 뒤집지 않는다
    assert status == {"a": "verified", "b": "rejected", "c": "verified"}
    assert merged["sector"] == "반도체"
    assert merge_entry({"sector": "미디어/엔터"}, {"sector": "반도체"})["sector"] == "미디어/엔터"
    assert json.dumps(existing).count("pending") == 1  # 입력 원본은 건드리지 않는다
