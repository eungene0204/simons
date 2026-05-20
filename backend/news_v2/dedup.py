"""
Title normalization + dedup hashing for news_v2.

Two layers, in order of cost:
  1. normalize_title(raw) → strip noise, lowercase, collapse whitespace.
  2. SHA256(normalized_title) → stable 64-char hex hash used as dedup key.

Embedding-based dedup is a separate, slower path used in maintenance jobs
(deduplicate_news task) — not on the hot collect path.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Source/agency prefixes Korean outlets put in titles, e.g. "[속보] ..." or "(서울=뉴스1) ..."
_BRACKET_PREFIX = re.compile(r"^\s*[\[\(].{1,30}?[\]\)]\s*")
_AGENCY_PREFIX = re.compile(
    r"^\s*(?:속보|단독|특징주|특보|종합|업데이트|상보|시황|화제|이슈|기획|인터뷰|르포|르뽀|영상|사진)[\s:|·\-]+",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")
_NON_TEXT = re.compile(r"[^\w\s가-힣]+")


def normalize_title(raw: str) -> str:
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", raw).strip()
    prev = None
    while text != prev:
        prev = text
        text = _BRACKET_PREFIX.sub("", text)
        text = _AGENCY_PREFIX.sub("", text)
    text = _NON_TEXT.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip().lower()
    return text


def title_hash(raw: str) -> str:
    return hashlib.sha256(normalize_title(raw).encode("utf-8")).hexdigest()


def is_duplicate(title_a: str, title_b: str) -> bool:
    """Fast string-level duplicate check."""
    return title_hash(title_a) == title_hash(title_b)


# ─── embedding-based dedup (slow, optional) ────────────────────────────────────

def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def near_duplicate(
    embedding_a: list[float], embedding_b: list[float], threshold: float = 0.92
) -> bool:
    return cosine(embedding_a, embedding_b) >= threshold
