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

# Ollama HTTP 엔드포인트 (배포 시 OLLAMA_HOST 로 교체 가능)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


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
