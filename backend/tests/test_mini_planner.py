"""Mini-Planner(Phase 3) 계약 — 동적 도구 계획의 결정론 안전 장치.

핵심: 화이트리스트·스텝 예산·루프 차단·근거 없는 finish 거부(관찰값만 채택)·
되묻기 질문 출력 관문 통과. 실패는 전부 None(고정 파이프라인 폴백 신호).
"""

import json

import engine.knowledge_graph as kg
import engine.term_grounding as tg
from strategy_conversation.planner.mini_planner import plan_universe_resolution
from strategy_conversation.planner.shadow import maybe_shadow_plan


class ScriptedChat:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, system_prompt, user_message):
        self.calls += 1
        return self.responses.pop(0) if self.responses else ""


def _tool(name, text="미지테마"):
    return json.dumps({"action": "tool", "tool": name, "args": {"text": text}})


_FINISH = json.dumps({"action": "finish"})


# ── 정상 경로 ─────────────────────────────────────────────────────────────────

def test_kg_hit_then_finish(monkeypatch):
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "반도체")
    chat = ScriptedChat([_tool("kg_resolve_sector"), _FINISH])
    result = plan_universe_resolution("미지테마", chat)
    assert result is not None and result.outcome == "resolved"
    assert result.sector == "반도체"
    assert [s.tool for s in result.steps] == ["kg_resolve_sector"]


def test_theme_companies_adopted_from_observation(monkeypatch):
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: None)
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: {
        "term": "미지테마", "companies": [{"symbol": "005930", "name": "삼성전자"}],
        "first_known_date": None,
    })
    chat = ScriptedChat([
        _tool("kg_resolve_sector"), _tool("kg_theme_companies"), _FINISH,
    ])
    result = plan_universe_resolution("미지테마", chat)
    assert result is not None and result.outcome == "resolved"
    assert result.sector is None
    assert result.companies[0]["symbol"] == "005930"


def test_ground_term_receives_planner_chat(monkeypatch):
    captured = {}

    def fake_resolve_sector(text, chat, **kwargs):
        captured["chat"] = chat
        return "에너지/원자력"

    monkeypatch.setattr(tg, "resolve_sector", fake_resolve_sector)
    chat = ScriptedChat([_tool("ground_term"), _FINISH])
    result = plan_universe_resolution("SMR", chat)
    assert result is not None and result.sector == "에너지/원자력"
    assert captured["chat"] is chat  # 검색 그라운딩 LLM은 planner와 같은 chat 공유


def test_clarify_decision_passes_guard(monkeypatch):
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: None)
    chat = ScriptedChat([
        _tool("kg_resolve_sector"),
        json.dumps({"action": "clarify",
                    "question": "어떤 업종의 전략을 만들까요?"}),
    ])
    result = plan_universe_resolution("미지테마", chat)
    assert result is not None and result.outcome == "clarify"
    assert result.question == "어떤 업종의 전략을 만들까요?"


# ── 결정론 안전 장치(전부 None 폴백) ─────────────────────────────────────────

def test_finish_without_observed_evidence_fails():
    assert plan_universe_resolution("미지테마", ScriptedChat([_FINISH])) is None


def test_clarify_with_forbidden_phrase_fails(monkeypatch):
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: None)
    chat = ScriptedChat([
        _tool("kg_resolve_sector"),
        json.dumps({"action": "clarify", "question": "반도체 전략 사용을 권장합니다."}),
    ])
    assert plan_universe_resolution("미지테마", chat) is None


def test_non_whitelisted_tool_rejected():
    chat = ScriptedChat([_tool("compile_strategy")])
    assert plan_universe_resolution("미지테마", chat) is None


def test_duplicate_call_loop_rejected(monkeypatch):
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: None)
    chat = ScriptedChat([_tool("kg_resolve_sector"), _tool("kg_resolve_sector")])
    assert plan_universe_resolution("미지테마", chat) is None


def test_step_budget_exhausted(monkeypatch):
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: None)
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    chat = ScriptedChat([_tool("kg_resolve_sector"), _tool("kg_theme_companies")])
    assert plan_universe_resolution("미지테마", chat, max_steps=2) is None


def test_invalid_json_fails():
    assert plan_universe_resolution("미지테마", ScriptedChat(["글쎄요, 잘 모르겠네요"])) is None


def test_blank_term_fails():
    assert plan_universe_resolution("  ", ScriptedChat([_FINISH])) is None


# ── Shadow 모드 ───────────────────────────────────────────────────────────────

def test_shadow_off_is_noop(monkeypatch):
    monkeypatch.delenv("STRATEGY_PLANNER_MODE", raising=False)
    assert maybe_shadow_plan(["미지테마"]) is None


def test_shadow_runs_and_logs(monkeypatch, tmp_path):
    log_path = tmp_path / "planner_shadow.jsonl"
    monkeypatch.setenv("STRATEGY_PLANNER_MODE", "shadow")
    monkeypatch.setenv("STRATEGY_PLANNER_SHADOW_LOG", str(log_path))
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "반도체")
    chat = ScriptedChat([_tool("kg_resolve_sector"), _FINISH])

    thread = maybe_shadow_plan(["미지테마"], chat_fn=chat)
    assert thread is not None
    thread.join(timeout=10)

    record = json.loads(log_path.read_text().strip())
    assert record["term"] == "미지테마"
    assert record["outcome"] == "resolved"
    assert record["sector"] == "반도체"
    assert record["error"] is None
    assert "baseline_sector" in record and "latency_ms" in record
