"""되묻기 질문 문구·칩(engine.strategy_slots)을 프론트 고정용 픽스처로 내보낸다.

문구의 정본은 백엔드 하나다(2026-08-16 사용자 결정). 그런데 프론트는 칩 답변을 백엔드
왕복 없이 즉시 적용하므로(대화 지연) 질문 문구도 로컬에 있어야 한다 — 판정을 같은 방식으로
고정한 `export_slot_judgments.py`와 같은 계약이다: **정본이 픽스처를 만들고 프론트는 그것만
읽는다.** 프론트에 문구를 직접 적는 표(SLOT_PROMPTS)는 이 픽스처로 대체됐다.

정본을 고치고 이 스크립트를 안 돌리면 backend/tests/test_strategy_slots.py가 깨진다.

실행: python scripts/export_slot_prompts.py     # 픽스처 갱신
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

FIXTURE = ROOT / "app" / "analytics" / "new" / "__fixtures__" / "slot-prompts.json"


def build_fixture() -> dict:
    from engine import strategy_slots as slots

    def entry(field: str, variant: str | None = None) -> dict:
        question, suggestions = slots.slot_question(field, variant)
        return {"question": question, "suggestions": suggestions}

    return {
        "slots": {field: entry(field) for field in slots.FIELD_ORDER},
        # 슬롯 하나가 상황에 따라 다르게 묻는 변형(분위 그룹·랭킹의 '최대 보유'),
        # 그리고 그 전략에 성립하지 않는 선택지를 뺀 매수 조건 칩 목록.
        "variants": {
            slots.MAX_POSITIONS: {
                slots.VARIANT_QUANTILE: entry(slots.MAX_POSITIONS, slots.VARIANT_QUANTILE),
                slots.VARIANT_RANKING: entry(slots.MAX_POSITIONS, slots.VARIANT_RANKING),
            },
            slots.ENTRY: {
                # 단일 종목: 여러 종목을 비교하는 랭킹 선택지가 성립하지 않는다.
                "single_asset": {"suggestions": slots.entry_chips(cross_sectional=False)},
                # ETF: 기업 재무제표 지표를 조건으로 쓸 수 없다.
                "etf": {"suggestions": slots.entry_chips(["ETF"])},
            },
        },
    }


def main() -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(build_fixture(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"✓ {FIXTURE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
