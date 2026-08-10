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
    # 용어 추출(구조화)은 타지 않게 해 답변 생성 호출만 남긴다.
    monkeypatch.setattr(
        intent_routes, "_mlx_llm_structured", lambda *a, **k: pytest.fail("추출은 이 테스트 대상이 아니다")
    )
    recorder._reply = "PBR은 주가순자산비율입니다."

    intent_routes.generate_general_answer("PBR이 뭐야?", caller_facts="총 수익률: +10.0%")

    assert recorder.calls
    assert recorder.calls[-1]["temperature"] == 0.3
