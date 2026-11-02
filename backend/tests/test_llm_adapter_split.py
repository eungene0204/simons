"""LLM 어댑터 분리 계약 — 구조화 출력은 greedy, 산문만 샘플링.

종전에는 어댑터 하나가 `temperature=0.3`으로 둘 다 처리했다. 0.3은 산문(코치 문장)에
맞춘 값인데 분류가 같은 어댑터를 쓰면서 딸려온 것이지 분류를 위해 고른 값이 아니었다.

실측(2026-08-11): 같은 입력 '코스닥 상장사 수가 몇 개야?'가 5회 중
GENERAL_INVESTMENT↔UNKNOWN으로 갈렸고, greedy로 바꾸자 5/5 고정됐다. 라벨이 흔들리면
같은 질문에 다른 답이 나가고, QA 하니스가 flaky해져 회귀를 놓친다.

여기서 고정하는 것은 **어느 호출부가 어느 어댑터를 쓰는가**다. 다시 하나로 합쳐지면
증상이 조용히 돌아오므로(값이 아니라 배선의 문제였다) 배선을 테스트로 못박는다.
"""

from __future__ import annotations

import pytest

from api import intent_routes


class _Recorder:
    """parser.chat 호출 인자를 기록하는 스텁."""

    def __init__(self, reply: str = '{"intent": "GENERAL_INVESTMENT"}'):
        self.calls: list[dict] = []
        self._reply = reply

    def chat(self, system_prompt, user_msg, *, max_tokens, temperature, top_p):
        self.calls.append({"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens})
        return self._reply


class _Lock:
    def priority(self, _level):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    stub = type("Main", (), {"_active_nl_parser": staticmethod(lambda: rec),
                             "_mlx_inference_lock": _Lock()})
    monkeypatch.setattr(intent_routes, "_main_module", lambda: stub)
    return rec


def test_structured_adapter_is_greedy(recorder):
    """구조화 출력은 온도를 주지 않는다 — 정답 고르기에 표현 변주는 해가 된다."""
    intent_routes._mlx_llm_structured("sys", "user", max_tokens=220)

    assert recorder.calls == [{"temperature": 0.0, "top_p": 1.0, "max_tokens": 220}]


def test_prose_adapter_still_samples(recorder):
    """산문 답변은 종전대로 샘플링한다 — 매번 같은 문장이면 어색하다."""
    intent_routes._mlx_llm_prose("sys", "user", max_tokens=300)

    assert recorder.calls == [{"temperature": 0.3, "top_p": 0.9, "max_tokens": 300}]


def test_classification_uses_the_structured_adapter(recorder, monkeypatch):
    """분류가 산문 어댑터로 되돌아가면 라벨이 다시 흔들린다."""
    import asyncio

    from intent.schemas import IntentRequest

    monkeypatch.setattr(intent_routes, "_llm_available", lambda: True)
    asyncio.run(intent_routes.classify_query(IntentRequest(query="코스닥 상장사 수가 몇 개야?")))

    assert recorder.calls, "분류가 LLM을 부르지 않았다"
    assert all(call["temperature"] == 0.0 for call in recorder.calls)


def test_general_answer_uses_the_prose_adapter(recorder, monkeypatch):
    """일반 지식 답변은 산문 쪽이어야 한다(구조화로 넘기면 표현이 굳는다)."""
    monkeypatch.setattr(intent_routes, "_llm_available", lambda: True)
    monkeypatch.setattr(intent_routes.platform_defaults, "reply", lambda q: None)
    # 용어 추출(구조화)은 따로 막아 답변 생성 호출만 남긴다.
    from intent import glossary_facts
    monkeypatch.setattr(glossary_facts, "extract_terms", lambda *a, **k: [])
    monkeypatch.setattr(
        intent_routes, "_mlx_llm_structured", lambda *a, **k: pytest.fail("추출은 이 테스트 대상이 아니다")
    )
    recorder._reply = "PBR은 주가순자산비율입니다."

    intent_routes.generate_general_answer("PBR이 뭐야?", caller_facts="총 수익률: +10.0%")

    assert recorder.calls
    assert recorder.calls[-1]["temperature"] == 0.3


def test_chat_failure_is_reported_on_console_not_swallowed(monkeypatch, caplog):
    """LLM 호출 예외는 빈 응답으로 보고하되 원인을 WARNING으로 남긴다 — debug로만 남기면
    basicConfig 없는 앱에서 버려져, OpenRouter 상류 502가 분류 트레이스에 '구조화 출력
    해석 실패'로만 보였다(2026-09-08)."""
    import logging

    class _Boom:
        def chat(self, *a, **k):
            raise RuntimeError("openrouter error 502: Upstream error from Nvidia: Service temporarily overloaded")

    stub = type("Main", (), {"_active_nl_parser": staticmethod(lambda: _Boom()),
                             "_mlx_inference_lock": _Lock()})
    monkeypatch.setattr(intent_routes, "_main_module", lambda: stub)
    with caplog.at_level(logging.WARNING, logger=intent_routes.logger.name):
        assert intent_routes._mlx_llm_structured("sys", "user", max_tokens=220) == ""
    assert any("openrouter error 502" in r.getMessage() and r.levelno == logging.WARNING
               for r in caplog.records)


def test_classify_adapter_is_greedy_with_short_openrouter_attempt_cap(monkeypatch):
    """의도 분류는 greedy + OpenRouter 시도 상한을 건다 — 상류 무응답 ~120초를 그대로 기다리면
    폴백까지 135초가 걸려 프록시(120초)가 먼저 끊었다(2026-10-31)."""
    import llm_backend

    seen = []

    class _Rec:
        def chat(self, system_prompt, user_msg, *, max_tokens, temperature, top_p):
            seen.append((temperature, top_p, max_tokens, llm_backend.openrouter_attempt_timeout_s()))
            return "{}"

    stub = type("Main", (), {"_active_nl_parser": staticmethod(lambda: _Rec()),
                             "_mlx_inference_lock": _Lock()})
    monkeypatch.setattr(intent_routes, "_main_module", lambda: stub)
    intent_routes._classify_llm("sys", "user")
    assert seen == [(0.0, 1.0, 400, intent_routes._CLASSIFY_OPENROUTER_ATTEMPT_TIMEOUT_S)]
    assert llm_backend.openrouter_attempt_timeout_s() is None


def test_classify_llm_failure_is_503_not_interpretation_failure(monkeypatch):
    """분류 LLM 호출 실패는 해석 실패(UNKNOWN)가 아니라 503이다 — 해석 실패로 돌려주면 화면이
    "조금 다르게 표현해 주세요"로 사용자 탓을 했다(2026-10-31)."""
    import asyncio

    from fastapi import HTTPException

    from intent.schemas import IntentRequest

    class _Boom:
        def chat(self, *a, **k):
            raise RuntimeError("openrouter 상류 일시 오류 408")

    stub = type("Main", (), {"_active_nl_parser": staticmethod(lambda: _Boom()),
                             "_mlx_inference_lock": _Lock()})
    monkeypatch.setattr(intent_routes, "_main_module", lambda: stub)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(intent_routes.classify_query(IntentRequest(query="KOSPI 5거래일 연속 상승 매수")))
    assert exc.value.status_code == 503
