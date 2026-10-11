"""내부 토큰 — 관리자·내부·운영 변경 엔드포인트의 이중 잠금(NFR-SEC-012).

백엔드는 외부에 노출되지 않는다(Caddy는 web만 프록시)는 전제로 인증 없이 동작한다. 그런데
2026-10-11 Next 라우트가 디코드된 '..'를 백엔드 경로에 끼워, 비로그인 요청이 백엔드의 아무
경로에 닿는 사고가 실측됐다(NFR-SEC-011로 Next 쪽은 막았다). 같은 실수가 다시 나와도 위험한
엔드포인트에는 닿지 않도록, 아래 경로는 정상 호출자(Next 서버·스케줄러)만 아는 토큰을 요구한다.

- 토큰: 환경변수 INTERNAL_API_TOKEN. 같은 .env를 읽는 backend·web·scheduler가 공유한다.
- 헤더: X-Internal-Token. Next는 fetchBackend가 자동으로 싣고, 스크립트는 직접 싣는다.
- 미설정이면 보호 경로를 전부 거부한다(fail-closed) — 설정 누락이 잠금 해제가 되면 안 된다.
- 거부 응답은 404 — 엔드포인트의 존재를 드러내지 않는다.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
from typing import Optional

logger = logging.getLogger("internal_auth")

HEADER = "x-internal-token"
ENV = "INTERNAL_API_TOKEN"

_PREFIXES = ("/admin/", "/internal/")
# (메서드, 경로 패턴) — 운영 데이터를 바꾸는 엔드포인트. 사용자 기능(백테스트·파싱 등)은 넣지 않는다.
_RULES = (
    ("POST", re.compile(r"^/sync-stocks$")),
    # GET이지만 DART 공시로 Stock.listingStatus를 갱신하고 DART 일 한도를 쓴다.
    ("GET", re.compile(r"^/market/dart/notices$")),
    ("POST", re.compile(r"^/market/delist/[^/]+$")),
    ("DELETE", re.compile(r"^/market/delist/[^/]+$")),
    ("POST", re.compile(r"^/market/listing-status/sync$")),
    ("POST", re.compile(r"^/virtual-account/[^/]+/force-liquidate/[^/]+$")),
    ("POST", re.compile(r"^/ai/runtime/metrics/reset$")),
    ("POST", re.compile(r"^/v2/news/[^/]+/refresh$")),
)

_warned_unset = False


def is_protected(method: str, path: str) -> bool:
    """이 요청이 내부 토큰을 요구하는가. path는 ASGI가 디코드·정규화한 경로다."""
    if path.startswith(_PREFIXES):
        return True
    method = method.upper()
    return any(method == m and pattern.match(path) for m, pattern in _RULES)


def authorized(header_value: Optional[str]) -> bool:
    """헤더 토큰이 설정값과 같은가. 설정이 없으면 항상 거부한다."""
    global _warned_unset
    expected = os.environ.get(ENV, "").strip()
    if not expected:
        if not _warned_unset:
            logger.warning("%s 미설정 — 보호 경로를 전부 거부한다(fail-closed)", ENV)
            _warned_unset = True
        return False
    return hmac.compare_digest((header_value or "").strip(), expected)


async def middleware(request, call_next):
    """보호 경로에 토큰이 맞지 않으면 404. 판정은 메서드·경로 표기뿐이다."""
    from fastapi.responses import JSONResponse

    # 판정은 라우터가 엔드포인트를 고르는 경로(scope["path"])로 한다 — request.url.path는 URL을 다시
    # 쪼갠 값이라 디코드된 '?'에서 잘려, '/market/delist/%3Fx'가 판정을 비켜 갔다(2026-10-11 검토 실측).
    if is_protected(request.method, request.scope.get("path", "")) and not authorized(
        request.headers.get(HEADER)
    ):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return await call_next(request)
