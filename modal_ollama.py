"""
Modal serverless GPU — Ollama(Qwen) LLM 엔드포인트.

하이브리드 배포의 GPU 절반. 앱(Next/FastAPI)은 싼 CPU 박스(Vultr)에 상시 떠 있고,
LLM(코치 / 뉴스요약 / NL 전략파서 / 설명생성)만 이 Modal 함수가 serverless GPU로 처리한다.
안 쓰면 scale-to-zero 라 $0.

왜 "Ollama를 그대로" 띄우나
─────────────────────────
앱은 Ollama 네이티브 API를 직접 호출한다:
  - engine/nl_parser.py  : {OLLAMA_HOST}/api/chat  +  {OLLAMA_HOST}/v1 (instructor/openai)
  - ai/summarize.py      : {OLLAMA_HOST}/api/chat
따라서 일반 OpenAI API로 바꾸면 코드 수정이 크다. 대신 진짜 Ollama 서버를 컨테이너 안에서
돌리고 포트 11434를 @modal.web_server로 그대로 노출하면 /api/chat·/v1·/api/tags 가 전부
투명하게 동작 → 앱은 .env의 OLLAMA_HOST 한 줄만 이 함수의 URL로 바꾸면 끝.

모델은 앱 설정과 일치해야 한다 (불일치 시 Ollama가 "model not found"):
  앱 .env: NL_OLLAMA_MODEL=hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M  ==  아래 MODEL
  (코드 기본값 qwen3:8b가 아니라 .env 오버라이드 값이 실제 사용 모델)

배포
────
  pip install modal && modal token new        # 최초 1회 인증
  modal run  modal_ollama.py::download_model   # 모델을 볼륨에 1회 프리캐시(콜드스타트 단축)
  modal deploy modal_ollama.py                 # 영구 배포 → https URL 출력

  # 앱 박스 .env:
  #   OLLAMA_HOST=https://<org>--simons-ollama-ollama-server.modal.run
  #   (requires_proxy_auth=True 이므로 앱이 Modal-Key/Modal-Secret 헤더를 보내야 함 — 아래 보안 메모)

보안 (필수)
──────────
requires_proxy_auth=True 로 열어두지 않으면 누구나 네 GPU를 호출해 요금 폭탄이 난다.
앱 쪽은 Ollama로 가는 모든 요청에 Modal proxy-auth 헤더를 실어야 한다:
  Modal-Key: <token-id>,  Modal-Secret: <token-secret>   (modal token 생성분)
→ engine/nl_parser.py 의 OpenAI(default_headers=...) 와 httpx /api/chat 호출,
  ai/summarize.py 의 httpx 호출에 헤더 주입이 필요(별도 소규모 작업).
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.request

import modal

# ── 설정 ──────────────────────────────────────────────────────────────────────
MODEL = "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M"  # 앱의 NL_OLLAMA_MODEL(.env)과 반드시 동일
GPU = "L4"                  # 8B Q4(~6GB)엔 L4(24GB)면 충분. 더 싸게: "T4"(16GB), 더 빠르게: "A10G"
OLLAMA_PORT = 11434
SCALEDOWN_WINDOW = 300      # 마지막 요청 후 5분 warm 유지 → 테스트 세션 중 콜드스타트 감소(비용 trade-off)
STARTUP_TIMEOUT = 600       # 첫 콜드스타트에서 모델 로드/풀까지 대기 여유

OLLAMA_VERSION = "0.5.7"    # 핀: 빌드 재현성

# ── 이미지: Ollama 설치 ────────────────────────────────────────────────────────
image = (
    modal.Image.debian_slim()
    .apt_install("curl", "zstd")  # zstd: 최신 ollama 설치 스크립트가 추출에 요구
    .run_commands(
        "curl -fsSL https://ollama.com/install.sh | sh",
    )
    .env(
        {
            "OLLAMA_HOST": f"0.0.0.0:{OLLAMA_PORT}",  # 모든 인터페이스 바인딩(Modal이 프록시)
            "OLLAMA_KEEP_ALIVE": "-1",                # warm 컨테이너 동안 모델을 VRAM에 유지(요청간 재로드 방지)
        }
    )
)

app = modal.App("simons-ollama")

# 모델 가중치 캐시 — 콜드스타트마다 5GB 재다운로드를 막는다.
model_volume = modal.Volume.from_name("simons-ollama-models", create_if_missing=True)
VOLUME_PATH = "/root/.ollama"


def _wait_until_ready(timeout: int = 60) -> None:
    """ollama serve 가 11434에서 응답할 때까지 대기."""
    url = f"http://127.0.0.1:{OLLAMA_PORT}/api/tags"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("ollama serve가 제때 기동하지 않음")


def _start_ollama_and_pull() -> subprocess.Popen:
    """ollama serve 백그라운드 기동 + 모델 보장(볼륨에 있으면 즉시, 없으면 pull)."""
    proc = subprocess.Popen(["ollama", "serve"])
    _wait_until_ready()
    # pull은 idempotent — 볼륨에 캐시돼 있으면 매니페스트만 확인하고 즉시 끝난다.
    subprocess.run(["ollama", "pull", MODEL], check=True)
    model_volume.commit()  # 새로 받았으면 볼륨에 영속화
    return proc


@app.function(
    image=image,
    gpu=GPU,
    volumes={VOLUME_PATH: model_volume},
    timeout=24 * 60 * 60,        # 장시간 단일 요청도 허용(여기선 서버 수명)
    scaledown_window=SCALEDOWN_WINDOW,
    min_containers=0,            # scale-to-zero — 안 쓰면 $0
)
@modal.concurrent(max_inputs=4)  # 한 컨테이너가 동시 요청 4개까지(10명 테스트 충분, VRAM 한도 내)
@modal.web_server(port=OLLAMA_PORT, startup_timeout=STARTUP_TIMEOUT, requires_proxy_auth=True)
def ollama_server() -> None:
    """포트 11434(Ollama)를 HTTPS로 노출. 컨테이너 기동 시 serve+pull 후 Modal이 프록시."""
    _start_ollama_and_pull()
    # web_server: 이 함수가 반환해도 Popen 프로세스는 계속 11434를 서빙한다.


@app.function(
    image=image,
    gpu=GPU,
    volumes={VOLUME_PATH: model_volume},
    timeout=30 * 60,
)
def download_model() -> None:
    """모델을 볼륨에 1회 프리캐시.  실행: modal run modal_ollama.py::download_model"""
    proc = _start_ollama_and_pull()
    print(f"✅ {MODEL} 볼륨 캐시 완료")
    proc.terminate()
