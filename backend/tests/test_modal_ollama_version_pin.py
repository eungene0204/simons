"""Modal Ollama 이미지의 버전 핀이 실제로 설치에 전달되는지 검사(소스 스캔).

2026-08-21 사고: `OLLAMA_VERSION` 상수는 "핀: 빌드 재현성" 주석과 함께 선언돼 있었지만
설치 명령(`curl … install.sh | sh`)에 전달되지 않아, 이미지를 다시 빌드할 때마다 최신
Ollama가 깔렸다. 그 결과 프로덕션(0.30.8)과 로컬 dev(0.30.7)의 추론 스택이 조용히
어긋났고, 같은 프롬프트·같은 가중치·temperature 0에서도 전략 해석 결과가 갈렸다
(프로덕션만 '최대 보유 기간'을 반영하고도 unsupported_features에 이중 기입 → 거짓
"지원하지 않아 전략에 반영하지 못했어요" 안내).

핀은 선언이 아니라 **전달**돼야 효력이 있다 — 이 테스트가 그 배선을 강제한다.
"""

from __future__ import annotations

import re
from pathlib import Path

_MODAL_OLLAMA = Path(__file__).resolve().parents[2] / "modal_ollama.py"


def _source() -> str:
    return _MODAL_OLLAMA.read_text(encoding="utf-8")


def test_modal_ollama_source_exists() -> None:
    assert _MODAL_OLLAMA.is_file(), f"{_MODAL_OLLAMA} 가 없다 — 경로가 바뀌었으면 이 테스트도 갱신"


def test_ollama_version_pin_is_a_concrete_version() -> None:
    """핀 값은 install.sh의 ?version= 이 받는 표기(접두사 v 없는 x.y.z)여야 한다."""
    match = re.search(r'^OLLAMA_VERSION\s*=\s*"([^"]+)"', _source(), re.MULTILINE)
    assert match, "modal_ollama.py에 OLLAMA_VERSION 상수가 없다"
    assert re.fullmatch(r"\d+\.\d+\.\d+", match.group(1)), (
        f"OLLAMA_VERSION={match.group(1)!r} — install.sh는 접두사 'v' 없는 x.y.z를 요구한다"
    )


def test_install_command_passes_the_version_pin() -> None:
    """install.sh 호출이 OLLAMA_VERSION을 실제로 넘겨야 한다(선언만 하면 핀이 아니다)."""
    install_lines = [
        line for line in _source().splitlines()
        if "install.sh" in line and not line.lstrip().startswith("#")
    ]
    assert install_lines, "modal_ollama.py에서 ollama install.sh 호출을 찾지 못했다"
    for line in install_lines:
        assert "OLLAMA_VERSION" in line, (
            f"설치 명령이 버전 핀을 전달하지 않는다 → 빌드마다 최신판이 깔린다: {line.strip()}"
        )
