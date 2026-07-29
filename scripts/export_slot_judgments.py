"""빈 슬롯 판정(engine.strategy_slots)의 교차 런타임 계약 픽스처를 생성한다.

프론트는 칩 답변을 백엔드 왕복 없이 즉시 적용하므로(대화 지연) 판정을 로컬에서도
계산해야 한다 — 구현이 둘일 수밖에 없다면, **판정의 정본은 백엔드 하나**로 두고
프론트를 그 정본에 고정한다. 이 스크립트가 정본의 답을 픽스처로 내보내고,
vitest(`app/analytics/new/backtestReadiness.parity.test.ts`)가 프론트 게이트를
같은 입력에 돌려 대조한다. 어긋나면 CI가 깨진다.

실행: python scripts/export_slot_judgments.py     # 픽스처 갱신
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

FIXTURE = ROOT / "app" / "analytics" / "new" / "__fixtures__" / "slot-judgments.json"

ALL_EXPLICIT = ["universe", "max_positions", "rebalancing",
                "backtest_period", "initial_capital"]


def _sig(kind: str, signal_type: str) -> dict:
    return {"indicator": kind, "signal_type": signal_type,
            "short_period": 5, "long_period": 20}


def _complete() -> dict:
    return {
        "description": "완성 전략",
        "universe": ["KOSPI"],
        "target_symbols": [],
        "sector": None,
        "fundamental_filters": [],
        "entry_signals": [_sig("ma_crossover", "buy")],
        "exit_signals": [_sig("ma_crossover", "sell")],
        "ranking_metric": None,
        "hold_period_days": None,
        "max_positions": 10,
        "rebalancing_period": "monthly",
        "stop_loss_pct": 10.0,
        "take_profit_pct": 20.0,
        "trailing_stop_pct": None,
        "backtest_period": "5y",
        "backtest_start_date": None,
        "backtest_end_date": None,
        "initial_capital": 10_000_000,
    }


def _case(name: str, *, patch: Optional[dict] = None,
          explicit: Optional[list] = None, declined: bool = False) -> dict:
    parsed = _complete()
    parsed.update(patch or {})
    return {
        "name": name,
        "parsed": parsed,
        "explicitFields": ALL_EXPLICIT if explicit is None else explicit,
        "allowNoRebalancing": declined,
    }


def build_cases() -> list[dict]:
    cases: list[dict] = [
        _case("완성 전략"),
        _case("빈 전략(기본값만)", patch={
            "universe": [], "entry_signals": [], "exit_signals": [],
            "rebalancing_period": "none", "stop_loss_pct": None,
            "take_profit_pct": None,
        }, explicit=[]),
        # 필드별 단일 공백 — 진행 순서(첫 공백 하나)를 필드마다 확인한다.
        _case("유니버스 없음", patch={"universe": [], "sector": None}, explicit=[]),
        _case("유니버스 값은 있고 미언급", explicit=[f for f in ALL_EXPLICIT if f != "universe"]),
        _case("매수 조건 없음", patch={"entry_signals": []}),
        _case("매수=재무 필터", patch={
            "entry_signals": [],
            "fundamental_filters": [{"metric": "per", "operator": "<=", "value": 10}],
        }),
        _case("매수=랭킹", patch={"entry_signals": [], "ranking_metric": "return"}),
        _case("매도 조건 없음", patch={"exit_signals": [], "rebalancing_period": "none"},
              explicit=[f for f in ALL_EXPLICIT if f != "rebalancing"]),
        _case("매도=보유기간", patch={"exit_signals": [], "hold_period_days": 20}),
        _case("매도=정기 리밸런싱", patch={"exit_signals": []}),
        _case("최대 보유 미언급", explicit=[f for f in ALL_EXPLICIT if f != "max_positions"]),
        # 0은 모델이 하한(1)으로 보정한다 — 프론트가 받는 값도 보정 후 값이다.
        _case("최대 보유 0은 모델이 하한으로 보정", patch={"max_positions": 0}),
        _case("리밸런싱 없음", patch={"rebalancing_period": "none"},
              explicit=[f for f in ALL_EXPLICIT if f != "rebalancing"]),
        _case("리밸런싱 안 함(사용자 결정)", patch={"rebalancing_period": "none"},
              explicit=[f for f in ALL_EXPLICIT if f != "rebalancing"], declined=True),
        _case("손절 없음", patch={"stop_loss_pct": None}),
        _case("익절 없음", patch={"take_profit_pct": None}),
        _case("트레일링만 있음", patch={"stop_loss_pct": None, "trailing_stop_pct": 10.0}),
        _case("기간 미언급", explicit=[f for f in ALL_EXPLICIT if f != "backtest_period"]),
        _case("초기 자본 미언급", explicit=[f for f in ALL_EXPLICIT if f != "initial_capital"]),
        _case("초기 자본 값 0", patch={"initial_capital": 0}),
        # 지정 종목 모드
        _case("단독 종목(리밸런싱 면제)", patch={
            "target_symbols": ["005930"], "universe": [], "rebalancing_period": "none",
        }, explicit=[f for f in ALL_EXPLICIT if f not in ("universe", "rebalancing")]),
        _case("다종목 지정(리밸런싱 필요)", patch={
            "target_symbols": ["108860", "139670", "051160"], "universe": [],
            "rebalancing_period": "none",
        }, explicit=[f for f in ALL_EXPLICIT if f not in ("universe", "rebalancing")]),
        _case("지정 종목인데 매수 조건 없음", patch={
            "target_symbols": ["108860", "139670"], "universe": [], "entry_signals": [],
        }),
        _case("업종만 지정", patch={"universe": [], "sector": "반도체"}),
        # 신규 상장 유니버스(FR-STR-073) — 대상 시기를 되묻는 중이라 값이 없어도
        # 사용자가 대상을 말한 것이므로 유니버스를 다시 묻지 않는다.
        _case("신규 상장만 지정(대상 시기 되묻는 중)", patch={
            "universe": [], "sector": None, "new_listing_only": True,
            "listing_from": None, "listing_to": None,
        }),
        # [회귀 2026-07-29] 신규 상장 코호트는 창 시작이 상장일 하한으로 확정된다 —
        # 시스템이 정한 값이라 provenance엔 없지만 다시 물으면 안 된다.
        _case("신규 상장 코호트 — 백테스트 기간 재질문 금지", patch={
            "new_listing_only": True, "listing_from": "2026-01-01",
            "listing_to": "2026-12-31", "backtest_start_date": "2026-01-01",
        }, explicit=[f for f in ALL_EXPLICIT if f != "backtest_period"]),
        # 명시 날짜가 있는 창 — 날짜가 있다고 판정이 뒤집히지 않는다(회귀 고정).
        _case("명시 날짜가 있는 백테스트 창", patch={
            "backtest_start_date": "2020-01-01", "backtest_end_date": "2024-12-31",
        }),
    ]
    return cases


def judge(case: dict) -> tuple[dict, Optional[str], list[str]]:
    """(프론트가 받는 parsed, 첫 빈 슬롯, 채워진 슬롯 라벨). parsed는 모델 검증을 거친 dump다 —
    입력값 그대로 두면 모델 보정(하한 클램프 등)이 두 런타임을 갈라놓는다."""
    from engine.nl_parser import ParsedStrategy
    from engine import strategy_slots

    parsed = ParsedStrategy.model_validate(case["parsed"])
    kwargs = dict(
        explicit_fields=case["explicitFields"],
        require_explicit=True,
        rebalancing_declined=case["allowNoRebalancing"],
    )
    status = strategy_slots.next_missing(parsed, **kwargs)
    # 슬롯별 정답도 함께 내보낸다 — '첫 빈 슬롯' 하나만으로는 슬롯별로 표시하는 소비자
    # (진행률 패널)를 대조할 수 없어, 게이트만 고치고 패널이 낡은 채 남았다(2026-07-29).
    filled = strategy_slots.filled_slots(parsed, **kwargs)
    return parsed.model_dump(mode="json"), (status.field if status else None), filled


def build_fixture() -> dict[str, Any]:
    cases = []
    for case in build_cases():
        parsed_dump, missing_field, filled_slots = judge(case)
        cases.append({**case, "parsed": parsed_dump,
                      "expectedMissingField": missing_field,
                      "expectedFilledSlots": filled_slots})
    return {
        "_comment": (
            "engine/strategy_slots.py(빈 슬롯 판정 SOT)가 생성한 계약 픽스처. "
            "직접 편집하지 말 것 — python scripts/export_slot_judgments.py 로 갱신한다. "
            "프론트 게이트(backtestReadiness.ts)와 진행률 패널"
            "(builderProgressPresentation.ts)은 같은 입력에 같은 답을 내야 한다."
        ),
        "cases": cases,
    }


def main() -> int:
    fixture = build_fixture()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{FIXTURE.relative_to(ROOT)} — {len(fixture['cases'])}개 케이스")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
