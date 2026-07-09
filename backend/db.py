"""공용 앱 DB 어댑터 — Supabase Postgres.

여러 백엔드 모듈이 `sqlite3`로 앱 DB(Prisma dev.db)를 직접 열던 것을 이 어댑터 하나로
대체한다. 호출부 변경을 최소화하기 위해 sqlite3와 유사한 인터페이스를 제공하되,
실제로는 psycopg(v3)로 Postgres에 연결한다.

핵심 방언 처리(한 곳에서):
- `?` 플레이스홀더 → `%s` 변환(psycopg 스타일). 리터럴 `%`는 `%%`로 먼저 이스케이프.
- `sqlite3.Row`처럼 정수 인덱스(`row[0]`)와 컬럼명(`row["col"]`) 둘 다 지원하는 row.
- `with conn:` 트랜잭션 시맨틱을 sqlite3와 동일하게(정상=commit, 예외=rollback, 연결 유지).
- Prisma 전용 URL 쿼리 파라미터(pgbouncer/connection_limit 등) 제거 — libpq가 거부함.
- Transaction pooler(pgbouncer) 대응: prepared statement 비활성(prepare_threshold=None).

DateTime 컬럼: SQLite 시절엔 Prisma가 epoch ms 정수로 저장해 Python도 정수로 넣었지만,
Postgres에선 `timestamp`이므로 `db.now()`가 돌려주는 tz-aware datetime 객체를 넣어야 한다.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg

# best-effort DB 접근부의 `except db.Error`용 — psycopg 에러 최상위 타입 재노출.
Error = psycopg.Error

# libpq가 이해하지 못하는 Prisma 전용 쿼리 파라미터 — 연결 전 제거한다.
_PRISMA_ONLY_PARAMS = {"pgbouncer", "connection_limit", "pool_timeout", "schema"}


def _clean_url(url: str) -> str:
    parts = urlsplit(url)
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _PRISMA_ONLY_PARAMS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def _translate(sql: str) -> str:
    """sqlite 스타일 SQL을 psycopg 스타일로. 리터럴 `%`를 `%%`로 이스케이프한 뒤
    positional `?`를 `%s`로 바꾼다. (이 코드베이스엔 문자열 리터럴 속 `?`가 없다.)"""
    return sql.replace("%", "%%").replace("?", "%s")


class _Row:
    """sqlite3.Row 호환 — 정수 인덱스와 컬럼명 접근을 모두 지원한다."""

    __slots__ = ("_cols", "_vals", "_map")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals
        self._map = None

    def _index(self):
        if self._map is None:
            self._map = {c: i for i, c in enumerate(self._cols)}
        return self._map

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._vals[key]
        return self._vals[self._index()[key]]

    def get(self, key, default=None):
        i = self._index().get(key)
        return default if i is None else self._vals[i]

    def keys(self):
        return list(self._cols)

    def __contains__(self, key):
        return key in self._index()

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


def _hybrid_row_factory(cursor):
    desc = cursor.description
    cols = [c.name for c in desc] if desc else []

    def make(values):
        return _Row(cols, values)

    return make


class _Cursor:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        self._cur.execute(_translate(sql), tuple(params) if params else ())
        return self

    def executemany(self, sql, seq):
        self._cur.executemany(_translate(sql), seq)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size) if size is not None else self._cur.fetchmany()

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __iter__(self):
        return iter(self._cur)

    def close(self):
        self._cur.close()


class _Conn:
    """sqlite3.Connection 유사 래퍼."""

    def __init__(self, pg):
        self._pg = pg

    def execute(self, sql, params=()):
        return _Cursor(self._pg.execute(_translate(sql), tuple(params) if params else ()))

    def executemany(self, sql, seq):
        cur = self._pg.cursor()
        cur.executemany(_translate(sql), seq)
        return _Cursor(cur)

    def cursor(self):
        return _Cursor(self._pg.cursor())

    def commit(self):
        self._pg.commit()

    def rollback(self):
        self._pg.rollback()

    def close(self):
        self._pg.close()

    @property
    def raw(self):
        return self._pg

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # sqlite3 시맨틱: 정상 종료=commit, 예외=rollback. 연결은 닫지 않는다.
        if exc_type is None:
            self._pg.commit()
        else:
            self._pg.rollback()
        return False


def connect() -> _Conn:
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://")):
        # db.Error(=psycopg.Error)로 던져야 advisor/research 등 기존 "DB 접근 실패해도
        # 조용히 폴백" 코드의 `except db.Error:` 가드가 이 경우도 정상적으로 흡수한다
        # (RuntimeError는 그 가드를 그냥 통과해 버려 best-effort 설계가 깨진다).
        raise Error(
            f"DATABASE_URL이 Postgres가 아닙니다(앞부분={url[:16]!r}). "
            "Supabase 이관 후에는 postgres URL이 필요합니다."
        )
    return _Conn(psycopg.connect(_clean_url(url), prepare_threshold=None, row_factory=_hybrid_row_factory))


def table_exists(conn, name: str) -> bool:
    """public 스키마에 해당 테이블이 있는지."""
    row = conn.execute("SELECT to_regclass(?)", (f'public."{name}"',)).fetchone()
    return bool(row and row[0] is not None)


def now() -> datetime:
    """DateTime 컬럼에 넣을 tz-aware 현재시각(UTC). epoch-ms 정수 대체."""
    return datetime.now(timezone.utc)
