#!/usr/bin/env python3
"""
'ai 모델'의 전체 파싱 흐름을 테스트:
1. 규칙 기반 추출 (안 됨)
2. LLM 폴백 (호출됨)
3. 신호 검증 (키워드 확인)
4. 프롬프트 오버라이드 적용
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.nl_parser import (
    ParsedStrategy,
    TechnicalSignal,
    _parse_rule_based_strategy,
    _validate_signals,
    _apply_prompt_overrides,
    _extract_technical_signals,
    _INDICATOR_KEYWORDS,
    _DESCRIPTIVE_INDICATORS,
)

def pretty_print_strategy(s: ParsedStrategy, indent=2):
    """ParsedStrategy를 읽기 좋게 출력"""
    prefix = " " * indent
    print(f"{prefix}entry_signals: {s.entry_signals}")
    print(f"{prefix}exit_signals: {s.exit_signals}")
    print(f"{prefix}max_positions: {s.max_positions}")
    print(f"{prefix}stop_loss_pct: {s.stop_loss_pct}")
    print(f"{prefix}ranking_metric: {s.ranking_metric}")

def test_ai_model_full_pipeline():
    """전체 파이프라인에서 AI 모델이 어떻게 처리되는지"""

    prompts = [
        "AI 모델이 상승 예측한 종목 매수",
        "ai 모델이 하락을 예측하면 매도",
        "AI 모델 상승 종목만 사서 10개 최대",
        "AI 모델이 매수 신호면 매수, 매도 신호면 매도",
    ]

    for i, prompt in enumerate(prompts, 1):
        print("=" * 80)
        print(f"Test Case {i}: {prompt!r}")
        print("=" * 80)

        # Step 1: 규칙 기반 파싱
        print("\n[Step 1] 규칙 기반 파싱")
        rule_result = _parse_rule_based_strategy(prompt)
        if rule_result:
            print("✓ 성공 - 규칙만으로 충분")
            pretty_print_strategy(rule_result)
        else:
            print("✗ 실패 - LLM으로 폴백 예정")

        # Step 2: 기술적 신호 추출
        print("\n[Step 2] 규칙 기반 기술적 신호 추출")
        entry, exit_ = _extract_technical_signals(prompt)
        print(f"진입: {entry}")
        print(f"청산: {exit_}")

        # Step 3: 신호 검증 시뮬레이션
        print("\n[Step 3] 신호 검증 (LLM 폴백 후)")
        test_signals = [
            TechnicalSignal(indicator="ai_model", signal_type="buy", threshold=70),
            TechnicalSignal(indicator="ai_drop_model", signal_type="sell", threshold=70),
        ]
        for sig in test_signals:
            validated = _validate_signals([sig], prompt)
            status = "✓ 통과" if validated else "✗ 차단"
            print(f"  {sig.indicator}: {status}")
            if not validated:
                print(f"    → 프롬프트에 키워드 {_INDICATOR_KEYWORDS.get(sig.indicator)} 미발견")

        # Step 4: 프롬프트 오버라이드
        print("\n[Step 4] 프롬프트 오버라이드 적용 시뮬레이션")
        simulated = ParsedStrategy(
            description=prompt,
            universe=["KOSPI200"],
            fundamental_filters=[],
            entry_signals=[
                TechnicalSignal(indicator="ai_model", signal_type="buy", threshold=70)
            ],
            exit_signals=[
                TechnicalSignal(indicator="ai_drop_model", signal_type="sell", threshold=70)
            ],
            max_positions=10,
            hold_period_days=None,
            rebalancing_period="none",
            stop_loss_pct=None,
            take_profit_pct=None,
            trailing_stop_pct=None,
            max_mdd_limit_pct=None,
            backtest_period="5y",
            initial_capital=10000000.0,
            execution_timing="next_open",
            fee_rate=0.015,
            slippage_rate=0.05,
        )

        result = _apply_prompt_overrides(simulated, prompt)
        print("오버라이드 후 결과:")
        pretty_print_strategy(result)

        print()

def test_ai_model_keyword_matching():
    """AI 모델 키워드 매칭 상세 분석"""
    print("\n" + "=" * 80)
    print("AI 모델 키워드 매칭 분석")
    print("=" * 80)

    print("\n[설정]")
    print(f"ai_model 키워드: {_INDICATOR_KEYWORDS.get('ai_model')}")
    print(f"ai_drop_model 키워드: {_INDICATOR_KEYWORDS.get('ai_drop_model')}")
    print(f"서술형 지표들(키워드 검증 스킵): {_DESCRIPTIVE_INDICATORS}")

    print("\n[테스트]")
    test_cases = [
        ("ai 모델 매수", True),  # "ai" 포함 → 통과
        ("AI", True),  # "ai" 포함 → 통과
        ("인공지능", True),  # "인공지능" 포함 → 통과
        ("AI 모델", True),  # "ai" 포함 → 통과
        ("머신러닝 모델 매수", False),  # "ai", "인공지능" 미포함 → 차단
        ("딥러닝", False),  # 키워드 미포함 → 차단
    ]

    for prompt, expected_pass in test_cases:
        compact = prompt.lower().replace(" ", "")
        ai_keywords = _INDICATOR_KEYWORDS.get("ai_model", [])
        has_keyword = any(kw in compact for kw in ai_keywords)

        status = "✓ 통과" if has_keyword else "✗ 차단"
        expected = "(예상됨)" if has_keyword == expected_pass else "(⚠️ 예상과 다름)"

        print(f"  {prompt!r}: {status} {expected}")
        if not has_keyword and ai_keywords:
            print(f"    필요한 키워드: {ai_keywords} (없음)")

if __name__ == "__main__":
    test_ai_model_full_pipeline()
    test_ai_model_keyword_matching()
    print("\n" + "=" * 80)
    print("📊 결론")
    print("=" * 80)
    print("""
'ai 모델' 입력의 흐름:

1. 규칙 기반 추출: ✗ 실패
   → _extract_technical_signals에 AI 모델 regex 패턴이 없음

2. LLM 폴백: ✓ 필수
   → SYSTEM_PROMPT의 라인 249-251에서 AI 모델 처리 정의
   → "ai_model" 또는 "ai_drop_model" indicator로 변환

3. 신호 검증: ✓ 통과 (대부분의 경우)
   → 키워드: ["ai", "인공지능"]
   → "AI 모델"에는 "ai" 포함 → 검증 통과
   → ⚠️ 주의: "머신러닝", "딥러닝" 등은 차단됨

4. 프롬프트 오버라이드: ✓ 적용
   → 리스크 필드/universe/ranking 추출 및 적용
   → 기술적 신호는 _validate_signals로 필터링

⚠️ 주의사항:
- "AI 모델"을 입력할 때 "ai" 또는 "인공지능"이라는 단어가 포함되어야 LLM 환각 방지 검증을 통과합니다.
- 프롬프트가 "머신러닝으로 매수"라고 하면 ai_model 신호가 차단될 수 있습니다.
""")
