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
from engine.watchdog import backtest_timeout_s, walk_forward_timeout_s


class RemoteBacktestError(RuntimeError):
    """원격 백테스트 워커 호출 실패(연결·비200). 로컬 폴백 없이 그대로 드러낸다."""


def remote_url() -> str | None:
    """원격 실행이 활성일 때만 워커 URL, 아니면 None(=로컬 실행)."""
    if os.environ.get("BACKTEST_EXECUTOR", "local").strip().lower() != "modal":
        return None
    return (os.environ.get("BACKTEST_REMOTE_URL") or "").strip() or None


def job_url(fn_slug: str) -> str | None:
    """장시간 잡 엔드포인트 URL — 단일 백테스트 URL에서 함수 슬러그만 치환해 파생.

    Modal 웹 엔드포인트 URL은 `<계정>--<앱>-<함수명>.modal.run` 형태라
    (modal_backtest.py의 함수 이름과 1:1), 별도 env 없이 파생한다.
    """
    base = remote_url()
    if not base:
        return None
    if "run-backtest" not in base:
        raise RemoteBacktestError(
            f"BACKTEST_REMOTE_URL에서 잡 URL을 파생할 수 없음(run-backtest 미포함): {base}"
        )
    return base.replace("run-backtest", fn_slug)


def _post_json(url: str, payload: Dict[str, Any], *, read_timeout_s: float, what: str) -> Dict[str, Any]:
    timeout = httpx.Timeout(connect=30.0, read=read_timeout_s, write=120.0, pool=30.0)
    try:
        resp = httpx.post(url, json=payload, headers=modal_auth_headers(), timeout=timeout)
    except httpx.HTTPError as exc:
        raise RemoteBacktestError(f"원격 {what} 워커 연결 실패: {exc}") from exc
    if resp.status_code != 200:
        raise RemoteBacktestError(f"원격 {what} 워커 HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def run(engine, req_dict: Dict[str, Any]) -> Dict[str, Any]:
    url = remote_url()
    if not url:
        return engine.run_backtest(req_dict)
    # read는 워치독 한도 + 콜드스타트 여유. 워치독(run_with_timeout)이 최종 상한이다.
    return _post_json(url, req_dict, read_timeout_s=backtest_timeout_s() + 45.0, what="백테스트")


def run_optimization(engine, *, base_request, user_prompt, ranges, target_metric, n_trials) -> Dict[str, Any]:
    """전략 최적화 디스패치 — 원격이면 워커 run_optimize, 아니면 인프로세스."""
    url = job_url("run-optimize")
    if not url:
        from ai.local_optimization_agent import LocalOptimizationAgent

        return LocalOptimizationAgent(engine).run_optimization_loop(
            base_request=base_request, user_prompt=user_prompt, ranges=ranges,
            target_metric=target_metric, n_trials=n_trials,
        )
    payload = {"base_request": base_request, "user_prompt": user_prompt, "ranges": ranges,
               "target_metric": target_metric, "n_trials": n_trials}
    return _post_json(url, payload, read_timeout_s=walk_forward_timeout_s() + 120.0, what="최적화")


def run_walk_forward(engine, wf_payload: Dict[str, Any]) -> Dict[str, Any]:
    """워크포워드(동기) 디스패치. wf_payload는 워커 계약(base_request + analyze 인자)."""
    url = job_url("run-walk-forward")
    if not url:
        from engine.walk_forward import WalkForwardAnalyzer

        return WalkForwardAnalyzer(engine).analyze(**wf_payload)
    return _post_json(url, wf_payload, read_timeout_s=walk_forward_timeout_s() + 120.0, what="워크포워드")


def iter_walk_forward_stream(wf_payload: Dict[str, Any]):
    """원격 워크포워드 SSE 바이트 스트림 제너레이터(원격일 때만 호출할 것).

    워커의 이벤트 형식이 인프로세스 스트림과 동일하므로 그대로 통과시킨다.
    호출측(라우트)이 제너레이터를 닫으면 응답이 닫혀 워커의 협조적 취소가 발동한다.
    """
    import json as _json

    def _error_event(msg: str) -> bytes:
        return (f"data: {_json.dumps({'type': 'error', 'message': msg}, ensure_ascii=False)}\n\n"
                "data: [DONE]\n\n").encode()

    url = job_url("run-walk-forward-stream")
    assert url, "iter_walk_forward_stream은 원격 모드에서만 호출한다"
    timeout = httpx.Timeout(connect=30.0, read=walk_forward_timeout_s() + 120.0, write=120.0, pool=30.0)
    try:
        with httpx.stream("POST", url, json=wf_payload, headers=modal_auth_headers(), timeout=timeout) as resp:
            if resp.status_code != 200:
                resp.read()
                yield _error_event(f"원격 워크포워드 워커 HTTP {resp.status_code}")
                return
            yield from resp.iter_raw()
    except httpx.HTTPError as exc:
        # 스트림은 이미 200으로 시작됐을 수 있으므로 예외 대신 SSE error 이벤트로 전달
        yield _error_event(f"원격 워크포워드 워커 연결 실패: {exc}")
