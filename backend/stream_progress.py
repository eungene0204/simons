from __future__ import annotations


# 백테스트 스트림이 내보내는 진행 문구는 전부 이 파일에 모은다.
#
# 표시 번역은 프론트 t() 소관이라(lib/i18n) 백엔드는 **한국어 정본 템플릿**과 치환 인자만
# 싣는다 — 완성된 문장을 보내면 사전 키가 값마다 달라져 /us에서 번역할 수 없다.
# 자리표시자는 t()와 같은 위치 인자({0}, {1} …)를 쓴다.
#
# 새 문구를 추가하면 lib/i18n/en.ts에도 같은 원문을 키로 넣는다
# (tests/backtest-stream-progress-i18n.test.ts가 이 파일을 스캔해 강제한다).
StatusMessage = tuple[str, list[object]]

LOADING_STOCK_DATA = "종목 데이터 로딩 중..."
APPLYING_FUNDAMENTAL_FILTERS = "재무 필터 적용 중... ({0})"
SIMULATION_RUNNING = "시뮬레이션 실행 중... (최근 {0}년, 각 시점에 상장돼 있던 종목 기준 · 상장폐지 종목 포함)"
AGGREGATING_TRADES = "거래 내역 집계 중..."
CALCULATING_METRICS = "성과 지표 계산 중..."
EVALUATING_CONDITIONS = "전략 조건 계산 및 시뮬레이션 진행 중..."
ANALYSIS_COMPLETE = "분석 완료!"


def simulation_phase_label(period_years: int) -> StatusMessage:
    """시뮬레이션 진행 문구.

    종목 수는 표기하지 않는다 — 요청에 담긴 심볼 목록은 '현재 상장' 종목 수(예: 836)일
    뿐이고, 엔진은 생존편향 제거를 위해 각 시점에 실제로 상장돼 있던 종목(상장폐지분 포함)을
    point-in-time으로 다시 구성해 백테스트한다([project_survivorship_pit_universe]).
    따라서 고정된 현재 종목 수를 보여주면 '현재 상장 종목만 테스트한다'는 오해를 준다.
    정확한 과거 종목 수는 기간·시점마다 달라 단일 숫자로 나타낼 수 없으므로, 숫자 대신
    시점 기준 유니버스를 사용한다는 사실을 알린다."""
    return (SIMULATION_RUNNING, [period_years])


def build_backtest_stream_status(
    wait_count: int, phases: list[StatusMessage]
) -> StatusMessage | None:
    """Return a status update often enough to keep SSE connections alive."""
    ticks_per_message = 10
    if wait_count % ticks_per_message != 0:
        return None

    phase_index = wait_count // ticks_per_message
    if phase_index < len(phases):
        return phases[phase_index]

    return (EVALUATING_CONDITIONS, [])
