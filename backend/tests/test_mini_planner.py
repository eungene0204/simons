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

def _kg_miss(monkeypatch):
    """사전 관찰(KG 조회 2종)이 전부 미스인 상태 — LLM 결정 루프로 진입한다."""
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: None)
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)


def test_kg_hit_resolves_without_llm(monkeypatch):
    """사전 관찰이 섹터를 주면 LLM 턴 없이 결정적으로 종료한다."""
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "반도체")
    chat = ScriptedChat([])
    result = plan_universe_resolution("미지테마", chat)
    assert result is not None and result.outcome == "resolved"
    assert result.sector == "반도체"
    assert [s.tool for s in result.steps] == ["kg_resolve_sector"]
    assert chat.calls == 0


def test_theme_companies_adopted_from_observation(monkeypatch):
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: None)
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: {
        "term": "미지테마", "companies": [{"symbol": "005930", "name": "삼성전자"}],
        "first_known_date": None,
    })
    chat = ScriptedChat([])
    result = plan_universe_resolution("미지테마", chat)
    assert result is not None and result.outcome == "resolved"
    assert result.sector is None
    assert result.companies[0]["symbol"] == "005930"
    assert chat.calls == 0


def test_tool_name_in_action_field_normalized(monkeypatch):
    """도구명을 action에 쓴 LLM 출력({"action": "ground_term"})은 형식 정규화로
    tool 액션으로 복구한다 — 의미가 명백한 표기 변형은 결정론 보정 대상(계약 § 판정 기준)."""
    _kg_miss(monkeypatch)
    monkeypatch.setattr(tg, "resolve_sector", lambda text, chat, **kw: "화학")
    chat = ScriptedChat([
        json.dumps({"action": "ground_term", "args": {"text": "미지테마"}}),
    ])
    result = plan_universe_resolution("미지테마", chat)
    assert result is not None and result.outcome == "resolved"
    assert result.sector == "화학"


def test_ground_term_receives_planner_chat(monkeypatch):
    _kg_miss(monkeypatch)
    captured = {}

    def fake_resolve_sector(text, chat, **kwargs):
        captured["chat"] = chat
        return "에너지/원자력"

    monkeypatch.setattr(tg, "resolve_sector", fake_resolve_sector)
    chat = ScriptedChat([_tool("ground_term", "SMR")])
    result = plan_universe_resolution("SMR", chat)
    assert result is not None and result.sector == "에너지/원자력"
    assert captured["chat"] is chat  # 검색 그라운딩 LLM은 planner와 같은 chat 공유


def test_clarify_decision_passes_guard(monkeypatch):
    _kg_miss(monkeypatch)
    chat = ScriptedChat([
        json.dumps({"action": "clarify",
                    "question": "어떤 업종의 전략을 만들까요?"}),
    ])
    result = plan_universe_resolution("미지테마", chat)
    assert result is not None and result.outcome == "clarify"
    assert result.question == "어떤 업종의 전략을 만들까요?"


# ── 결정론 안전 장치(전부 None 폴백) ─────────────────────────────────────────

def test_finish_without_observed_evidence_fails(monkeypatch):
    _kg_miss(monkeypatch)
    assert plan_universe_resolution("미지테마", ScriptedChat([_FINISH])) is None


def test_clarify_with_forbidden_phrase_fails(monkeypatch):
    _kg_miss(monkeypatch)
    chat = ScriptedChat([
        json.dumps({"action": "clarify", "question": "반도체 전략 사용을 권장합니다."}),
    ])
    assert plan_universe_resolution("미지테마", chat) is None


def test_non_whitelisted_tool_rejected(monkeypatch):
    _kg_miss(monkeypatch)
    chat = ScriptedChat([_tool("compile_strategy")])
    assert plan_universe_resolution("미지테마", chat) is None


def test_duplicate_of_seeded_call_rejected(monkeypatch):
    """사전 관찰로 이미 실행된 KG 조회를 LLM이 다시 부르면 루프로 차단한다."""
    _kg_miss(monkeypatch)
    chat = ScriptedChat([_tool("kg_resolve_sector")])
    assert plan_universe_resolution("미지테마", chat) is None


def test_theme_requery_after_ground_learning_deterministic(monkeypatch):
    """검색 학습 성공 후 테마 재조회·종료는 LLM 턴 없는 결정론 절차다 — 학습이 만든
    테마 앵커의 상장사를 확보한다(고정 체인의 학습→apply_theme_companies 재시도 계약)."""
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: None)
    theme_hits = iter([None, {
        "term": "미지테마", "companies": [{"symbol": "005930", "name": "삼성전자"}],
        "first_known_date": None,
    }])
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: next(theme_hits))
    monkeypatch.setattr(tg, "resolve_sector", lambda text, chat, **kw: "반도체")
    chat = ScriptedChat([_tool("ground_term")])
    result = plan_universe_resolution("미지테마", chat)
    assert result is not None and result.outcome == "resolved"
    assert result.sector == "반도체"
    assert result.companies[0]["symbol"] == "005930"
    assert chat.calls == 1  # 검색 결정 1턴만 — 재조회·finish는 LLM 턴을 쓰지 않는다


def test_step_budget_exhausted(monkeypatch):
    _kg_miss(monkeypatch)
    monkeypatch.setattr(tg, "resolve_sector", lambda text, chat, **kw: None)
    chat = ScriptedChat([_tool("ground_term", "표현A"), _tool("ground_term", "표현B")])
    assert plan_universe_resolution("미지테마", chat, max_steps=2) is None


def test_invalid_json_fails(monkeypatch):
    _kg_miss(monkeypatch)
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
