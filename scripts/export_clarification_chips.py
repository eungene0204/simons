"""되묻기 칩(strategy_conversation.primary._clarification_items가 만드는 열거형 선택지)의
한국어 정본 목록을 프론트 픽스처로 내보낸다.

칩은 백엔드가 한국어 정본으로 만들고(칩=값 결속 계약 — 결속은 한국어 표기로 발행 시 확정),
/us 표시는 프론트 t()가 lib/i18n/en.ts로 옮긴다. 값이 섞인 칩("매출액증가율 10% 이상",
"수익률 산정 기간 60일")은 조합이 유한하므로 여기서 전부 열거해 사전 누락을 게이트로 막는다
(tests/clarification-chips-i18n.test.ts). 정본(레지스트리 추천값·칩 빌더)을 고치고 이 스크립트를
안 돌리면 backend/tests/test_clarification_chips_fixture.py가 깨진다.

실행: python scripts/export_clarification_chips.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
FIXTURE = ROOT / "app" / "analytics" / "new" / "__fixtures__" / "clarification-chips.json"


def build_fixture() -> dict:
    from strategy_conversation import primary
    from strategy_conversation.registry.indicator_registry import REGISTRY

    chips: dict[str, list[str]] = {}
    # ① 조건 임계값 칩 — 추천값이 있는 지표 × 방향(이상/이하). 시가총액 '이하'는 3단 변형.
    seen: set[str] = set()
    values: list[str] = []
    for spec in REGISTRY.values():
        if spec.id in seen or spec.recommended_value is None or spec.data_pending:
            continue
        seen.add(spec.id)
        unit = {"percent": "%", "ratio": "배", "억원": "억원", "년": "년"}.get(spec.value_type or "", "")
        name = spec.display_name.split("(")[0]
        for direction in ("이상", "이하"):
            if spec.id == "fundamental.market_cap" and direction == "이하":
                values.extend(f"{name} {v:g}{unit} {direction}"
                              for v in primary._numeric_options(spec.recommended_value, 1000, 3000))
            else:
                values.append(f"{name} {spec.recommended_value:g}{unit} {direction}")
    chips["condition_values"] = values
    # ② 랭킹 산정 기간 칩
    chips["ranking_lookback"] = (
        [f"수익률 산정 기간 {n}일" for n in primary._numeric_options(60, 20, 120)]
        + [f"변동성 산정 기간 {n}일" for n in primary._numeric_options(60, 120, 200)]
    )
    # ③ 슬롯 칩 — 추천값은 검증기 정본(종목수 10·리밸런싱 monthly)과 인터프리터 추천값 범위.
    slot: list[str] = []
    for field, (_topic, build) in primary._SLOT_CHIP_BUILDERS.items():
        recs = {"strategy.portfolio.selection_count": [10, 5, 20],
                "strategy.portfolio.hold_period_days": [None, 20, 60],
                "strategy.risk_management.stop_loss": [None, 5, 10, 15],
                "strategy.risk_management.take_profit": [None, 10, 20, 30],
                "strategy.risk_management.trailing_stop": [None, 10, 15]}.get(field, [None])
        for rec in recs:
            for chip in build(rec):
                if chip not in slot:
                    slot.append(chip)
    chips["slots"] = slot
    # ④ 크로스 기간 칩
    chips["cross_periods"] = [primary._cross_period_chip(role, s, l)
                              for role in ("entry", "exit") for s, l in primary._CROSS_PERIOD_OPTIONS]
    # ⑤ 신규 상장 시기 칩 — 연도는 오늘 기준이라 픽스처엔 상대 표기만 싣고, 연도 칩은 프론트
    #    사전이 "{0}년 상장" 템플릿으로는 못 옮기므로 백엔드가 ui_language.msg로 만든다.
    chips["new_listing"] = [c for c in primary._new_listing_period_chips() if "년 상장" not in c]
    # ⑥ 시장 국면 필터·변동성 역비중 칩(엔진 v16.14) — 정본 표 그대로.
    from engine import strategy_slots
    chips["portfolio_extras"] = (
        list(strategy_slots.MARKET_REGIME_EXPOSURE_CHIP_VALUES)
        + list(strategy_slots.MARKET_REGIME_MA_CHIP_VALUES)
        + list(strategy_slots.MARKET_REGIME_VOL_MULTIPLE_CHIP_VALUES)
        + list(strategy_slots.ALLOCATION_LOOKBACK_CHIP_VALUES)
    )
    return chips


def main() -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(build_fixture(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ {FIXTURE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
