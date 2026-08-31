"""Modal serverless CPU — 백테스트 원격 워커 엔드포인트.

하이브리드 배포의 세 번째 레인. 앱(Next/FastAPI)은 Vultr CPU 박스에 상시 떠 있고,
LLM은 modal_ollama.py(GPU)가, **백테스트 실행은 이 워커(CPU)**가 맡는다.
동시 요청이 오면 Modal이 요청 수만큼 컨테이너를 자동으로 늘리므로(오토스케일)
50건 동시 실행도 각자 전용 코어로 병렬 처리된다. 안 쓰면 scale-to-zero라 $0.

계약 (결과 동일성)
─────────────────
백테스트는 "실행 장소가 바뀌어도 답이 바뀌지 않는다"가 계약이다. 이를 위해:
  - 파이썬·수치 라이브러리 버전을 prod 백엔드와 **정확히 같은 값으로 핀**한다
    (아래 PINNED_DEPS — 2026-08-31 prod 컨테이너 실측 버전. 올릴 때는 반드시
    backend/requirements.txt·prod와 같은 커밋에서 함께 올린다).
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

# prod 백엔드 컨테이너 실측 버전(2026-08-31)과 동일 핀 — 결과 동일성의 전제.
PINNED_DEPS = [
    "fastapi==0.135.3",
    "pydantic==2.12.5",
    "numpy==2.4.4",
    "pandas==2.3.3",
    "polars==1.39.3",
    "scipy==1.17.1",
    "numba==0.67.0",
    "vectorbt==1.0.0",
    "plotly==6.8.0",       # vectorbt 전이 의존 핀(7.x는 vectorbt import 파손)
    "pyarrow==23.0.1",
    "stockstats==0.6.8",
    "pykrx==1.2.8",
    "requests==2.33.1",
    "beautifulsoup4==4.14.3",
    "python-dotenv",
    "httpx==0.28.1",
    "joblib==1.5.3",
    "xgboost==3.2.0",
]

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(*PINNED_DEPS)
    # torch는 CPU 휠로(기본 PyPI 휠은 CUDA 동봉 ~2.5GB) — ai_model/ai_drop_model 지표용.
    .pip_install("torch==2.12.0", index_url="https://download.pytorch.org/whl/cpu")
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
    import json
    import sys

    if f"{APP_ROOT}/backend" not in sys.path:
        sys.path.insert(0, f"{APP_ROOT}/backend")

    global _engine
    try:
        _engine
    except NameError:
        from backtest_engine import BacktestEngine

        _engine = BacktestEngine()  # 컨테이너 수명 동안 재사용(웜 요청은 즉시 실행)

    result = _engine.run_backtest(request)
    # numpy 스칼라가 섞여 있어도 순수 JSON으로 정규화해 반환한다
    # (백엔드는 어차피 pydantic response_model로 한 번 더 검증한다).
    return json.loads(json.dumps(result, default=float))
