"""startup 로컬 Ollama 모델 preload 목록 — 인터프리터 슬롯(9B)만 적재하는 계약.

2026-07-26 모델 슬롯 분리 때 startup preload가 레거시 파서 슬롯(4B)만 적재해 첫
전략 파싱이 9B 로드 지연을 떠안던 버그(07-27 수정) + 4B는 사용 중지라 적재하지
않는다는 사용자 결정(07-27)의 회귀 테스트. 인터프리터 슬롯 미설정 시엔 인터프리터가
실제로 폴백하는 파서 모델을 적재한다.
"""

from main import _local_preload_models


def test_preload_only_interpreter_slot(monkeypatch):
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODEL", "qwen3.5-9b")
    assert _local_preload_models("qwen3.5-4b") == ["qwen3.5-9b"]


def test_preload_falls_back_to_parser_model_without_env(monkeypatch):
    monkeypatch.delenv("STRATEGY_INTERPRETER_MODEL", raising=False)
    assert _local_preload_models("qwen3.5-4b") == ["qwen3.5-4b"]
