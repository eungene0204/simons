from __future__ import annotations

import hashlib
import json
from pathlib import Path


_BASE_DIR = Path(__file__).resolve().parent.parent
_UNIVERSE_FILES = (
    _BASE_DIR / "data" / "korea-stocks.json",
    _BASE_DIR / "data" / "kospi200-cache.json",
)


def universe_cache_stamp() -> str:
    parts: list[str] = []
    for path in _UNIVERSE_FILES:
        if path.exists():
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
        else:
            parts.append(f"{path.name}:missing")
    return "|".join(parts)


def nl_cache_key(prompt: str, backend: str, model: str | None, previous_parsed: dict | None) -> str:
    payload = {
        "prompt": prompt.strip(),
        "backend": backend,
        "model": model or "",
        "previous_parsed": previous_parsed or {},
        "universe_stamp": universe_cache_stamp(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
