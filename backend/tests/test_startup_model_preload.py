"""startup 로컬 Ollama 모델 preload 목록 — 인터프리터 슬롯(9B)만 적재하는 계약.

2026-07-26 모델 슬롯 분리 때 startup preload가 레거시 파서 슬롯(4B)만 적재해 첫
전략 파싱이 9B 로드 지연을 떠안던 버그(07-27 수정) + 4B는 사용 중지라 적재하지
않는다는 사용자 결정(07-27)의 회귀 테스트. 인터프리터 슬롯 미설정 시엔 인터프리터가
실제로 폴백하는 파서 모델을 적재한다.
"""

import main
from main import _local_preload_models


def test_preload_only_interpreter_slot(monkeypatch):
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODEL", "qwen3.5-9b")
    assert _local_preload_models("qwen3.5-4b") == ["qwen3.5-9b"]


def test_preload_falls_back_to_parser_model_without_env(monkeypatch):
    monkeypatch.delenv("STRATEGY_INTERPRETER_MODEL", raising=False)
    assert _local_preload_models("qwen3.5-4b") == ["qwen3.5-4b"]


# ── 로컬 Ollama 미기동 알림 ───────────────────────────────────────────────────
# 2026-08-01: `ollama serve`가 죽은 채 백엔드가 조용히 기동해, 전략 입력이 UNKNOWN으로
# 분류되고 "일반적인 설명을 준비하지 못했습니다" 폴백이 나갔다. 적재·prefill 실패는
# 둘 다 무시되므로 startup 로그에 아무 단서도 남지 않았다.

class _DummyParser:
    ollama_model = "dummy-model"

    def _init_ollama(self):
        pass


def _run_startup(monkeypatch, reachable: bool, kicked: list):
    monkeypatch.setattr("llm_backend.resolve_llm_backend", lambda: "ollama")
    monkeypatch.setattr("engine.nl_parser.NLStrategyParser", lambda backend: _DummyParser())
    monkeypatch.setattr("llm_backend.is_local_ollama", lambda: True)
    monkeypatch.setattr(main, "_local_ollama_reachable", lambda: reachable)
    monkeypatch.setattr(main, "_kick_local_ollama_model_preload", kicked.append)
    monkeypatch.setattr(main, "_kick_system_prompt_prefill", lambda _model: None)
    main.preload_nl_parser()


def test_unreachable_local_ollama_warns_and_skips_preload(monkeypatch, capsys):
    kicked: list = []
    _run_startup(monkeypatch, reachable=False, kicked=kicked)

    out = capsys.readouterr().out
    assert "로컬 Ollama 서버에 닿지 못했습니다" in out
    assert "brew services start ollama" in out
    # 서버가 없으면 적재를 시도해도 실패만 삼킨다 — 건너뛴다.
    assert kicked == []


def test_reachable_local_ollama_preloads_without_warning(monkeypatch, capsys):
    kicked: list = []
    _run_startup(monkeypatch, reachable=True, kicked=kicked)

    assert "닿지 못했습니다" not in capsys.readouterr().out
    assert kicked == _local_preload_models(_DummyParser.ollama_model)
