"""LLM 재시도 진행 표시 채널(llm_progress) — '재확인 중...' 단계의 결속·복귀 계약."""

from __future__ import annotations

import llm_progress


def test_retrying_is_noop_without_bound_holder():
    with llm_progress.retrying():
        pass  # 예외 없이 지나간다(비스트리밍 라우트·스크립트)


def test_retrying_sets_stage_and_restores_previous_on_exit():
    holder = {"stage": "universe"}
    with llm_progress.bind(holder):
        with llm_progress.retrying():
            assert holder["stage"] == "retrying"
        assert holder["stage"] == "universe"


def test_retrying_restores_previous_stage_on_exception():
    holder = {"stage": "thinking"}
    with llm_progress.bind(holder):
        try:
            with llm_progress.retrying():
                raise RuntimeError("boom")
        except RuntimeError:
            pass
    assert holder["stage"] == "thinking"


def test_nested_retrying_restores_once_at_outer_exit():
    holder = {"stage": "entry"}
    with llm_progress.bind(holder):
        with llm_progress.retrying():
            with llm_progress.retrying():
                assert holder["stage"] == "retrying"
            assert holder["stage"] == "retrying"  # 안쪽이 먼저 되돌리지 않는다
        assert holder["stage"] == "entry"


def test_bind_is_scoped_to_context():
    holder = {"stage": "parsing"}
    with llm_progress.bind(holder):
        pass
    with llm_progress.retrying():
        assert holder["stage"] == "parsing"  # bind를 벗어나면 holder를 건드리지 않는다
