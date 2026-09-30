"""검색 그라운딩 학습 어휘집 저장소 — 공유 DB(TermLexiconEntry)가 정본이다.

종전엔 git 밖 파일(data/term_lexicon.json)을 환경마다 따로 키워 같은 문장이 환경마다
다르게 풀렸다(2026-09-30 'bts 관련주': 로컬은 K-팝 기획사 관계 verified로 테마 상장사
13곳, 프로덕션은 첫 검색 출처 1건이라 pending → 업종 근사 '미디어/엔터'로 굳음). 로컬과
운영은 같은 Supabase를 쓰므로, 어휘집을 DB에 두면 한 곳에서 배운 내용을 모두가 읽는다.

경로 계약: 호출부는 종전처럼 경로를 넘긴다. **기본 경로(DEFAULT_PATH)만 DB로** 가고,
다른 경로(테스트의 임시 파일·스크립트의 명시 경로)는 파일로 간다. TERM_LEXICON_STORE=file
이면 기본 경로도 파일이다(테스트 conftest가 고정 — 테스트가 공유 DB에 쓰지 않게).

읽기: snapshot()은 공유 캐시(수정 금지, 파싱 핫패스용), load()는 수정 가능한 사본.
DB 읽기는 _DB_TTL_S 동안 캐시한다(다른 환경·콘솔의 변경은 그 안에 반영). 같은 프로세스의
쓰기는 캐시를 즉시 갱신한다. DB 장애는 직전 스냅샷(없으면 빈 어휘집)으로 fail-open —
어휘집이 비면 종전 '파일 없음'과 같이 검색 그라운딩·되묻기 체인이 담당한다.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "term_lexicon.json"

_DB_TTL_S = float(os.getenv("TERM_LEXICON_DB_TTL_S", "30"))

_LOCK = threading.Lock()
# 파일: path → (mtime, lexicon) / DB: (loaded_at, lexicon, version)
_FILE_CACHE: dict[str, tuple[float, dict]] = {}
_DB_CACHE: Optional[tuple[float, dict, int]] = None
_DB_VERSION = 0


def uses_db(path: Path) -> bool:
    if os.getenv("TERM_LEXICON_STORE", "db").lower() == "file":
        return False
    if Path(path) != DEFAULT_PATH:
        return False
    return os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://"))


# ─── 파일 ─────────────────────────────────────────────────────────────────────

def _read_file(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _file_mtime(path: Path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _file_snapshot(path: Path) -> dict:
    mtime = _file_mtime(path)
    if mtime == 0.0:
        return {}
    cached = _FILE_CACHE.get(str(path))
    if cached is not None and cached[0] == mtime:
        return cached[1]
    lexicon = _read_file(path)
    _FILE_CACHE[str(path)] = (mtime, lexicon)
    return lexicon


def _file_save(path: Path, key: str, entry: dict) -> None:
    lexicon = _read_file(path)
    lexicon[key] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lexicon, f, ensure_ascii=False, indent=1)
    tmp.replace(path)


# ─── DB ───────────────────────────────────────────────────────────────────────

def _db_fetch() -> dict:
    import db

    conn = db.connect()
    try:
        rows = conn.execute(
            'SELECT "key", "entry" FROM "TermLexiconEntry" ORDER BY "createdAt", "key"'
        ).fetchall()
    finally:
        conn.close()
    return {r[0]: r[1] for r in rows if isinstance(r[1], dict)}


def _db_snapshot() -> tuple[dict, int]:
    global _DB_CACHE, _DB_VERSION
    now = time.monotonic()
    cached = _DB_CACHE
    if cached is not None and now - cached[0] < _DB_TTL_S:
        return cached[1], cached[2]
    try:
        lexicon = _db_fetch()
    except Exception:  # noqa: BLE001 — 어휘집 장애가 파싱을 깨면 안 된다(fail-open)
        logger.warning("학습 어휘집 DB 읽기 실패 — 직전 스냅샷 유지", exc_info=True)
        if cached is not None:
            _DB_CACHE = (now, cached[1], cached[2])
            return cached[1], cached[2]
        return {}, _DB_VERSION
    with _LOCK:
        if cached is None or lexicon != cached[1]:
            _DB_VERSION += 1
        _DB_CACHE = (now, lexicon, _DB_VERSION)
    return lexicon, _DB_VERSION


def _db_save(key: str, entry: dict) -> None:
    global _DB_CACHE, _DB_VERSION
    import db
    from psycopg.types.json import Jsonb

    conn = db.connect()
    try:
        with conn:
            conn.execute(
                'INSERT INTO "TermLexiconEntry" ("key", "entry", "createdAt", "updatedAt") '
                "VALUES (?, ?, clock_timestamp(), clock_timestamp()) "
                'ON CONFLICT ("key") DO UPDATE SET "entry" = EXCLUDED."entry", '
                '"updatedAt" = clock_timestamp()',
                (key, Jsonb(entry)),
            )
    finally:
        conn.close()
    with _LOCK:
        if _DB_CACHE is not None:
            lexicon = dict(_DB_CACHE[1])
            lexicon[key] = entry
            _DB_VERSION += 1
            _DB_CACHE = (_DB_CACHE[0], lexicon, _DB_VERSION)


# ─── 공개 API ─────────────────────────────────────────────────────────────────

def snapshot(path: Path = DEFAULT_PATH) -> dict:
    """읽기 전용 공유 스냅샷 — 호출부는 수정하지 않는다."""
    if uses_db(path):
        return _db_snapshot()[0]
    return _file_snapshot(Path(path))


def load(path: Path = DEFAULT_PATH) -> dict:
    """수정 가능한 사본."""
    return copy.deepcopy(snapshot(path))


def version(path: Path = DEFAULT_PATH) -> tuple:
    """변경 감지 토큰 — 지식그래프 재합성 캐시 키."""
    if uses_db(path):
        return ("db", _db_snapshot()[1])
    return ("file", _file_mtime(Path(path)))


def save_entry(path: Path, key: str, entry: dict) -> None:
    """항목 하나를 저장한다(키 단위 upsert — 동시 요청이 서로의 항목을 지우지 않는다)."""
    if uses_db(path):
        try:
            _db_save(key, entry)
        except Exception:  # noqa: BLE001 — 저장 실패는 다음 언급 때 재검색으로 복구된다
            logger.warning("학습 어휘집 DB 저장 실패 | key=%r", key, exc_info=True)
        return
    with _LOCK:
        _file_save(Path(path), key, entry)


def merge_edges(existing_edges: list, incoming_edges: list) -> list[dict]:
    """가져오기 병합 — 기존 검토 결정(verified/rejected)은 유지하고, 기존 pending만
    들어오는 verified로 올리며, 기존에 없는 (type, target)은 더한다."""
    incoming = {
        (e.get("type"), e.get("target")): e for e in incoming_edges if isinstance(e, dict)
    }
    merged: list[dict] = []
    seen: set = set()
    for e in existing_edges:
        if not isinstance(e, dict):
            continue
        key = (e.get("type"), e.get("target"))
        seen.add(key)
        new = incoming.get(key)
        if e.get("status") == "pending" and new and new.get("status") == "verified":
            merged.append(dict(new))
        else:
            merged.append(e)
    merged.extend(dict(e) for k, e in incoming.items() if k not in seen)
    return merged


def merge_entry(existing: Optional[dict], incoming: dict) -> dict:
    """가져오기 항목 병합 — 기존 항목이 기준(정의·섹터는 최신 학습분), 섹터가 비면 들어온 값."""
    if not isinstance(existing, dict):
        return incoming
    combined = dict(existing)
    if not combined.get("sector") and incoming.get("sector"):
        combined["sector"] = incoming["sector"]
    combined["edges"] = merge_edges(existing.get("edges") or [], incoming.get("edges") or [])
    return combined
