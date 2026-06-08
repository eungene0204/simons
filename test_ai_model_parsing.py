#!/usr/bin/env python3
"""
'ai 모델'이라는 텍스트가 NL 파서에서 어떻게 인식되는지 테스트
"""

import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.nl_parser import (
    NLStrategyParser,
    _parse_rule_based_strategy,
    _extract_technical_signals,
    _validate_signals,
    TechnicalSignal,
)

def test_ai_model_recognition():
    """'ai 모델'이 어떻게 인식되는지 테스트"""

    # Test 1: 규칙 기반 파싱
    print("=" * 80)
    print("Test 1: 규칙 기반 파싱")
    print("=" * 80)

    test_cases = [
        "AI 모델이 상승 예측하면 매수",
        "ai 모델 매수",
        "AI 모델로 매수",
        "AI 모델이 상승 예측한 종목만 매수",
        "AI 모델 하락 예측 시 매도",
        "AI 모델이 하락을 예측하면 청산",
    ]

    for prompt in test_cases:
        print(f"\n입력: {prompt!r}")

        # 규칙 기반 파싱 시도
        rule_result = _parse_rule_based_strategy(prompt)
        print(f"  규칙 기반 결과: {'성공' if rule_result else '실패 (LLM으로 폴백)'}")

        # 기술적 신호 추출 확인
        entry, exit_ = _extract_technical_signals(prompt)
        print(f"  진입 신호: {entry}")
        print(f"  청산 신호: {exit_}")

        if rule_result:
            print(f"  최종 파싱 결과:")
            print(f"    entry_signals: {rule_result.entry_signals}")
            print(f"    exit_signals: {rule_result.exit_signals}")

    # Test 2: 신호 검증
    print("\n" + "=" * 80)
    print("Test 2: 신호 검증 (_validate_signals)")
    print("=" * 80)

    signals_to_test = [
        TechnicalSignal(indicator="ai_model", signal_type="buy", threshold=70),
        TechnicalSignal(indicator="ai_drop_model", signal_type="sell", threshold=70),
    ]

    for signal in signals_to_test:
        print(f"\n신호: {signal.indicator} ({signal.signal_type})")

        for prompt in ["AI 모델 매수", "AI 모델", "ai"]:
            validated = _validate_signals([signal], prompt)
            is_valid = len(validated) > 0
            print(f"  프롬프트 {prompt!r}: {'통과' if is_valid else '차단 (환각으로 판정)'}")

    # Test 3: 키워드 검증 로직 확인
    print("\n" + "=" * 80)
    print("Test 3: 키워드 검증 로직")
    print("=" * 80)

    from engine.nl_parser import _INDICATOR_KEYWORDS

    print(f"\nai_model 키워드: {_INDICATOR_KEYWORDS.get('ai_model', [])}")
    print(f"ai_drop_model 키워드: {_INDICATOR_KEYWORDS.get('ai_drop_model', [])}")

    # 키워드 매칭 시뮬레이션
    test_prompts = ["AI 모델", "ai", "인공지능", "AI 모델 매수"]
    for prompt in test_prompts:
        compact = prompt.lower().replace(" ", "")
        has_ai_kw = any(kw in compact for kw in _INDICATOR_KEYWORDS.get("ai_model", []))
        print(f"  {prompt!r}: {'통과' if has_ai_kw else '실패'}")

if __name__ == "__main__":
    test_ai_model_recognition()
