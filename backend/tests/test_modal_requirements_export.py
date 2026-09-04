"""Modal 워커 이미지의 의존성 핀이 uv.lock에서 갈라지지 않았는지 검사.

2026-09-04 uv 이관 전까지 `modal_backtest.py`의 PINNED_DEPS는 prod 컨테이너를 손으로
실측해 옮겨 적은 목록이었다. 직접 의존만 적혀 있었고 전이 의존(scipy·numba·polars-runtime…)은
아무도 고정하지 않았으므로, 앱 박스와 Modal 워커가 조용히 다른 버전으로 돌 수 있었다 —
백테스트의 "실행 장소가 바뀌어도 답이 바뀌지 않는다"는 계약을 사람의 기억에 맡긴 셈이다.

이제 requirements-modal.txt는 앱 박스와 **같은 uv.lock**에서 내보낸 파생물이다. 파생물은
재생성을 잊는 순간 원본과 갈라지므로, 이 테스트가 그 갈라짐을 잡는다.

재생성:  bash scripts/export_modal_requirements.sh
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXPORT = _REPO_ROOT / "requirements-modal.txt"
_MODAL_BACKTEST = _REPO_ROOT / "modal_backtest.py"

# scripts/export_modal_requirements.sh 와 반드시 같은 플래그여야 한다(다르면 거짓 불일치).
_EXPORT_ARGS = [
    "uv", "export", "--frozen", "--only-group", "modal",
    "--no-hashes", "--no-annotate", "--no-header",
]


def test_export_file_exists() -> None:
    assert _EXPORT.is_file(), (
        f"{_EXPORT.name} 이 없다 — bash scripts/export_modal_requirements.sh 로 생성한다"
    )


def test_export_matches_the_lockfile() -> None:
    """커밋된 파생물이 uv.lock의 현재 해석과 같아야 한다."""
    if shutil.which("uv") is None:
        pytest.skip("uv 미설치 — 이 대조는 uv가 있는 환경(CI·로컬 dev)에서만 의미가 있다")

    fresh = subprocess.run(
        _EXPORT_ARGS, cwd=_REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout

    assert fresh == _EXPORT.read_text(encoding="utf-8"), (
        "requirements-modal.txt 가 uv.lock과 어긋난다 — 의존성을 바꾼 커밋에서 "
        "`bash scripts/export_modal_requirements.sh` 를 돌리고 결과를 함께 커밋할 것"
    )


def test_image_actually_installs_the_export() -> None:
    """핀은 선언이 아니라 **전달**돼야 효력이 있다(modal_ollama 핀 사고와 같은 교훈)."""
    source = _MODAL_BACKTEST.read_text(encoding="utf-8")

    match = re.search(r'^PINNED_REQUIREMENTS\s*=\s*"([^"]+)"', source, re.MULTILINE)
    assert match, "modal_backtest.py에 PINNED_REQUIREMENTS 상수가 없다"
    assert match.group(1) == _EXPORT.name, (
        f"PINNED_REQUIREMENTS={match.group(1)!r} — 커밋된 파생물 {_EXPORT.name} 을 가리켜야 한다"
    )

    assert "uv_pip_install(requirements=[PINNED_REQUIREMENTS])" in source, (
        "이미지 빌드가 PINNED_REQUIREMENTS를 설치에 넘기지 않는다 — 선언만 하면 핀이 아니다"
    )


def test_export_excludes_torch() -> None:
    """torch는 CPU 인덱스에서 따로 깐다 — 이 파일에 섞이면 CUDA 휠(~2.5GB)을 받는다."""
    names = {
        line.split("==")[0].strip()
        for line in _EXPORT.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "torch" not in names, (
        "requirements-modal.txt에 torch가 들어갔다 — pyproject의 modal 그룹에서 빼고 재생성할 것"
    )
