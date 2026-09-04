"""Modal serverless CPU — 백테스트 원격 워커 엔드포인트.

하이브리드 배포의 세 번째 레인. 앱(Next/FastAPI)은 Vultr CPU 박스에 상시 떠 있고,
LLM은 modal_ollama.py(GPU)가, **백테스트 실행은 이 워커(CPU)**가 맡는다.
동시 요청이 오면 Modal이 요청 수만큼 컨테이너를 자동으로 늘리므로(오토스케일)
50건 동시 실행도 각자 전용 코어로 병렬 처리된다. 안 쓰면 scale-to-zero라 $0.

계약 (결과 동일성)
─────────────────
백테스트는 "실행 장소가 바뀌어도 답이 바뀌지 않는다"가 계약이다. 이를 위해:
  - 파이썬·수치 라이브러리 버전을 prod 백엔드와 **정확히 같은 값으로 핀**한다.
    2026-09-04부터 이 핀은 손으로 적지 않는다 — requirements-modal.txt가 앱 박스와
    같은 uv.lock에서 파생되므로 전이 의존(scipy·numba…)까지 자동으로 같은 값이다.
    (구조: pyproject.toml의 `modal` 그룹이 "무엇을", uv.lock이 "어떤 버전으로"를 정한다)
  - x86_64 리눅스로 prod와 같은 아키텍처다(로컬 ARM Mac과의 ULP 차이는
    project 이력상 이미 알려진 노이즈 — x86끼리는 동일해야 한다).
  - 전환 전 scripts/qa_backtest_modal_equivalence.py 로 prod↔Modal 전수 대조.

데이터
──────
엔진이 읽는 data/(ohlcv·ohlcv-us·fundamentals·메타 JSON)는 Volume
`simons-backtest-data`에 있다. 정본은 prod 박스이므로 **동기화는 박스에서**
scripts/sync_modal_backtest_data.sh 로 올린다(일일 데이터 갱신 후 재실행 필요).
AI 지표(ai_model/ai_drop_model)의 model/v3 가중치(~10MB)는 git 추적 파일이라
이미지에 직접 담는다.

배포
────
  .venv/bin/modal deploy modal_backtest.py     # → https URL 출력
  # 앱 박스 .env:
  #   BACKTEST_EXECUTOR=modal
  #   BACKTEST_REMOTE_URL=https://<org>--simons-backtest-run-backtest.modal.run
  #   (requires_proxy_auth=True — 기존 MODAL_KEY/MODAL_SECRET 헤더 재사용)
"""

from __future__ import annotations

import modal

# ── 설정 ──────────────────────────────────────────────────────────────────────
APP_ROOT = "/root/app"                    # backend/ 코드가 이 밑에 놓인다 →
DATA_PATH = f"{APP_ROOT}/data"            # 엔진의 base_dir/data 경로 해석과 일치
WORKER_CPU = 8.0                          # 컨테이너당 전용 코어 — 벤치상 1건 ≈ 10~20 코어·초
WORKER_MEMORY_MB = 16384                  # 전 시장 유니버스 백테스트 여유분
WORKER_TIMEOUT_S = 650                    # 백엔드 워치독(BACKTEST_TIMEOUT_S=600)보다 약간 크게
SCALEDOWN_WINDOW = 600                    # 마지막 요청 후 10분 warm 유지(연속 사용 콜드 방지)
MAX_CONTAINERS = 64                       # 폭주 시 비용 상한(50 동시 + 여유)

# 장시간 잡(최적화·워크포워드) — 백엔드 walk_forward_timeout_s(3600)보다 약간 크게.
JOB_TIMEOUT_S = 3700
JOB_MAX_CONTAINERS = 16                   # 잡은 드물고 무거움 — 폭주 상한을 낮게
WFA_CPU = 16.0                            # 창 병렬 4 × 창당 Phase1 풀 3 = 12프로세스 + 여유
WFA_MEMORY_MB = 24576                     # 창 워커마다 엔진·prep 캐시를 따로 가짐
# ⚠️ 컨테이너의 os.cpu_count()는 호스트 코어를 보므로(cgroup 비인지) 자동 산정이 과대해진다.
#    창 병렬·창당 풀 크기를 반드시 명시 고정한다 (아래 _pin_wfa_env).
WFA_ENV = {"WALK_FORWARD_WORKERS": "4", "BACKTEST_PHASE1_WORKERS": "3"}

# 워커 이미지가 설치하는 엔진 의존성 — 앱 박스와 같은 uv.lock에서 내보낸 파생물이다.
# 무엇이 들어갈지는 pyproject.toml의 [dependency-groups] modal 이 정하고, 어떤 버전으로
# 들어갈지는 uv.lock이 정한다. 둘 중 하나를 고치면 반드시 재생성하고 함께 커밋한다:
#     bash scripts/export_modal_requirements.sh
# (잊으면 backend/tests/test_modal_requirements_export.py 가 실패한다)
PINNED_REQUIREMENTS = "requirements-modal.txt"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .uv_pip_install(requirements=[PINNED_REQUIREMENTS])
    # torch는 CPU 휠로(기본 PyPI 휠은 CUDA 동봉 ~2.5GB) — ai_model/ai_drop_model 지표용.
    # 잠금의 리눅스 해석(2.12.0+cpu)과 같은 휠이다.
    .uv_pip_install("torch==2.12.0", index_url="https://download.pytorch.org/whl/cpu")
    .env(
        {
            # 데드락 가드 — prod compose와 동일(없으면 polars/OMP 스레드 경합으로 행).
            "POLARS_MAX_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "KMP_DUPLICATE_LIB_OK": "TRUE",
            # Phase1 프로세스 풀 크기 — os.cpu_count()는 호스트 코어를 보므로 명시 고정.
            "BACKTEST_PHASE1_WORKERS": "7",
        }
    )
    .add_local_dir("model/v3", f"{APP_ROOT}/model/v3")
    .add_local_dir(
        "backend",
        f"{APP_ROOT}/backend",
        ignore=["__pycache__", "*.pyc", "tests", ".pytest_cache"],
    )
)

app = modal.App("simons-backtest")

data_volume = modal.Volume.from_name("simons-backtest-data", create_if_missing=True)


def _get_engine():
    """엔진 lazy 싱글턴 — 컨테이너 수명 동안 재사용(웜 요청은 즉시 실행)."""
    import sys

    if f"{APP_ROOT}/backend" not in sys.path:
        sys.path.insert(0, f"{APP_ROOT}/backend")

    global _engine
    try:
        return _engine
    except NameError:
        from backtest_engine import BacktestEngine

        _engine = BacktestEngine()
        return _engine


def _jsonify(result):
    """numpy 스칼라가 섞여 있어도 순수 JSON으로 정규화해 반환한다
    (백엔드는 어차피 pydantic response_model로 한 번 더 검증한다)."""
    import json

    return json.loads(json.dumps(result, default=float))


def _pin_wfa_env() -> None:
    """WFA 컨테이너의 코어 분배 명시 고정 — os.cpu_count() 과대 산정 방지."""
    import os

    os.environ.update(WFA_ENV)


@app.function(
    image=image,
    cpu=WORKER_CPU,
    memory=WORKER_MEMORY_MB,
    volumes={DATA_PATH: data_volume},
    timeout=WORKER_TIMEOUT_S,
    scaledown_window=SCALEDOWN_WINDOW,
    min_containers=0,
    max_containers=MAX_CONTAINERS,
)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def run_backtest(request: dict) -> dict:
    """백테스트 요청(dict, BacktestRequest.model_dump()와 동일 형태) → 결과 dict.

    컨테이너당 요청 1개(기본값) — 각 백테스트가 코어를 독점하고,
    동시 요청은 Modal 오토스케일이 컨테이너를 늘려 처리한다.
    """
    return _jsonify(_get_engine().run_backtest(request))


@app.function(
    image=image,
    cpu=WORKER_CPU,
    memory=WORKER_MEMORY_MB,
    volumes={DATA_PATH: data_volume},
    timeout=JOB_TIMEOUT_S,
    scaledown_window=SCALEDOWN_WINDOW,
    min_containers=0,
    max_containers=JOB_MAX_CONTAINERS,
)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def run_optimize(request: dict) -> dict:
    """전략 최적화(optuna, seed=42라 결정적) — 백엔드 /optimize와 동일 계약.

    페이로드: {base_request, user_prompt, ranges, target_metric, n_trials}
    트라이얼이 순차라 8코어 + 이미지 기본 BACKTEST_PHASE1_WORKERS=7을 그대로 쓴다.
    """
    engine = _get_engine()
    from ai.local_optimization_agent import LocalOptimizationAgent

    agent = LocalOptimizationAgent(engine)
    # None은 "미지정"으로 취급해 기본값을 살린다(user_prompt는 필수 인자라 None도 전달).
    kwargs = {"base_request": request["base_request"],
              "user_prompt": request.get("user_prompt"),
              "ranges": request.get("ranges")}
    kwargs.update({k: request[k] for k in ("target_metric", "n_trials") if request.get(k) is not None})
    return _jsonify(agent.run_optimization_loop(**kwargs))


def _wfa_kwargs(request: dict) -> dict:
    """백엔드 WalkForwardRequest.model_dump() 페이로드 → analyzer.analyze 인자.

    None은 "미지정"으로 취급해 빼고 analyze()의 기본값(target_metric="cagr" 등)을
    살린다 — None을 명시 전달하면 기본값을 덮어써 결과가 조용히 갈린다(게이트 실사고).
    (is_bars/oos_bars는 기본값 자체가 None이라 드롭해도 동치.)
    """
    kwargs = {"base_request": request["base_request"], "ranges": request.get("ranges")}
    for key in ("n_splits", "train_pct", "anchor", "target_metric",
                "n_trials", "method", "is_bars", "oos_bars"):
        if request.get(key) is not None:
            kwargs[key] = request[key]
    return kwargs


@app.function(
    image=image,
    cpu=WFA_CPU,
    memory=WFA_MEMORY_MB,
    volumes={DATA_PATH: data_volume},
    timeout=JOB_TIMEOUT_S,
    scaledown_window=SCALEDOWN_WINDOW,
    min_containers=0,
    max_containers=JOB_MAX_CONTAINERS,
)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def run_walk_forward(request: dict) -> dict:
    """워크포워드 분석(동기 JSON) — 백엔드 /walk-forward와 동일 계약."""
    _pin_wfa_env()
    engine = _get_engine()
    from engine.walk_forward import WalkForwardAnalyzer

    return _jsonify(WalkForwardAnalyzer(engine).analyze(**_wfa_kwargs(request)))


@app.function(
    image=image,
    cpu=WFA_CPU,
    memory=WFA_MEMORY_MB,
    volumes={DATA_PATH: data_volume},
    timeout=JOB_TIMEOUT_S,
    scaledown_window=SCALEDOWN_WINDOW,
    min_containers=0,
    max_containers=JOB_MAX_CONTAINERS,
)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
def run_walk_forward_stream(request: dict):
    """워크포워드 SSE 스트림 — 백엔드 /walk-forward/stream과 같은 이벤트 프로토콜.

    백엔드는 이 스트림을 바이트 그대로 통과(proxy)시킨다. 클라이언트(백엔드)가
    연결을 끊으면 Starlette가 제너레이터를 취소 → finally에서 협조적 취소 플래그를
    세워 다음 창 경계에서 분석이 중단된다(main.py의 인프로세스 패턴과 동일).
    """
    import json
    import queue as _queue
    import threading
    import time

    from fastapi.responses import StreamingResponse

    _pin_wfa_env()
    engine = _get_engine()

    progress_q: _queue.Queue = _queue.Queue()
    result_holder: dict = {}
    error_holder: dict = {}
    cancel_event = threading.Event()

    def run_wfa():
        try:
            from engine.walk_forward import WalkForwardAnalyzer

            result_holder["data"] = WalkForwardAnalyzer(engine).analyze(
                **_wfa_kwargs(request),
                progress_callback=progress_q.put,
                should_cancel=cancel_event.is_set,
            )
        except Exception as exc:  # noqa: BLE001 — 에러는 이벤트로 전달
            error_holder["error"] = str(exc)

    thread = threading.Thread(target=run_wfa, daemon=True)

    def generate():
        thread.start()
        HEARTBEAT_S = 15.0
        last_emit = time.monotonic()
        try:
            while thread.is_alive():
                emitted = False
                while True:
                    try:
                        payload = progress_q.get_nowait()
                    except _queue.Empty:
                        break
                    yield f"data: {json.dumps({'type': 'progress', **payload}, ensure_ascii=False, default=float)}\n\n"
                    emitted = True
                if emitted:
                    last_emit = time.monotonic()
                elif time.monotonic() - last_emit >= HEARTBEAT_S:
                    yield ": keep-alive\n\n"
                    last_emit = time.monotonic()
                time.sleep(0.2)
            while True:
                try:
                    payload = progress_q.get_nowait()
                except _queue.Empty:
                    break
                yield f"data: {json.dumps({'type': 'progress', **payload}, ensure_ascii=False, default=float)}\n\n"
            # 이벤트 형식은 백엔드 인프로세스 스트림(main.py walk_forward_stream)과
            # 바이트 수준으로 동일해야 한다 — 백엔드가 그대로 통과시키기 때문.
            if error_holder:
                yield f"data: {json.dumps({'type': 'error', 'message': error_holder['error']}, ensure_ascii=False)}\n\n"
            elif "data" in result_holder:
                result = _jsonify(result_holder["data"])
                if result.get("status") in ("error", "cancelled"):
                    yield f"data: {json.dumps({'type': 'error', 'message': result.get('message', '워크포워드 분석 실패')}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'result', 'data': result}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            cancel_event.set()  # 클라이언트 이탈 포함 — 다음 창 경계에서 중단

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
