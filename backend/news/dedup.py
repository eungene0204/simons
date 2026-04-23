"""
Deduplication layer.

Identifies near-duplicate articles using a multi-signal approach:
1. Exact URL match (caught by storage UNIQUE constraint)
2. Body hash match (same content, different URL)
3. Normalized title similarity using Jaccard on character n-grams
4. Publish time proximity (within 2 hours)

Only articles passing all checks are considered new.
The dedup window looks back 24 hours to catch delayed re-publishes.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from news.schemas import NormalizedArticle
from news.storage import get_recent_article_titles


# Jaccard similarity threshold above which two articles are considered duplicates
_TITLE_SIM_THRESHOLD = 0.65

# Time window within which title similarity is checked
_TIME_WINDOW_HOURS = 24

# Minimum title length to run similarity (very short titles are excluded)
_MIN_TITLE_LEN = 8


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/spaces for comparison."""
    title = unicodedata.normalize("NFC", title.lower())
    title = re.sub(r"[^\w가-힣a-z0-9]", "", title)
    return title


def _char_ngrams(text: str, n: int = 3) -> set:
    """Character n-gram set for Jaccard similarity."""
    return {text[i : i + n] for i in range(max(0, len(text) - n + 1))}


def _jaccard(a: str, b: str, n: int = 3) -> float:
    sa = _char_ngrams(a, n)
    sb = _char_ngrams(b, n)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union


def is_duplicate(
    article: NormalizedArticle,
    recent: List[dict],
) -> Tuple[bool, Optional[str]]:
    """
    Check if `article` is a near-duplicate of any article in `recent`.

    Returns (is_dup, canonical_id).
    `recent` is the output of storage.get_recent_article_titles().
    """
    if not recent:
        return False, None

    article_time = article.published_at
    if article_time.tzinfo is None:
        article_time = article_time.replace(tzinfo=timezone.utc)

    # Body hash check runs before title-length guard — it's a definitive match.
    if article.body_hash:
        for rec in recent:
            if rec.get("bodyHash") == article.body_hash:
                return True, rec["id"]

    norm_title = _normalize_title(article.title)
    if len(norm_title) < _MIN_TITLE_LEN:
        return False, None

    for rec in recent:

        # Time proximity check
        rec_time_str = rec.get("publishedAt", "")
        try:
            rec_time = datetime.fromisoformat(rec_time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        time_diff = abs((article_time - rec_time).total_seconds())
        if time_diff > _TIME_WINDOW_HOURS * 3600:
            continue

        # Title similarity check (only within time window)
        norm_rec_title = _normalize_title(rec.get("title", ""))
        sim = _jaccard(norm_title, norm_rec_title)
        if sim >= _TITLE_SIM_THRESHOLD:
            return True, rec["id"]

    return False, None


def filter_duplicates(
    articles: List[NormalizedArticle],
    existing_recent: Optional[List[dict]] = None,
) -> Tuple[List[NormalizedArticle], int]:
    """
    Filter a batch of incoming articles, removing duplicates.

    Also deduplicates within the batch itself (e.g., same story from two
    providers fetched in the same run).

    Returns (unique_articles, num_duplicates).
    """
    if existing_recent is None:
        existing_recent = get_recent_article_titles(_TIME_WINDOW_HOURS)

    unique: List[NormalizedArticle] = []
    # Accumulate accepted articles to catch intra-batch duplicates
    accepted_as_recent: List[dict] = list(existing_recent)
    dup_count = 0

    for article in articles:
        is_dup, canonical_id = is_duplicate(article, accepted_as_recent)
        if is_dup:
            dup_count += 1
        else:
            unique.append(article)
            # Add to accepted pool for intra-batch dedup
            accepted_as_recent.append({
                "id": article.id,
                "title": article.title,
                "url": article.url,
                "bodyHash": article.body_hash,
                "publishedAt": article.published_at.isoformat(),
            })

    return unique, dup_count
