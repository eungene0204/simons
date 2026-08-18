"""요청 취소 — 클라이언트가 연결을 끊으면('대화 종료') 진행 중인 서버 작업을 멈춘다.

전략 분석(파싱·빌더 스텝)은 SSE 요청 하나가 워커 스레드 하나를 돌리고, 그 스레드가
LLM(Ollama) HTTP 호출을 여러 번 한다. 클라이언트가 끊겨도 스레드는 그 사실을 모르므로
LLM 생성이 끝까지 돌고, 다음 요청은 그 뒤에 줄을 선다. 이 모듈은 요청 단위 취소 토큰을
워커 스레드에 묶어 두 가지를 한다.

  1. 협조적 중단 — LLM 호출 직전마다 토큰을 확인해, 취소됐으면 OperationCancelled를 던진다.
  2. 진행 중 호출 차단 — 토큰이 묶인 스레드가 여는 HTTP 소켓을 추적해 두고, 취소 시 닫는다.
     소켓이 닫히면 Ollama도 요청 컨텍스트 취소로 생성을 중단한다(GPU 반환).

OperationCancelled는 BaseException이다 — 파이프라인 곳곳의 `except Exception` 폴백
("장애가 파스를 깨면 안 된다")이 취소를 삼키고 저품질 결과를 만들어 캐시에 남기는 일이
없도록, 취소는 어떤 폴백도 거치지 않고 워커 스레드 최상단까지 올라간다.
"""

from __future__ import annotations

import contextlib
import contextvars
import http.client
import socket
import threading
import urllib.error
import urllib.request
from typing import Iterator, Optional


class OperationCancelled(BaseException):
    """요청이 취소돼 작업을 중단했다(클라이언트 연결 종료)."""


class CancelToken:
    """요청 하나의 취소 상태. 스레드 안전 — cancel()은 다른 스레드(이벤트 루프)에서 부른다."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._sockets: list[socket.socket] = []

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        """취소를 표시하고, 추적 중인 소켓을 닫아 진행 중인 HTTP 호출을 끊는다."""
        self._event.set()
        with self._lock:
            sockets, self._sockets = self._sockets, []
        for sock in sockets:
            _close_socket(sock)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise OperationCancelled()

    def track_socket(self, sock: socket.socket) -> None:
        """이 요청이 연 소켓을 등록한다. 이미 취소된 뒤면 즉시 닫는다."""
        with self._lock:
            if not self.cancelled:
                self._sockets.append(sock)
                return
        _close_socket(sock)


def _close_socket(sock: socket.socket) -> None:
    # 다른 스레드가 recv에 막혀 있어도 shutdown이 깨운다. 이미 닫힌 소켓이면 무시한다.
    with contextlib.suppress(OSError):
        sock.shutdown(socket.SHUT_RDWR)
    with contextlib.suppress(OSError):
        sock.close()


_current: contextvars.ContextVar[Optional[CancelToken]] = contextvars.ContextVar(
    "cancel_token", default=None
)


@contextlib.contextmanager
def bind(token: CancelToken) -> Iterator[CancelToken]:
    """현재 실행 컨텍스트(워커 스레드)에 토큰을 묶는다. 스레드를 새로 만들면 상속되지 않으므로
    작업 스레드의 진입 함수 안에서 연다."""
    reset = _current.set(token)
    try:
        yield token
    finally:
        _current.reset(reset)


def current() -> Optional[CancelToken]:
    return _current.get()


def is_cancelled() -> bool:
    token = _current.get()
    return token is not None and token.cancelled


def raise_if_cancelled() -> None:
    token = _current.get()
    if token is not None:
        token.raise_if_cancelled()


@contextlib.contextmanager
def cancellable_io() -> Iterator[None]:
    """소켓 I/O 구간을 감싼다 — 취소로 소켓이 닫혀서 난 I/O 예외는 OperationCancelled로 바꾼다.

    닫힌 소켓의 read는 ConnectionResetError·IncompleteRead·URLError 등으로 나타나는데, 이를
    그대로 두면 호출부가 'LLM 장애'로 오판해 폴백·재시도·오류 로그를 남긴다."""
    try:
        yield
    except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
        token = _current.get()
        if token is not None and token.cancelled:
            raise OperationCancelled() from exc
        raise


# ─── urllib 소켓 추적 ──────────────────────────────────────────────────────────
# urllib.request.urlopen이 여는 연결을 토큰에 등록한다. 토큰이 묶이지 않은 컨텍스트에서는
# 등록만 건너뛰므로(no-op) 다른 urlopen 호출(KIS·검색 등)의 동작은 그대로다.


def _track(sock: Optional[socket.socket]) -> None:
    token = _current.get()
    if token is not None and sock is not None:
        token.track_socket(sock)


class _TrackedHTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:  # noqa: D401 — 표준 시그니처
        super().connect()
        _track(self.sock)


class _TrackedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self) -> None:  # noqa: D401 — 표준 시그니처
        super().connect()
        _track(self.sock)


class _TrackedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_TrackedHTTPConnection, req)


class _TrackedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_TrackedHTTPSConnection, req, context=self._context)


_install_lock = threading.Lock()
_installed = False


def install_socket_tracking() -> None:
    """urllib 전역 opener를 소켓 추적판으로 바꾼다(멱등). 서버 기동 시 한 번 부른다."""
    global _installed
    with _install_lock:
        if _installed:
            return
        urllib.request.install_opener(
            urllib.request.build_opener(_TrackedHTTPHandler, _TrackedHTTPSHandler)
        )
        _installed = True
