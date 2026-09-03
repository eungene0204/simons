"""되묻기 칩 픽스처 신선도 — 정본(레지스트리 추천값·primary 칩 빌더)이 바뀌면 프론트 픽스처도
갱신돼야 한다(scripts/export_clarification_chips.py). 픽스처는 /us 영어 사전 게이트
(tests/clarification-chips-i18n.test.ts)의 입력이라, 낡으면 새 칩이 한국어로 새도 게이트가 초록이다."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_clarification_chips_fixture_is_fresh():
    root = Path(__file__).resolve().parents[2]
    fixture_path = root / "app" / "analytics" / "new" / "__fixtures__" / "clarification-chips.json"
    assert fixture_path.exists(), "칩 픽스처가 없다 — export_clarification_chips.py 실행 필요"
    spec = importlib.util.spec_from_file_location(
        "export_clarification_chips", root / "scripts" / "export_clarification_chips.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        expected = module.build_fixture()
    finally:
        sys.modules.pop(spec.name, None)
    committed = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert committed == expected, (
        "되묻기 칩 정본이 바뀌었는데 프론트 픽스처가 낡았다 — "
        "python scripts/export_clarification_chips.py 로 갱신할 것"
    )
