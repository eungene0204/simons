"""백테스트 실행 디스패처 — 인프로세스(기본) vs Modal 원격 CPU 워커.

BACKTEST_EXECUTOR=modal 이고 BACKTEST_REMOTE_URL 이 설정된 경우에만 원격 실행한다.
그 외에는 종전 그대로 로컬 엔진을 부른다(로컬 dev·테스트는 env 미설정 → 무변경).

원격 실패는 로컬로 폴백하지 않는다 — CPU 아키텍처 간 부동소수점 ULP 차이로
실행 장소가 섞이면 같은 전략이 실행마다 미세하게 다른 결과를 갖게 되기 때문
(정본 레인은 하나여야 한다). 실패는 에러로 드러내 기존 에러 경로(500/504)를 탄다.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import httpx

# Modal proxy-auth 헤더(MODAL_KEY/MODAL_SECRET) — LLM 레인과 같은 토큰을 쓴다.
from llm_backend import ollama_auth_headers as modal_auth_headers
from engine.watchdog import backtest_timeout_s


class RemoteBacktestError(RuntimeError):
    """원격 백테스트 워커 호출 실패(연결·비200). 로컬 폴백 없이 그대로 드러낸다."""


def remote_url() -> str | None:
    """원격 실행이 활성일 때만 워커 URL, 아니면 None(=로컬 실행)."""
    if os.environ.get("BACKTEST_EXECUTOR", "local").strip().lower() != "modal":
        return None
    return (os.environ.get("BACKTEST_REMOTE_URL") or "").strip() or None


def run(engine, req_dict: Dict[str, Any]) -> Dict[str, Any]:
    url = remote_url()
    if not url:
        return engine.run_backtest(req_dict)

    # read는 워치독 한도 + 콜드스타트 여유. 워치독(run_with_timeout)이 최종 상한이다.
    timeout = httpx.Timeout(connect=30.0, read=backtest_timeout_s() + 45.0, write=120.0, pool=30.0)
    try:
        resp = httpx.post(url, json=req_dict, headers=modal_auth_headers(), timeout=timeout)
    except httpx.HTTPError as exc:
        raise RemoteBacktestError(f"원격 백테스트 워커 연결 실패: {exc}") from exc
    if resp.status_code != 200:
        raise RemoteBacktestError(
            f"원격 백테스트 워커 HTTP {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()
