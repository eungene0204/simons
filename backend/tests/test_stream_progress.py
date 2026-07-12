import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from stream_progress import build_backtest_stream_status, simulation_phase_label


def test_simulation_phase_label_omits_current_stock_count():
    # [생존편향] 진행 문구에 '현재 상장 종목 수'(예: 836)를 넣으면 사용자가 현재 상장 종목만
    # 테스트하는 것으로 오해한다. 고정 종목 수를 표기하지 않고 시점 기준 유니버스를 알려야 한다.
    label = simulation_phase_label(5)
    assert "836" not in label
    # 'N종목 × M년' 형태의 고정 종목 수 표기가 사라졌는지 확인한다.
    assert "종목 ×" not in label and "종목×" not in label
    # 기간과 point-in-time(상장폐지 포함) 유니버스임을 알린다.
    assert "5년" in label
    assert "상장폐지" in label


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
