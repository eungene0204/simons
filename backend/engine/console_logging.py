"""dev/운영 콘솔 상시 출력 로거 — 관찰용 INFO 로그가 버려지지 않게 하는 헬퍼.

앱에는 logging.basicConfig가 없어 모듈 로거의 INFO가 파이썬 최후수단 핸들러
(WARNING 이상)에서 전부 버려진다 — KG 조회 로그가 콘솔에 안 보이던 원인
(2026-07-27 제보). [NL-PARSE]·[LLM-INTERPRETER]가 print를 쓰는 것과 같은 이유로
전용 StreamHandler를 달되, propagate=False로 스크립트의 basicConfig 등 상위
핸들러와의 중복 출력을 막는다.
"""
from __future__ import annotations

import logging


def console_logger(name: str, tag: str) -> logging.Logger:
    """이름표(tag) 달린 콘솔 상시 출력 로거. 이미 핸들러가 있으면 그대로 둔다."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(f"[{tag}] %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
