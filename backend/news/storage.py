"""
News storage layer — SQLite CRUD operations.

Uses direct sqlite3 connections (same pattern as virtual_trader.py / research_routes.py)
so we stay independent of the Prisma client while sharing the same dev.db file.
All write operations use INSERT OR IGNORE or INSERT OR REPLACE to be idempotent.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from news.schemas import (
    NormalizedArticle,
    ArticleSymbolMap,
    ExtractedEvent,
    ImpactEstimate,
    NewsSignalRecord,
    IngestionStats,
    NewsItemResponse,
)


def _db_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("file:"):
        rel = db_url.replace("file:", "", 1)
        candidate = os.path.join(project_root, "prisma", rel) if rel.startswith("./") else os.path.join(project_root, "prisma", rel)
        if os.path.exists(candidate):
            return candidate
        alt = os.path.join(project_root, rel.lstrip("./"))
        if os.path.exists(alt):
            return alt
    return os.path.join(project_root, "prisma", "prisma", "dev.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.isoformat()


def _iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# ─── Article CRUD ──────────────────────────────────────────────────────────────

def upsert_article(article: NormalizedArticle) -> bool:
    """Insert or skip if URL already exists. Returns True if newly inserted."""
    conn = _connect()
    try:
        now = _now_iso()
        result = conn.execute(
            """
            INSERT OR IGNORE INTO NewsArticle
              (id, title, summary, url, source, author, publishedAt, crawledAt,
               category, language, bodyHash, canonicalId, isCanonical, createdAt, updatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                article.id,
                article.title,
                article.summary,
                article.url,
                article.source,
                article.author,
                _dt_to_iso(article.published_at),
                _dt_to_iso(article.crawled_at),
                article.category,
                article.language,
                article.body_hash,
                article.canonical_id,
                1 if article.is_canonical else 0,
                now,
                now,
            ),
        )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def upsert_raw_article(
    article_id: Optional[str],
    provider: str,
    external_id: Optional[str],
    title: str,
    body: Optional[str],
    url: str,
    source: str,
    author: Optional[str],
    published_at: datetime,
    category: Optional[str],
    raw_json: Dict[str, Any],
) -> str:
    """Insert raw article record. Returns the generated id."""
    import uuid
    raw_id = uuid.uuid4().hex
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO NewsArticleRaw
              (id, articleId, provider, externalId, title, body, url, source, author,
               publishedAt, category, rawJson, crawledAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                raw_id,
                article_id,
                provider,
                external_id,
                title,
                body,
                url,
                source,
                author,
                _dt_to_iso(published_at),
                category,
                json.dumps(raw_json, ensure_ascii=False),
                _now_iso(),
            ),
        )
        conn.commit()
        return raw_id
    finally:
        conn.close()


def url_exists(url: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM NewsArticle WHERE url = ? LIMIT 1", (url,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_article_by_id(article_id: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM NewsArticle WHERE id = ? LIMIT 1", (article_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_recent_article_titles(window_hours: int = 24, limit: int = 500) -> List[Dict[str, Any]]:
    """Used by dedup to compare incoming articles against recent ones."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, title, url, bodyHash, publishedAt
            FROM NewsArticle
            WHERE publishedAt >= datetime('now', ?)
            ORDER BY publishedAt DESC
            LIMIT ?
            """,
            (f"-{window_hours} hours", limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_as_duplicate(article_id: str, canonical_id: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE NewsArticle SET isCanonical = 0, canonicalId = ?, updatedAt = ? WHERE id = ?",
            (canonical_id, _now_iso(), article_id),
        )
        conn.commit()
    finally:
        conn.close()


# ─── Symbol mapping CRUD ──────────────────────────────────────────────────────

def upsert_symbol_maps(maps: List[ArticleSymbolMap]) -> None:
    if not maps:
        return
    conn = _connect()
    try:
        import uuid
        article_ids = {m.article_id for m in maps}
        for article_id in article_ids:
            conn.execute("DELETE FROM NewsArticleSymbol WHERE articleId = ?", (article_id,))
        for m in maps:
            conn.execute(
                """
                INSERT INTO NewsArticleSymbol
                  (id, articleId, symbol, companyName, scope, sector, relevance, createdAt)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    uuid.uuid4().hex,
                    m.article_id,
                    m.symbol,
                    m.company_name,
                    m.scope,
                    m.sector,
                    m.relevance,
                    _now_iso(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_symbols_for_article(article_id: str) -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM NewsArticleSymbol WHERE articleId = ?", (article_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── Event CRUD ───────────────────────────────────────────────────────────────

def upsert_event(event: ExtractedEvent) -> None:
    conn = _connect()
    try:
        import uuid
        conn.execute(
            """
            INSERT OR REPLACE INTO NewsEvent
              (id, articleId, eventType, sentiment, severity, surprise, credibility,
               novelty, relevance, summary, riskFlags, affectedEntities, expectedHorizon,
               modelVersion, createdAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                uuid.uuid4().hex,
                event.article_id,
                event.event_type,
                event.sentiment,
                event.severity,
                event.surprise,
                event.credibility,
                event.novelty,
                event.relevance,
                event.summary,
                json.dumps(event.risk_flags, ensure_ascii=False),
                json.dumps(event.affected_entities, ensure_ascii=False),
                event.expected_horizon,
                event.model_version,
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_event_for_article(article_id: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM NewsEvent WHERE articleId = ? LIMIT 1", (article_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ─── Impact CRUD ──────────────────────────────────────────────────────────────

def upsert_impact(impact: ImpactEstimate) -> None:
    conn = _connect()
    try:
        import uuid
        conn.execute(
            """
            INSERT OR REPLACE INTO NewsImpact
              (id, articleId, symbol, impactDirection, impactScore, confidenceScore,
               expectedHorizon, expectedAlpha1d, expectedAlpha5d, volatilityJumpRisk,
               riskAlertLevel, modelVersion, createdAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                uuid.uuid4().hex,
                impact.article_id,
                impact.symbol,
                impact.impact_direction,
                impact.impact_score,
                impact.confidence_score,
                impact.expected_horizon,
                impact.expected_alpha_1d,
                impact.expected_alpha_5d,
                impact.volatility_jump_risk,
                impact.risk_alert_level,
                impact.model_version,
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_impact_for_article(article_id: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM NewsImpact WHERE articleId = ? LIMIT 1", (article_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ─── Signal CRUD ──────────────────────────────────────────────────────────────

def upsert_signals(signals: List[NewsSignalRecord]) -> None:
    if not signals:
        return
    conn = _connect()
    try:
        import uuid
        for s in signals:
            conn.execute(
                """
                INSERT OR IGNORE INTO NewsSignal
                  (id, articleId, symbol, signalType, value, direction, confidence,
                   validFrom, validUntil, metadata, modelVersion, createdAt)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    uuid.uuid4().hex,
                    s.article_id,
                    s.symbol,
                    s.signal_type,
                    s.value,
                    s.direction,
                    s.confidence,
                    _dt_to_iso(s.valid_from),
                    _dt_to_iso(s.valid_until),
                    json.dumps(s.metadata, ensure_ascii=False),
                    s.model_version,
                    _now_iso(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_signals_for_symbol(
    symbol: str,
    as_of: Optional[datetime] = None,
    signal_type: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Returns signals for a symbol with strict look-ahead enforcement:
    only signals where validFrom <= as_of are returned.
    """
    conn = _connect()
    try:
        cutoff = _dt_to_iso(as_of) if as_of else _now_iso()
        params: List[Any] = [symbol, cutoff]
        extra = ""
        if signal_type:
            extra = " AND signalType = ?"
            params.append(signal_type)
        rows = conn.execute(
            f"""
            SELECT ns.*, na.publishedAt, na.title, na.url, na.source
            FROM NewsSignal ns
            JOIN NewsArticle na ON na.id = ns.articleId
            WHERE ns.symbol = ?
              AND ns.validFrom <= ?
              {extra}
            ORDER BY ns.validFrom DESC
            LIMIT ?
            """,
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── Composite article query ───────────────────────────────────────────────────

def get_articles_for_symbol(
    symbol: str,
    as_of: Optional[datetime] = None,
    limit: int = 20,
    page: int = 1,
) -> List[Dict[str, Any]]:
    """Articles mapped to a symbol with event + impact data, enforcing look-ahead."""
    conn = _connect()
    try:
        cutoff = _dt_to_iso(as_of) if as_of else _now_iso()
        offset = (page - 1) * limit
        rows = conn.execute(
            """
            SELECT na.*, ne.eventType, ne.sentiment, ne.severity, ne.credibility,
                   ne.riskFlags, ne.summary as eventSummary,
                   ni.impactDirection, ni.impactScore, ni.confidenceScore,
                   ni.riskAlertLevel, ni.expectedAlpha1d,
                   nas.scope, nas.sector, nas.relevance
            FROM NewsArticle na
            JOIN NewsArticleSymbol nas ON nas.articleId = na.id
            LEFT JOIN NewsEvent ne ON ne.articleId = na.id
            LEFT JOIN NewsImpact ni ON ni.articleId = na.id
            WHERE nas.symbol = ?
              AND na.publishedAt <= ?
              AND na.isCanonical = 1
            ORDER BY na.publishedAt DESC
            LIMIT ? OFFSET ?
            """,
            (symbol, cutoff, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_top_articles(
    as_of: Optional[datetime] = None,
    limit: int = 20,
    page: int = 1,
    scope: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Recent canonical articles with event + impact joined, look-ahead safe."""
    conn = _connect()
    try:
        cutoff = _dt_to_iso(as_of) if as_of else _now_iso()
        offset = (page - 1) * limit
        scope_clause = "AND nas.scope = ?" if scope else ""
        params: List[Any] = [cutoff]
        if scope:
            params.append(scope)
        params += [limit, offset]
        rows = conn.execute(
            f"""
            SELECT na.*, ne.eventType, ne.sentiment, ne.severity, ne.credibility,
                   ne.riskFlags, ne.summary as eventSummary,
                   ni.impactDirection, ni.impactScore, ni.confidenceScore,
                   ni.riskAlertLevel, ni.expectedAlpha1d,
                   GROUP_CONCAT(nas.symbol, ',') as symbols,
                   nas.scope, nas.sector
            FROM NewsArticle na
            LEFT JOIN NewsArticleSymbol nas ON nas.articleId = na.id
            LEFT JOIN NewsEvent ne ON ne.articleId = na.id
            LEFT JOIN NewsImpact ni ON ni.articleId = na.id
            WHERE na.publishedAt <= ?
              AND na.isCanonical = 1
              {scope_clause}
            GROUP BY na.id
            ORDER BY na.publishedAt DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_articles_for_symbol(symbol: str, as_of: Optional[datetime] = None) -> int:
    conn = _connect()
    try:
        cutoff = _dt_to_iso(as_of) if as_of else _now_iso()
        row = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM NewsArticle na
            JOIN NewsArticleSymbol nas ON nas.articleId = na.id
            WHERE nas.symbol = ? AND na.publishedAt <= ? AND na.isCanonical = 1
            """,
            (symbol, cutoff),
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


# ─── Ingestion log CRUD ───────────────────────────────────────────────────────

def start_ingestion_log(provider: str) -> str:
    import uuid
    log_id = uuid.uuid4().hex
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO NewsIngestionLog
              (id, provider, startedAt, status, createdAt)
            VALUES (?,?,?,?,?)
            """,
            (log_id, provider, _now_iso(), "running", _now_iso()),
        )
        conn.commit()
        return log_id
    finally:
        conn.close()


def finish_ingestion_log(
    log_id: str,
    status: str,
    fetched: int,
    deduplicated: int,
    inserted: int,
    error: Optional[str] = None,
) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE NewsIngestionLog
            SET finishedAt = ?, status = ?, fetched = ?, deduplicated = ?, inserted = ?, error = ?
            WHERE id = ?
            """,
            (_now_iso(), status, fetched, deduplicated, inserted, error, log_id),
        )
        conn.commit()
    finally:
        conn.close()


# ─── Stock name lookup (used by entity_mapper) ────────────────────────────────

def get_stock_by_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT symbol, name, market FROM Stock WHERE symbol = ?", (symbol,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_stocks() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT symbol, name, market FROM Stock WHERE name IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── Body hash ────────────────────────────────────────────────────────────────

def compute_body_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
