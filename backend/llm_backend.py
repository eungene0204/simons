"""LLM 백엔드 선택 (단일 진실 소스).

기본 백엔드는 **Ollama**다. 배포 환경(리눅스 GPU 서버)과 개발 환경(맥)이 동일한
백엔드를 쓰도록(dev/prod parity) Ollama를 기본으로 삼는다. MLX(Apple Silicon 전용)는
맥에서 명시적으로 옵트인할 때만 쓴다. LLM을 사용하는 모든 코드는 backend 문자열을
직접 하드코딩하지 말고 resolve_llm_backend()로 결정한다.

우선순위:
  1. 환경변수 LLM_BACKEND ("mlx" | "ollama") — 명시적 강제 (맥 dev에서 MLX를 쓰려면 이걸로)
  2. preferred 인자가 "mlx" 이고 MLX를 실제 쓸 수 있으면 "mlx" (명시적 옵트인)
  3. 그 외에는 항상 "ollama" (기본값)
"""

from __future__ import annotations

import os
import platform
from typing import Literal, Optional

Backend = Literal["mlx", "ollama"]
Provider = Literal["ollama", "openrouter"]

# Ollama HTTP 엔드포인트 (배포 시 OLLAMA_HOST 로 교체 가능)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

# ── LLM 전송 프로바이더 ──────────────────────────────────────────────────────
# LLM_PROVIDER=openrouter 이면 모든 chat 호출(파서·인터프리터·검증기·코치·AI 리포트)이
# 로컬/Modal Ollama 대신 OpenRouter(OpenAI 호환 API)로 간다(2026-09-06 사용자 결정:
# 로컬 Qwen 모델·prod Modal LLM 대신 API 사용 실험). 호출부는 Ollama /api/chat 형태의
# payload를 그대로 만들고, 전송 어댑터(llm_chat.py)가 프로바이더별 형식으로 바꾼다.
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")
# 기본 모델 — 무료 슬러그(2026-09-06 사용자 결정). Qwen3-32B `:free`는 실측 404(무료 중단)였고
# 무료 19종 중 실제 인터프리터 프롬프트(2만 토큰)로 한국어 JSON을 온전히 낸 것은 이 모델뿐이었다
# (minimax-m3는 랭킹 누락, gemma/glm은 429). 유료 `qwen/qwen3-32b`는 OPENROUTER_MODEL로 선택 가능.
OPENROUTER_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


def llm_provider() -> Provider:
    """LLM 전송 프로바이더. 기본 "ollama", LLM_PROVIDER=openrouter 이면 "openrouter"."""
    value = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
    return "openrouter" if value == "openrouter" else "ollama"


def is_openrouter() -> bool:
    return llm_provider() == "openrouter"


def openrouter_model() -> str:
    """OpenRouter 레인의 모델 슬러그(OPENROUTER_MODEL). 전 슬롯이 이 한 모델을 쓴다 —
    Ollama 슬롯 env(NL_OLLAMA_MODEL 등)는 Ollama 모델명이라 OpenRouter에는 의미가 없다."""
    return os.environ.get("OPENROUTER_MODEL", "").strip() or OPENROUTER_DEFAULT_MODEL


def openrouter_headers() -> dict[str, str]:
    """OpenRouter 인증 헤더. 키가 없으면 즉시 실패한다 — 조용히 로컬로 폴백하면
    운영과 다른 모델로 검증하고도 성공한 것처럼 보이는 사고가 난다(FR-STR-019p ⑤)."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "LLM_PROVIDER=openrouter 인데 OPENROUTER_API_KEY 가 비어 있습니다 — "
            ".env에 키를 넣거나 LLM_PROVIDER를 ollama로 되돌리세요."
        )
    return {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://nullstock.im",
        "X-Title": "nullstock",
    }

# ── Ollama 모델 슬롯 정본 ────────────────────────────────────────────────────
# 이 프로젝트가 쓰는 로컬 모델은 **9B 하나뿐이다**(2026-08-03 사용자 결정 — 분류·파서·
# 코치 슬롯의 4B는 bare enum JSON 파손 34%·해외기업명 테마 오분류가 실측돼 폐기, 전
# 슬롯 9B 단일화). 코드 기본값으로 다른 모델명을 적으면 .env가 로드되지 않은 실행에서
# 조용히 그 모델로 폴백해, 운영과 다른 모델로 검증하고도 성공한 것처럼 보이는 사고가
# 난다 — 실제로 `qwen3:8b`라는 잘못된 기본값이 그런 사고를 냈다(FR-STR-019p ⑤).
OLLAMA_MODEL_9B = "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M"  # 전 슬롯(분류·파서·코치·인터프리터·AI 리포트)


def ollama_auth_headers() -> dict[str, str]:
    """Ollama 요청에 실을 인증 헤더.

    배포 시 Ollama를 Modal serverless GPU(requires_proxy_auth=True)로 빼면 모든
    요청에 Modal proxy-auth 헤더가 필요하다. MODAL_KEY/MODAL_SECRET 가 설정돼 있으면
    헤더를 반환하고, 없으면(로컬 Ollama·MLX) 빈 dict → 기존 동작 그대로.
    """
    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    if key and secret:
        return {"Modal-Key": key, "Modal-Secret": secret}
    return {}


def is_local_ollama() -> bool:
    """OLLAMA_BASE_URL이 로컬 엔드포인트(원격 Modal 등이 아님)인지 판단한다.

    로컬이면 콜드스타트가 없으므로 서버 시작 시 모델을 즉시 메모리에 적재할 수 있다.
    원격(Modal)은 scale-to-zero 콜드스타트 특성상 GET 워밍업을 따로 쓴다.
    """
    if is_openrouter():
        # OpenRouter는 원격 API다 — 로컬 러너 관리(preload·prefill·num_ctx 정합 가드·
        # 연결거부 fast-fail)는 전부 Ollama 로컬 전용이라 여기서 False로 끊는다.
        return False
    return any(host in OLLAMA_BASE_URL for host in ("localhost", "127.0.0.1", "0.0.0.0"))


def mlx_available() -> bool:
    """현재 프로세스에서 MLX 추론이 가능한지 판단한다 (Apple Silicon + mlx_lm 설치)."""
    if platform.system() != "Darwin":
        return False
    try:
        import mlx_lm  # noqa: F401
        return True
    except Exception:
        return False


def resolve_llm_backend(preferred: Optional[str] = None) -> Backend:
    """사용할 LLM 백엔드를 결정한다. 기본값은 "ollama".

    MLX는 (1) LLM_BACKEND=mlx 로 강제하거나, (2) preferred="mlx" 이고 실제로 MLX를
    쓸 수 있을 때만 선택된다. 그 외에는 항상 "ollama".
    """
    forced = os.environ.get("LLM_BACKEND", "").strip().lower()
    if forced in ("mlx", "ollama"):
        return forced  # type: ignore[return-value]

    if preferred == "mlx" and mlx_available():
        return "mlx"

    return "ollama"
