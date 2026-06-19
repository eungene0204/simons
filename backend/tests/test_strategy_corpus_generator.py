"""전략 코퍼스 생성기/NL 렌더러 회귀 테스트.

코퍼스 재구축(bge-m3) 파이프라인의 입력 품질을 보증한다:
- AI 신호 절대 미생성 (현행 서비스 미사용)
- 전부 to_backtest_request 변환 가능 (완결성)
- strategy_hash dedup → 고유성
- 시드 결정성 (재현 가능한 코퍼스)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from corpus.generator import FORBIDDEN_INDICATORS, generate_strategies
from corpus.nl_templates import render_description
from engine.strategy_converter import to_backtest_request
from vector_memory.identity import strategy_hash_for


@pytest.fixture(scope="module")
def strategies():
    return generate_strategies(300, seed=7)


def test_no_ai_signals(strategies):
    """코퍼스에 ai_model/ai_drop_model 신호가 절대 들어가면 안 된다."""
    for strategy in strategies:
        for sig in [*strategy.entry_signals, *strategy.exit_signals]:
            assert sig.indicator not in FORBIDDEN_INDICATORS


def test_all_convertible(strategies):
    """모든 전략이 백테스트 요청으로 변환 가능해야 한다(LLM 폴백 없이)."""
    for strategy in strategies:
        req = to_backtest_request(strategy, resolve_symbols=False)
        assert req["entry"]["conditions"] or req["exit"]["conditions"] or strategy.ranking_metric


def test_unique_by_hash(strategies):
    """생성 결과는 strategy_hash 기준 전부 고유해야 한다."""
    hashes = {strategy_hash_for(s.model_dump()) for s in strategies}
    assert len(hashes) == len(strategies)


def test_every_strategy_complete(strategies):
    """각 전략은 진입 요건과 회전 요건(청산/보유기간/리밸런싱/랭킹)을 모두 갖춰야 한다."""
    for strategy in strategies:
        has_entry = bool(strategy.fundamental_filters or strategy.entry_signals or strategy.ranking_metric)
        has_turnover = bool(
            strategy.exit_signals
            or strategy.hold_period_days
            or strategy.rebalancing_period != "none"
            or strategy.ranking_metric
        )
        assert has_entry and has_turnover


def test_seed_deterministic():
    """같은 시드는 같은 코퍼스를(해시 순서까지) 재현해야 한다."""
    a = [strategy_hash_for(s.model_dump()) for s in generate_strategies(100, seed=123)]
    b = [strategy_hash_for(s.model_dump()) for s in generate_strategies(100, seed=123)]
    assert a == b


def test_render_description_deterministic_and_nonempty(strategies):
    """NL 설명은 결정적이고 비어있지 않으며 미치환 플레이스홀더가 없어야 한다."""
    for strategy in strategies:
        first = render_description(strategy)
        assert first == render_description(strategy)
        assert len(first) >= 10
        assert "{" not in first and "}" not in first


def test_render_descriptions_are_varied(strategies):
    """설명이 전략마다 충분히 다양해야 한다(임베딩 검색 신호 확보)."""
    descriptions = {render_description(s) for s in strategies}
    assert len(descriptions) >= int(len(strategies) * 0.95)
