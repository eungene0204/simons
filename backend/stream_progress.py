from __future__ import annotations


def build_backtest_stream_status(wait_count: int, phases: list[str], poll_interval: float = 0.2) -> str | None:
    """Return a status update often enough to keep SSE connections alive."""
    ticks_per_message = 10
    if wait_count % ticks_per_message != 0:
        return None

    phase_index = wait_count // ticks_per_message
    if phase_index < len(phases):
        return phases[phase_index]

    elapsed_seconds = int(wait_count * poll_interval)
    return f"전략 조건 계산 및 시뮬레이션 진행 중... ({elapsed_seconds}초 경과)"
