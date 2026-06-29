import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from stream_progress import build_backtest_stream_status


def test_stream_status_uses_named_phases_first():
    phases = ["데이터 로딩", "시뮬레이션 실행", "성과 지표 계산"]

    assert build_backtest_stream_status(0, phases) == "데이터 로딩"
    assert build_backtest_stream_status(10, phases) == "시뮬레이션 실행"
    assert build_backtest_stream_status(20, phases) == "성과 지표 계산"


def test_stream_status_returns_none_between_ticks():
    assert build_backtest_stream_status(1, ["x"]) is None
    assert build_backtest_stream_status(9, ["x"]) is None


def test_stream_status_keeps_emitting_after_named_phases_are_exhausted():
    phases = ["데이터 로딩", "시뮬레이션 실행", "성과 지표 계산"]

    assert build_backtest_stream_status(30, phases) == "전략 조건 계산 및 시뮬레이션 진행 중..."
    assert build_backtest_stream_status(50, phases) == "전략 조건 계산 및 시뮬레이션 진행 중..."
