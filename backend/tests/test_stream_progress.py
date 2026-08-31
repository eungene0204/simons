import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from stream_progress import build_backtest_stream_status, simulation_phase_label


def render(status):
    """(템플릿, 인자) 쌍을 프론트 t()와 같은 규칙({0} 위치 인자)으로 펼친다."""
    template, args = status
    return template.format(*args)


def test_simulation_phase_label_omits_current_stock_count():
    # [생존편향] 진행 문구에 '현재 상장 종목 수'(예: 836)를 넣으면 사용자가 현재 상장 종목만
    # 테스트하는 것으로 오해한다. 고정 종목 수를 표기하지 않고 시점 기준 유니버스를 알려야 한다.
    label = render(simulation_phase_label(5))
    assert "836" not in label
    # 'N종목 × M년' 형태의 고정 종목 수 표기가 사라졌는지 확인한다.
    assert "종목 ×" not in label and "종목×" not in label
    # 기간과 point-in-time(상장폐지 포함) 유니버스임을 알린다.
    assert "5년" in label
    assert "상장폐지" in label


def test_simulation_phase_label_keeps_years_as_a_placeholder():
    # 표시 번역은 프론트 t() 소관 — 기간이 문장에 박히면 사전 키가 연수마다 달라져
    # /us에서 번역할 수 없다. 정본 템플릿은 {0}을 유지하고 연수는 인자로만 싣는다.
    template, args = simulation_phase_label(3)
    assert "{0}" in template
    assert "3" not in template
    assert args == [3]


def test_stream_status_uses_named_phases_first():
    phases = [("데이터 로딩", []), ("시뮬레이션 실행", []), ("성과 지표 계산", [])]

    assert build_backtest_stream_status(0, phases) == ("데이터 로딩", [])
    assert build_backtest_stream_status(10, phases) == ("시뮬레이션 실행", [])
    assert build_backtest_stream_status(20, phases) == ("성과 지표 계산", [])


def test_stream_status_returns_none_between_ticks():
    assert build_backtest_stream_status(1, [("x", [])]) is None
    assert build_backtest_stream_status(9, [("x", [])]) is None


def test_stream_status_keeps_emitting_after_named_phases_are_exhausted():
    phases = [("데이터 로딩", []), ("시뮬레이션 실행", []), ("성과 지표 계산", [])]

    assert build_backtest_stream_status(30, phases) == ("전략 조건 계산 및 시뮬레이션 진행 중...", [])
    assert build_backtest_stream_status(50, phases) == ("전략 조건 계산 및 시뮬레이션 진행 중...", [])
