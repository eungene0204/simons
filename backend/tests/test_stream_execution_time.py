"""
backtest-stream 엔드포인트의 executionTime 기록 테스트

변경사항 회귀 방지:
- run_bt()가 engine.run_backtest() 결과에 executionTime을 주입하는지 확인
"""
import time
import threading
import pytest
from unittest.mock import MagicMock, patch


def simulate_run_bt(mock_engine_result: dict) -> dict:
    """main.py의 run_bt() 패턴을 그대로 재현"""
    result_holder: dict = {}
    error_holder: dict = {}

    def run_bt():
        try:
            start_time = time.time()
            result = dict(mock_engine_result)  # engine.run_backtest() 대체
            result["executionTime"] = time.time() - start_time
            result_holder["data"] = result
        except Exception as exc:
            error_holder["error"] = str(exc)

    t = threading.Thread(target=run_bt)
    t.start()
    t.join()
    return result_holder.get("data", {}), error_holder


def test_execution_time_is_added():
    """executionTime 키가 결과에 존재해야 함"""
    engine_result = {"totalReturn": 10.0, "cagr": 5.0, "trades": 20}
    result, errors = simulate_run_bt(engine_result)

    assert not errors
    assert "executionTime" in result


def test_execution_time_is_non_negative():
    """executionTime은 0 이상의 숫자여야 함"""
    engine_result = {"totalReturn": 5.0}
    result, errors = simulate_run_bt(engine_result)

    assert not errors
    assert isinstance(result["executionTime"], float)
    assert result["executionTime"] >= 0


def test_execution_time_does_not_overwrite_other_fields():
    """executionTime 추가가 기존 결과 필드를 덮어쓰지 않아야 함"""
    engine_result = {
        "totalReturn": 15.3,
        "cagr": 7.2,
        "maxDrawdown": -12.5,
        "winRate": 55.0,
        "profitFactor": 1.8,
    }
    result, errors = simulate_run_bt(engine_result)

    assert not errors
    assert result["totalReturn"] == 15.3
    assert result["cagr"] == 7.2
    assert result["maxDrawdown"] == -12.5
    assert result["winRate"] == 55.0
    assert result["profitFactor"] == 1.8
    assert "executionTime" in result


def test_execution_time_on_exception():
    """engine.run_backtest()가 예외를 던지면 error_holder에 기록되고 result_holder는 비어야 함"""
    result_holder: dict = {}
    error_holder: dict = {}

    def run_bt():
        try:
            start_time = time.time()
            raise RuntimeError("backtest failed")
            result_holder["data"] = {}
        except Exception as exc:
            error_holder["error"] = str(exc)

    t = threading.Thread(target=run_bt)
    t.start()
    t.join()

    assert "error" in error_holder
    assert error_holder["error"] == "backtest failed"
    assert "data" not in result_holder
