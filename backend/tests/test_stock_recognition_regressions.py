"""종목 인식 회귀 테스트.

한 번이라도 잘못 인식·분류된 입력을 stock_recognition_regressions.json 에 모아
매 배포마다 자동 재검증한다(과제 7 — 회귀 테스트 시스템).

새 실패가 발견되면 JSON 에 케이스를 추가하기만 하면 자동으로 이 테스트가 검증한다.

원칙: "잘못된 종목을 자신 있게 분석하는 것보다, 모른다고 말하는 것이 안전하다."
모호 입력은 단일 종목으로 임의 선택되면 안 된다(무매칭/복수후보 = 안전).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from intent.classifier import classify
from stock_analysis.symbol_resolver import find_in_text

_DATASET = json.loads((Path(__file__).parent / "stock_recognition_regressions.json").read_text(encoding="utf-8"))


def _unique_ticker(prompt: str) -> str | None:
    tickers = {r.symbol for r in find_in_text(prompt)}
    return next(iter(tickers)) if len(tickers) == 1 else None


@pytest.mark.parametrize("case", _DATASET["recognition"], ids=lambda c: c["input"])
def test_recognition_resolves_expected_ticker(case):
    assert _unique_ticker(case["input"]) == case["expected_ticker"], case.get("note", "")


@pytest.mark.parametrize("case", _DATASET["ambiguous"], ids=lambda c: c["input"])
def test_ambiguous_input_not_arbitrarily_resolved(case):
    # 모호 입력은 단일 종목으로 확정되면 안 된다(무매칭 또는 복수후보여야 재질문 가능).
    assert _unique_ticker(case["input"]) is None, case.get("note", "")


@pytest.mark.parametrize("case", _DATASET["intent"], ids=lambda c: c["input"])
def test_intent_classification(case, monkeypatch):
    # [레거시 레인] 이 케이스들은 원문 정규식이 의도를 판정하던 시절의 회귀 자산이다.
    # 계약 레인에서 의도 판정은 LLM 소관이라 결정적으로 단정할 수 없다 — 그쪽 정확도는
    # scripts/qa_stock_recognition.py 하니스가 실측한다.
    monkeypatch.setenv("INTENT_CLASSIFIER_MODE", "legacy")
    assert classify(case["input"]).intent.value == case["expected_intent"], case.get("note", "")
