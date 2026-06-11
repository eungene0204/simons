"""LLM 백엔드 선택 (단일 진실 소스).

MLX(Apple Silicon 전용)를 우선 사용하되, 사용할 수 없는 환경(예: 리눅스 배포 서버)
에서는 자동으로 Ollama로 폴백한다. LLM을 사용하는 모든 코드는 backend 문자열을 직접
하드코딩하지 말고 resolve_llm_backend()로 결정한다.

우선순위:
  1. 환경변수 LLM_BACKEND ("mlx" | "ollama") — 명시적 강제
  2. preferred 인자가 "ollama" 면 그대로 사용
  3. mlx_lm 사용 가능(Darwin + 설치됨) 이면 "mlx", 아니면 "ollama"
"""

from __future__ import annotations

import os
import platform
from typing import Literal, Optional

Backend = Literal["mlx", "ollama"]

# Ollama HTTP 엔드포인트 (배포 시 OLLAMA_HOST 로 교체 가능)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


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
    """사용할 LLM 백엔드를 결정한다.

    preferred 가 "mlx" 라도 MLX를 쓸 수 없으면 "ollama" 로 자동 강등한다.
    """
    forced = os.environ.get("LLM_BACKEND", "").strip().lower()
    if forced in ("mlx", "ollama"):
        return forced  # type: ignore[return-value]

    if preferred == "ollama":
        return "ollama"

    return "mlx" if mlx_available() else "ollama"
