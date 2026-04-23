"""
Article normalization layer.

Converts RawArticle (provider-specific) → NormalizedArticle (canonical schema).
Handles:
- Title / body cleanup
- Timestamp UTC normalization
- Body hash computation for dedup
- cuid2 ID generation
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

import uuid

from news.schemas import RawArticle, NormalizedArticle
from news.storage import compute_body_hash


def _clean_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    # Strip HTML tags (providers may include markup in title/body)
    text = re.sub(r"<[^>]+>", "", text)
    # Normalize unicode (NFC)
    text = unicodedata.normalize("NFC", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove zero-width chars
    text = re.sub(r"[​‌‍﻿]", "", text)
    return text or None


def _truncate(text: Optional[str], max_len: int) -> Optional[str]:
    if text and len(text) > max_len:
        return text[:max_len]
    return text


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize(raw: RawArticle) -> NormalizedArticle:
    """
    Convert a RawArticle from any provider to a NormalizedArticle.
    The resulting object is ready for dedup + storage.
    """
    title = _clean_text(raw.title) or "(제목 없음)"
    body = _clean_text(raw.body)
    summary = _truncate(body, 500) if body else None

    body_hash = compute_body_hash(body) if body else compute_body_hash(title)
    published_at = _to_utc(raw.published_at)
    crawled_at = datetime.now(timezone.utc)

    return NormalizedArticle(
        id=uuid.uuid4().hex,
        title=title,
        summary=summary,
        url=raw.url.strip(),
        source=raw.source,
        author=_clean_text(raw.author),
        published_at=published_at,
        crawled_at=crawled_at,
        category=raw.category,
        language="ko",
        body_hash=body_hash,
        canonical_id=None,
        is_canonical=True,
    )
