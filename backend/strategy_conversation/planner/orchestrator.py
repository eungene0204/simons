"""총괄 에이전트 — 한 턴의 진행(기억 조회·해석·실행 가능성 점검·종료)을 LLM이 고른다.

기존 고정 파이프라인을 통째로 도구 하나(interpret)로 쓴다. 에이전트는 전략을 직접 만들거나
고치지 않고, 사용자에게 보이는 글도 쓰지 않는다 — 무엇을 어떤 순서로 부를지만 정한다.
안전 계약은 전부 결정론이다:

- interpret는 한 턴에 한 번(같은 발화를 두 번 반영하지 않는다)
- check_feasibility는 해석이 끝났고 남은 질문이 없는 전략에만(되묻는 중인 전략은 미완성)
- 점검은 전략을 바꾸지 않는다 — 과거 데이터에서 거래가 0건이면 정해진 사실 문장 하나를
  안내에 더할 뿐이다(규제 안전: 사실만, 행동 제안 없음)
- LLM이 고르는 것은 해석 전 한 번(기억을 먼저 볼지)뿐이다. 해석 뒤의 진행은 결정론이다 —
  점검할 수 있으면 점검하고 끝낸다. 해석 뒤 선택을 LLM에 물으면 점검·종료 둘뿐인 목록에서도
  interpret를 다시 골라 점검이 조용히 빠졌다(2026-11-14~15 Trace 93턴 중 43턴)
- 매 턴 지금 부를 수 있는 액션 목록을 주고 그 밖의 출력은 즉시 종료(스텝 예산
  config.orchestrator_max_steps). 고를 것이 하나뿐이면 LLM을 부르지 않는다
- 어떻게 끝나든 해석을 안 돌렸으면 호출부가 고정 파이프라인을 돌린다(폴백) — 에이전트
  장애가 대화를 깨지 않는다
- 기억은 해석에 쓰인다(2026-11-16): recall 뒤 LLM이 '이번 발화가 가리키는 이전 발화 조각'을
  **그대로 복사해** 내고(resolve_references), 러너가 그 조각이 실제 기록에 있는지 대조한 뒤
  해석 입력에 덧붙인다. LLM이 새 문장을 쓰는 것이 아니라 사용자의 이전 말을 고르는 것이다 —
  기록에 없는 조각은 버린다. 기억 조회는 고칠 전략이 있는 턴에만 연다
- 실행 가능성 점검은 큰 유니버스에서 표본 종목을 먼저 본다(run_feasibility)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from strategy_conversation import config
from strategy_conversation.planner.mini_planner import _extract_json

logger = logging.getLogger("strategy_interpreter.planner")

# 거래 0건 안내 — 사실 한 문장(예측·권유 없음). guard_text 불변은 테스트가 고정한다.
NO_TRADE_NOTICE = "과거 데이터 기준으로 이 조건에서는 백테스트 기간 동안 거래가 한 번도 발생하지 않았습니다."

_SYSTEM = """당신은 주식 백테스트 플랫폼에서 전략 대화 한 턴의 진행을 맡은 에이전트입니다.
전략을 직접 만들거나 고치지 않고, 사용자에게 보일 글도 쓰지 않습니다. 도구를 골라 부르기만 합니다.

매 턴 JSON 객체 하나만 출력하세요:
- {"action":"recall"} — 이 대화의 이전 턴 기록(발화·질문·점검 결과)을 조회합니다
- {"action":"interpret"} — 이번 발화를 전략에 반영합니다

규칙:
1. 이번 발화는 interpret로 반영해야 합니다.
2. 발화가 이전 대화를 가리키면(예: 아까, 다시, 그대로) interpret 전에 recall로 기록을 확인하세요.
3. action은 입력의 available_actions 안에서만 고르세요.

해석 뒤의 실행 가능성 점검과 종료는 시스템이 맡습니다."""

def _render_state(utterance: str, has_strategy: bool, pending_question: Optional[str],
                  steps: List[Dict[str, Any]], available: List[str]) -> str:
    return json.dumps({
        "utterance": utterance,
        "has_strategy": has_strategy,
        "pending_question": pending_question,
        "steps": steps,
        "available_actions": available,
    }, ensure_ascii=False)


_RESOLVE_SYSTEM = """당신은 주식 백테스트 플랫폼의 대화 기록 조회 담당입니다. 사용자의 이번 발화가 이전 턴에
자신이 한 말을 가리키면(예: 아까 말한 조건, 처음에 말한 대로, 그때 그 값) 가리킨 내용을 이전 발화에서
**글자 그대로 복사한 조각**으로 적습니다.

JSON 객체 하나만 출력하세요: {"quotes": ["<이전 발화에서 그대로 복사한 조각>"]}

규칙:
1. 조각은 turns의 utterance에 있는 글자 그대로여야 합니다. 요약하거나 고쳐 쓰지 마세요.
2. 가리킨 부분만 짧게 적으세요(조각마다 80자 이내, 최대 3개).
3. 이번 발화에 이미 적힌 내용은 적지 마세요. 가리키는 이전 말이 없으면 {"quotes": []} 입니다."""
_QUOTE_MAX_CHARS = 80
_QUOTE_MAX_COUNT = 3


def _compact(text: Any) -> str:
    return "".join(str(text or "").split())


def resolve_references(utterance: str, turns: List[Dict[str, Any]],
                       chat_fn: Callable[..., str]) -> List[str]:
    """이번 발화가 가리키는 이전 발화 조각(기록에 실재하는 것만). 없거나 실패하면 빈 목록."""
    past = [str(t.get("utterance") or "") for t in turns if t.get("utterance")]
    if not past:
        return []
    try:
        decision = _extract_json(chat_fn(_RESOLVE_SYSTEM, json.dumps({
            "utterance": utterance,
            "turns": [{"turn": i + 1, "utterance": text} for i, text in enumerate(past)],
        }, ensure_ascii=False), max_tokens=256))
    except Exception:  # noqa: BLE001 — 기억 해소 실패는 기억 없이 해석하는 것과 같다
        logger.warning("orchestrator 기억 해소 실패 — 기억 없이 해석", exc_info=True)
        return []
    quotes = decision.get("quotes") if isinstance(decision, dict) else None
    if not isinstance(quotes, list):
        return []
    current, haystacks = _compact(utterance), [_compact(text) for text in past]
    kept: List[str] = []
    for quote in quotes:
        compact = _compact(quote) if isinstance(quote, str) else ""
        if (compact and len(quote) <= _QUOTE_MAX_CHARS and compact not in current
                and any(compact in hay for hay in haystacks) and quote.strip() not in kept):
            kept.append(quote.strip())
    return kept[:_QUOTE_MAX_COUNT]


def _available(called: set, result: Optional[Dict[str, Any]], can_recall: bool = True) -> List[str]:
    """지금 부를 수 있는 액션 — 규칙 문장보다 목록이 잘 지켜진다(해석 뒤 interpret 반복 3/3 실측).

    해석 뒤에는 항상 하나다(점검할 수 있으면 점검, 아니면 종료) — LLM에 묻지 않는다."""
    if result is None:
        return [a for a in ("recall", "interpret")
                if a not in called and (a != "recall" or can_recall)]
    if "check_feasibility" not in called and feasibility_blocker(result) is None:
        return ["check_feasibility"]
    return ["finish"]


def _interpret_observation(result: Dict[str, Any]) -> Dict[str, Any]:
    """해석 결과에서 진행 판단에 필요한 구조 필드만 — 전략 본문은 싣지 않는다."""
    return {
        "question": result.get("clarification_question"),
        "priority": result.get("clarification_priority"),
        "notices": len(result.get("notices") or []),
        "symbol_count": result.get("symbol_count"),
    }


def feasibility_blocker(result: Optional[Dict[str, Any]]) -> Optional[str]:
    """점검할 수 없는 이유(없으면 None) — 미완성 전략을 백테스트하지 않는다."""
    if result is None:
        return "interpret를 먼저 부르세요"
    if result.get("clarification_question"):
        return "남은 질문이 있는 전략은 점검하지 않습니다"
    if not result.get("backtest_request") or not result.get("symbol_count"):
        return "실행할 전략이 없습니다"
    return None


def orchestrate(
    utterance: str, *, has_strategy: bool, pending_question: Optional[str],
    chat_fn: Callable[..., str],
    interpret: Callable[..., Dict[str, Any]],
    recall: Callable[[], List[Dict[str, Any]]],
    check_feasibility: Callable[[Dict[str, Any]], Dict[str, Any]],
    max_steps: Optional[int] = None, can_recall: Optional[bool] = None,
) -> Dict[str, Any]:
    """한 턴을 진행한다. 반환: {"result": 해석 결과|None, "feasibility": 점검 결과|None}.

    can_recall: 기억 조회를 열지(기본: 고칠 전략이 있을 때). 닫으면 LLM을 부르지 않는다.
    interpret는 기억에서 해소한 이전 발화 조각이 있으면 그것을 인자로 받는다.

    result가 None이면 해석을 돌리지 못한 것이다 — 호출부가 고정 파이프라인으로 폴백한다.
    interpret 도구가 던진 예외(LLM 연결 장애·취소 등)는 고정 파이프라인과 같게 그대로 올린다.
    """
    from observability import span

    budget = max_steps if max_steps is not None else config.orchestrator_max_steps()
    steps: List[Dict[str, Any]] = []
    called: set = set()
    result: Optional[Dict[str, Any]] = None
    feasibility: Optional[Dict[str, Any]] = None
    recalled_quotes: List[str] = []
    if can_recall is None:
        can_recall = has_strategy
    outcome = "budget_exhausted"
    with span("Agent · 총괄", "planner", inputs={"utterance": utterance}) as trace:
        for _ in range(budget):
            available = _available(called, result, can_recall)
            if len(available) == 1:
                # 고를 것이 하나뿐이면 LLM을 부르지 않는다(recall 뒤 recall 반복 실측).
                action = available[0]
            else:
                try:
                    decision = _extract_json(chat_fn(
                        _SYSTEM,
                        _render_state(utterance, has_strategy, pending_question, steps, available),
                        max_tokens=64))
                except Exception:  # noqa: BLE001 — 진행자 LLM 장애는 폴백이지 턴 실패가 아니다
                    logger.warning("orchestrator LLM 호출 실패 — 고정 진행으로", exc_info=True)
                    outcome = "error"
                    break
                action = decision.get("action") if decision else None
            if action == "finish" and result is not None:
                outcome = "finish"
                break
            if action not in available:
                outcome = "contract_violation"
                break
            called.add(action)
            if action == "recall":
                turns = recall()
                recalled_quotes = resolve_references(utterance, turns, chat_fn)
                observation: Any = {"turns": [
                    {"utterance": t.get("utterance"), "question": t.get("question"),
                     "feasibility": t.get("feasibility")} for t in turns],
                    "resolved": len(recalled_quotes)}
            elif action == "interpret":
                result = interpret(recalled_quotes) if recalled_quotes else interpret()
                observation = _interpret_observation(result)
            else:
                blocker = feasibility_blocker(result)
                if blocker:
                    observation = {"rejected": blocker}
                else:
                    feasibility = check_feasibility(result)
                    observation = feasibility
            steps.append({"action": action, "observation": observation})
        # 조회한 과거 발화 전체는 Trace에 다시 적지 않는다 — 원문 보관 기한(3일)이 새로 시작된다.
        # 해석에 쓰인 조각(resolved)만 호출부가 해석 입력에 실어 그 턴 Trace에 남는다.
        trace.output(outcome=outcome, interpreted=result is not None, feasibility=feasibility,
                     steps=[{"action": s["action"], "observation": (
                         {"turns": len(s["observation"]["turns"]),
                          "resolved": s["observation"]["resolved"]} if s["action"] == "recall"
                         else s["observation"])} for s in steps])
    return {"result": result, "feasibility": feasibility}


# 이보다 큰 유니버스는 표본 종목을 먼저 본다 — 전 종목(약 2,600) 점검은 종목 수에 비례해 60초를
# 넘겨 '점검 못 함'으로 끝났다(2026-11-16 실측 10턴 중 6턴, 기간을 줄여도 같음). 표본 300종목은 약 8초.
FEASIBILITY_SAMPLE_OVER = 600
FEASIBILITY_SAMPLE_SIZE = 300


def _sample_request(backtest_request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """큰 유니버스의 표본 점검 요청(고르게 건너뛰며 뽑는다). 작으면 None."""
    symbols = backtest_request.get("symbols") or []
    if len(symbols) <= FEASIBILITY_SAMPLE_OVER:
        return None
    step = len(symbols) / FEASIBILITY_SAMPLE_SIZE
    # universe_id가 있으면 엔진이 종목 목록 대신 유니버스 전체를 다시 편다 — 표본은 목록으로만 돈다.
    return {**backtest_request, "universe_id": None,
            "symbols": [symbols[int(i * step)] for i in range(FEASIBILITY_SAMPLE_SIZE)]}


def run_feasibility(backtest_request: Dict[str, Any], run_backtest: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    """전략을 과거 데이터에 실제로 돌려 거래 수를 센다. 실패는 '점검 못 함'이다(판정 없음).

    큰 유니버스는 표본에서 거래가 나오면 거기서 끝낸다(거래가 있다는 것만 확인하면 된다).
    표본이 0건이거나 표본 실행이 실패하면 전체를 돈다 — '거래 0건' 안내는 전체 결과로만 낸다.
    """
    sample = _sample_request(backtest_request)
    if sample is not None:
        try:
            sampled = int(run_backtest(sample).get("trades") or 0)
        except Exception as exc:  # noqa: BLE001 — 표본 실패는 전체 점검으로 넘어간다
            logger.warning("실행 가능성 표본 점검 실패 — 전체로 | err=%s", str(exc)[:200])
            sampled = 0
        if sampled > 0:
            return {"checked": True, "trades": sampled, "sampled": True}
    try:
        outcome = run_backtest(backtest_request)
        return {"checked": True, "trades": int(outcome.get("trades") or 0)}
    except Exception as exc:  # noqa: BLE001 — 점검은 부가 기능이다
        logger.warning("실행 가능성 점검 실패 — 판정 없음 | err=%s", str(exc)[:200])
        return {"checked": False}


def feasibility_notice(feasibility: Optional[Dict[str, Any]]) -> Optional[str]:
    """점검 결과가 사용자에게 알릴 사실이면 그 문장(없으면 None)."""
    if feasibility and feasibility.get("checked") and feasibility.get("trades") == 0:
        return NO_TRADE_NOTICE
    return None
