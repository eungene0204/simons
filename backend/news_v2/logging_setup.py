"""
Structured logging for news_v2.

Uses structlog if available, otherwise falls back to stdlib logging with a
key=value formatter. Either way callers do `log = get_logger(__name__)` and
get the same API: `log.info("event", symbol="005930", tier=1)`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

try:
    import structlog

    _HAS_STRUCTLOG = True
except ImportError:  # pragma: no cover
    _HAS_STRUCTLOG = False


_configured = False


def _kv_formatter(record: logging.LogRecord) -> str:
    base = f"{record.levelname} {record.name} {record.getMessage()}"
    extras = getattr(record, "_extras", None)
    if extras:
        kv = " ".join(f"{k}={v}" for k, v in extras.items())
        return f"{base} {kv}"
    return base


class _StdlibAdapter(logging.LoggerAdapter):
    def process(self, msg: Any, kwargs: dict) -> tuple[Any, dict]:
        extras = kwargs.pop("extra", None) or {}
        merged = {**(self.extra or {}), **kwargs}
        kwargs = {"extra": {"_extras": {**extras, **merged}}}
        return msg, kwargs

    def bind(self, **kwargs: Any) -> "_StdlibAdapter":
        return _StdlibAdapter(self.logger, {**(self.extra or {}), **kwargs})


def configure() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    if _HAS_STRUCTLOG:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
            cache_logger_on_first_use=True,
        )
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.format = _kv_formatter  # type: ignore[assignment]
        root = logging.getLogger()
        if not root.handlers:
            root.addHandler(handler)
        root.setLevel(logging.INFO)


def get_logger(name: str) -> Any:
    configure()
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return _StdlibAdapter(logging.getLogger(name), {})
