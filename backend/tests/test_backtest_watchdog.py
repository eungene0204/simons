"""백테스트 워치독(engine.watchdog) + 엔진 AI fail-fast 게이트 테스트.

실사례(2026-07-03): 파싱 환각으로 주입된 ai_model 신호가 꺼둔 AI 백테스트를 실행시켜
행에 빠졌고, SSE 스트림이 상태 메시지를 무한히 내보냈다. 두 방어선을 검증한다:
1) 엔진이 AI 신호를 fail-fast로 거절 (기능 OFF 스위치 / 모델 로드 불가)
2) 그래도 행에 빠지면 워치독이 제한 시간 안에 요청을 끝냄
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.watchdog import (
    BacktestTimeoutError,
    backtest_timeout_s,
    run_with_timeout,
    walk_forward_timeout_s,
)


# ─── run_with_timeout ────────────────────────────────────────────────

def test_returns_result_when_fn_finishes_in_time():
    assert run_with_timeout(lambda: 42, timeout_s=5.0) == 42


def test_propagates_fn_exception():
    def boom():
        raise ValueError("engine error")

    with pytest.raises(ValueError, match="engine error"):
        run_with_timeout(boom, timeout_s=5.0)


def test_raises_timeout_when_fn_hangs():
    def hang():
        time.sleep(10)

    t0 = time.monotonic()
    with pytest.raises(BacktestTimeoutError, match="제한 시간"):
        run_with_timeout(hang, timeout_s=0.2)
    assert time.monotonic() - t0 < 5.0  # 행에 매달리지 않고 즉시 반환


def test_timeout_budget_env_override(monkeypatch):
    monkeypatch.setenv("BACKTEST_TIMEOUT_S", "123")
    assert backtest_timeout_s() == 123.0


def test_walk_forward_timeout_exceeds_single_backtest_timeout(monkeypatch):
    """워크포워드는 창×시도만큼 백테스트를 반복하므로 단일 백테스트 제한(600초)에
    묶이면 정상 실행도 잘려 '연결 끊김'으로 보이던 버그(2026-07-06)의 회귀 방지."""
    monkeypatch.delenv("WALK_FORWARD_TIMEOUT_S", raising=False)
    monkeypatch.delenv("BACKTEST_TIMEOUT_S", raising=False)
    assert walk_forward_timeout_s() > backtest_timeout_s()

    monkeypatch.setenv("WALK_FORWARD_TIMEOUT_S", "777")
    assert walk_forward_timeout_s() == 777.0


# ─── 엔진 AI fail-fast 게이트 ────────────────────────────────────────

def _ai_backtest_request() -> dict:
    return {
        "symbols": ["005930"],
        "entry": {
            "logic": "OR",
            "conditions": [{"id": "ai_model", "type": "indicator", "params": {"threshold": 70}}],
        },
        "exit": {"logic": "OR", "conditions": []},
        "risk_params": {},
        "options": {},
        "period": "1Y",
    }


def test_engine_rejects_ai_signals_when_feature_disabled(monkeypatch):
    """AI_SIGNALS_ENABLED=0이면 AI 신호 백테스트를 즉시 명확한 에러로 거절한다."""
    from backtest_engine import BacktestEngine

    monkeypatch.setenv("AI_SIGNALS_ENABLED", "0")
    engine = BacktestEngine()

    with pytest.raises(Exception, match="비활성화"):
        engine.run_backtest(_ai_backtest_request())


def test_engine_rejects_ai_signals_when_model_unavailable(monkeypatch):
    """AI 모델 로드가 실패하면 0점(0거래) 침묵 진행 대신 즉시 에러를 낸다."""
    from backtest_engine import BacktestEngine

    monkeypatch.delenv("AI_SIGNALS_ENABLED", raising=False)
    engine = BacktestEngine()
    engine._ai_engine = "FAILED"  # AIEngine 초기화 실패 상태를 모사

    with pytest.raises(Exception, match="AI 모델을 로드할 수 없어"):
        engine.run_backtest(_ai_backtest_request())
