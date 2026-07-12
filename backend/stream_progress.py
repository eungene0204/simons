from __future__ import annotations


def simulation_phase_label(period_years: int) -> str:
    """시뮬레이션 진행 문구.

    종목 수는 표기하지 않는다 — 요청에 담긴 심볼 목록은 '현재 상장' 종목 수(예: 836)일
    뿐이고, 엔진은 생존편향 제거를 위해 각 시점에 실제로 상장돼 있던 종목(상장폐지분 포함)을
    point-in-time으로 다시 구성해 백테스트한다([project_survivorship_pit_universe]).
    따라서 고정된 현재 종목 수를 보여주면 '현재 상장 종목만 테스트한다'는 오해를 준다.
    정확한 과거 종목 수는 기간·시점마다 달라 단일 숫자로 나타낼 수 없으므로, 숫자 대신
    시점 기준 유니버스를 사용한다는 사실을 알린다."""
    return (
        f"시뮬레이션 실행 중... (최근 {period_years}년, 각 시점에 상장돼 있던 종목 기준 "
        "· 상장폐지 종목 포함)"
    )


def build_backtest_stream_status(wait_count: int, phases: list[str]) -> str | None:
    """Return a status update often enough to keep SSE connections alive."""
    ticks_per_message = 10
    if wait_count % ticks_per_message != 0:
        return None

    phase_index = wait_count // ticks_per_message
    if phase_index < len(phases):
        return phases[phase_index]

    return "전략 조건 계산 및 시뮬레이션 진행 중..."
