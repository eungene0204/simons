"""적립식 전용 판정(통합) — 적립 계획·조건별 매수 금액·현금 관리 규칙을 **한 번에** LLM에게 묻는다.

왜 통합했는가(2026-09-22): 적립식 해석은 일반 매매 전략 파이프라인 위에 별도 판정 넷(계획 회수·현금 풀·
조건부 금액·지표 어긋남 재생성)을 덧댄 구조였고, 판정끼리 **순서·항목 수·다른 결정론 보정**에 얽혀
하나가 흔들리면 전체가 "매수·매도 조건이 있는 적립식은 미지원"으로 무너졌다. 같은 문장에서 하루 사이
네 번 다른 자리가 깨졌다:
  - 1차가 계획을 비움 → 적립 판정이 전부 건너뜀(발동 조건이 계획 존재)
  - 금액 판정이 항목을 **순서**로 대조 → 120B가 문장 순서대로 3개를 내면(1개 요청) 항목 수 불일치로 판정 없음
  - 재생성본이 "아래에 있으면"을 crosses_below로 냄 → 일반 전략용 보정이 매도 선언으로 보고 청산 칸으로 이동
이 모듈은 그 넷을 한 호출로 합치고, 대조를 순서가 아니라 **인용 문자열**로 한다(LLM 출력끼리의 표기
포함 대조 — 여분 항목은 무시, 빠진 항목은 꼬리표 없음). 실패는 1회 재시도 뒤 판정 없음(fail-open).

호출 범위: 1차 해석이 적립 계획을 냈거나, 계획은 비었지만 자리를 못 찾은 말의 흔적(미지원 보고·거래대금
조건)이 남은 생성 턴. 그 밖의 턴은 호출이 없다. 수정 턴은 추가된 조건에 한해(only) 같은 판정을 받는다.

결정론 코드의 몫: ① 인용 출처 대조(계획 인용·금액 표기는 입력에 그대로 있어야 한다 — 새 칸을 만드는
회수라 느슨한 조각 대조를 쓰지 않는다) ② 금액 표기 환산(models._normalize_amount) ③ enum 소속 확인
④ 조건에 꼬리표 달기·상태 enum→비교 연산자(비교 연산자가 없는 자리만) ⑤ 같은 인용을 담은 미지원
보고·지어낸 거래대금 조건 걷기.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MODES = frozenset({"set", "add"})
PERIODS = frozenset({"weekly", "monthly", "bimonthly", "quarterly", "yearly"})
# 상태 enum → 비교 연산자. 납입액 규칙은 납입일 하루의 **상태**를 보는데 120B는 "200일선 아래에 있으면"을
# 교차 사건(crosses_below)으로 옮기기도 한다 — 사건 연산자는 규칙이 될 수 없다. 상태인지는 LLM이 답한다.
STATE_OPERATORS = {"below": "<", "above": ">"}
EVENT_OPERATORS = frozenset({"crosses_above", "crosses_below"})
_TRADING_VALUE_FACTOR = "fundamental.trading_value"

_SYSTEM = """당신은 **대조기**입니다. 사용자는 정기적으로 종목을 사 모으는 적립식 전략을 말했습니다. 전략 문장을 읽고 아래 네 가지를 **옮겨 적기만** 하세요(판단·계산·지어내기 금지).

plan — 일정한 주기마다 정해진 금액만큼 사는 기본 계획.
  quote: 그 말을 한 부분을 문장에서 그대로 옮긴 조각. amount: 회차 납입액을 말한 표기 그대로("100만 원"). period: weekly|monthly|bimonthly|quarterly|yearly. 없으면 셋 다 null.
rules — [조건] 목록의 조건마다 하나씩, 그 조건이 성립할 때 **얼마를 살지** 사용자가 말했는지.
  quote: [조건]에 적힌 조각을 **그대로** 복사. amount: 말한 표기 그대로, 말하지 않았으면 null. mode: 그 금액**으로** 사면 "set", 기본 납입액에 **더** 사면 "add", amount가 null이면 null. state: 조건이 기준선(이동평균선 등)이나 기준값 **아래에 있는 상태**면 "below", **위에 있는 상태**면 "above", 뚫고 지나가는 순간(돌파·이탈·교차)이거나 위아래가 없으면 null.
cash_reserve — 현금을 일정 수준 이상 **남겨 두라**는 규칙. stated: 그런 말을 했으면 true. percent: 비율로 말했으면 숫자("현금 20% 유지"=20), amount: 금액으로 말했으면 표기 그대로, 수준을 말하지 않았으면("일정 수준") 둘 다 null. quote: 그 조각, 없으면 null.
max_buy — **한 번에 사는 금액**을 보유 현금의 몇 % 이내로 제한하는 규칙. percent: 숫자 또는 null. quote: 그 조각 또는 null.

출력 형식(JSON만):
{"plan": {"quote": "매월 첫 거래일마다 100만 원씩 매수", "amount": "100만 원", "period": "monthly"},
 "rules": [{"quote": "종가가 200일 이동평균선 아래에 있으면", "amount": "200만원", "mode": "set", "state": "below"}],
 "cash_reserve": {"stated": true, "percent": null, "amount": null, "quote": "항상 일정 수준의 현금을 유지"},
 "max_buy": {"percent": 10, "quote": "단일 매수 금액은 보유 현금의 10%를 넘지 않으며"}}"""


def build_system_prompt() -> str:
    return _SYSTEM


@dataclass
class RuleVerdict:
    amount: Optional[float]
    mode: Optional[str]
    state_operator: Optional[str]


@dataclass
class PlanVerdict:
    plan_quote: Optional[str] = None
    plan_amount: Optional[str] = None       # 말한 표기 그대로(환산은 BacktestSpec의 validator)
    plan_period: Optional[str] = None
    rules: Dict[str, RuleVerdict] = field(default_factory=dict)   # compact(인용) → 판정
    cash_pool: Any = None                   # CashPoolSpec | None
    cash_quotes: List[str] = field(default_factory=list)


def applies_to(intent: Any) -> bool:
    """물어볼 턴인가 — 계획이 있거나, 계획이 비었는데 자리를 못 찾은 말의 흔적이 남았다."""
    strategy = getattr(intent, "strategy", None)
    if strategy is None:
        return False
    bt = strategy.backtest
    if bt.contribution_amount is not None or bt.contribution_period is not None:
        return True
    return bool(getattr(intent, "unsupported_features", None)) or any(
        c.factor == _TRADING_VALUE_FACTOR for c in strategy.entry_conditions)


def _number(value: Any, low: float, high: float, *, low_open: bool, high_open: bool) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if (number < low or (low_open and number == low) or number > high or (high_open and number == high)):
        return None
    return number


def _positive_amount(value: Any) -> Optional[float]:
    from strategy_conversation.interpreter.models import _normalize_amount

    amount = _normalize_amount(value)
    return (float(amount) if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 0
            else None)


def build_request(user_input, conditions):
    quotes = [c.source_text for c in conditions if c.source_text]
    rows = "\n".join(f'- "{q}"' for q in quotes) or "- (없음)"
    return _SYSTEM, f"[전략 문장]\n{user_input}\n\n[조건]\n{rows}", 256 + 64 * len(quotes)


def check_contribution_plan(
    user_input: str, conditions: List[Any], chat: Callable[..., str],
) -> Optional[PlanVerdict]:
    """한 번의 LLM 호출로 계획·규칙·현금 관리 판정을 받는다. 실패는 1회 재시도 뒤 None(판정 없음)."""
    from engine.nl_parser import _compact
    from observability import span
    from strategy_conversation.interpreter.models import CashPoolSpec
    from strategy_conversation.interpreter.output_repair import extract_json_object

    quotes = [c.source_text for c in conditions if c.source_text]
    system, user, max_tokens = build_request(user_input, conditions)
    compact_input = _compact(user_input)
    with span("Contribution Plan Check · 적립식 판정", "chain",
              inputs={"user_input": user_input, "quotes": quotes}) as trace:
        payload = None
        last_error = ""
        for attempt in range(2):
            try:
                payload = json.loads(extract_json_object(chat(system, user, max_tokens=max_tokens)))
                if not isinstance(payload, dict):
                    raise ValueError("객체가 아님")
                break
            except Exception as exc:  # noqa: BLE001 — 보조 판정이 턴을 깨지 않는다(fail-open)
                last_error = str(exc)[:300]
                payload = None
        if payload is None:
            logger.warning("contribution plan check failed — no verdict | err=%s", last_error)
            trace.output(failed=True, error=last_error)
            return None

        verdict = PlanVerdict()
        # ① 계획 — 인용과 금액 표기가 입력에 그대로 있어야 한다(없던 적립식을 만들 수 있는 자리).
        plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
        quote = plan.get("quote")
        if isinstance(quote, str) and _compact(quote) and _compact(quote) in compact_input:
            verdict.plan_quote = quote
            amount = plan.get("amount")
            if isinstance(amount, str) and _compact(amount) in compact_input and _positive_amount(amount):
                verdict.plan_amount = amount
            period = plan.get("period")
            period = period.strip().lower() if isinstance(period, str) else None
            verdict.plan_period = period if period in PERIODS else None

        # ② 규칙 — 인용으로 대조한다(순서·항목 수에 기대지 않는다). [조건]에 없는 인용은 무시.
        known = {_compact(q): q for q in quotes}
        for item in payload.get("rules") if isinstance(payload.get("rules"), list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("quote"), str):
                continue
            key = _compact(item["quote"])
            match = next((k for k in known if k and (k == key or k in key or key in k)), None)
            if match is None or match in verdict.rules:
                continue
            amount = _positive_amount(item.get("amount"))
            mode = item.get("mode")
            state = item.get("state")
            if amount is None or mode not in MODES:
                continue
            verdict.rules[match] = RuleVerdict(
                amount=amount, mode=mode,
                state_operator=STATE_OPERATORS.get(state) if isinstance(state, str) else None)

        # ③ 현금 관리 — cash_pool_check와 같은 결정론(비율이 금액을 이긴다, 값 없는 하한은 되묻기).
        reserve = payload.get("cash_reserve") if isinstance(payload.get("cash_reserve"), dict) else {}
        max_buy = payload.get("max_buy") if isinstance(payload.get("max_buy"), dict) else {}
        reserve_pct = _number(reserve.get("percent"), 0, 100, low_open=True, high_open=True)
        reserve_amount = None if reserve_pct is not None else _positive_amount(reserve.get("amount"))
        max_buy_pct = _number(max_buy.get("percent"), 0, 100, low_open=True, high_open=False)
        stated = reserve.get("stated") is True or reserve_pct is not None or reserve_amount is not None
        if stated or max_buy_pct is not None:
            cash_quotes = [q.strip() for q in (reserve.get("quote") if stated else None,
                                               max_buy.get("quote") if max_buy_pct is not None else None)
                           if isinstance(q, str) and q.strip()]
            verdict.cash_pool = CashPoolSpec(
                reserve_pct=reserve_pct, reserve_amount=reserve_amount, reserve_stated=stated,
                max_buy_pct=max_buy_pct, source_texts=cash_quotes)
            verdict.cash_quotes = cash_quotes
        trace.output(
            plan={"quote": verdict.plan_quote, "amount": verdict.plan_amount, "period": verdict.plan_period},
            rules={known[k]: vars(v) for k, v in verdict.rules.items()},
            cash_pool=verdict.cash_pool.model_dump() if verdict.cash_pool is not None else None,
        )
        return verdict


def apply_verdict(intent: Any, verdict: PlanVerdict, *, only: Optional[List[Any]] = None) -> List[str]:
    """판정을 전략에 옮긴다. 반환값은 로그용 요약 조각 목록.

    - 계획: 비어 있을 때만 채운다(1차 해석을 덮어쓰지 않는다). 채우면 같은 구절을 쥔 거래대금 조건을 걷는다.
    - 규칙: 인용이 대조된 조건에 금액·방식 꼬리표, 비교 연산자가 없는 자리(교차 사건·빈 칸)에만 상태 연산자.
    - 현금 풀: 비어 있을 때만 채우고, 같은 인용을 담은 미지원 보고·지어낸 거래대금 조건을 걷는다.
    """
    from engine.nl_parser import _compact
    from strategy_conversation.interpreter.models import BacktestSpec

    strategy = intent.strategy
    bt = strategy.backtest
    notes: List[str] = []

    if (bt.contribution_amount is None and bt.contribution_period is None
            and (verdict.plan_amount or verdict.plan_period)):
        try:
            filled = BacktestSpec.model_validate({
                **bt.model_dump(), "contribution_amount": verdict.plan_amount,
                "contribution_period": verdict.plan_period})
        except Exception:  # noqa: BLE001 — 읽을 수 없는 표기는 '못 읽은 것'과 같다
            filled = None
        if filled is not None and (filled.contribution_amount or filled.contribution_period):
            strategy.backtest = bt = filled
            plan_key = _compact(verdict.plan_quote or "")
            strategy.entry_conditions = [
                c for c in strategy.entry_conditions
                if not (c.factor == _TRADING_VALUE_FACTOR and _compact(c.source_text or "")
                        and _compact(c.source_text or "") in plan_key)]
            notes.append(f"계획 회수 {filled.contribution_amount}/{filled.contribution_period}")

    for cond in strategy.entry_conditions:
        if only is not None and not any(cond is c for c in only):
            continue
        rule = verdict.rules.get(_compact(cond.source_text or ""))
        if rule is None or cond.buy_amount is not None:
            continue
        cond.buy_amount, cond.buy_amount_mode = rule.amount, rule.mode
        if rule.state_operator and (cond.operator is None or cond.operator in EVENT_OPERATORS):
            cond.operator = rule.state_operator
        notes.append(f"{cond.source_text}={rule.mode} {rule.amount:g}{' ' + rule.state_operator if rule.state_operator else ''}")

    if verdict.cash_pool is not None and bt.cash_pool is None:
        bt.cash_pool = verdict.cash_pool
        quotes = [_compact(q) for q in verdict.cash_quotes if _compact(q)]

        def _same_phrase(text: Optional[str]) -> bool:
            key = _compact(text or "")
            return bool(key) and any(key in q or q in key for q in quotes)

        intent.unsupported_features = [f for f in intent.unsupported_features if not _same_phrase(str(f))]
        strategy.entry_conditions = [
            c for c in strategy.entry_conditions
            if not (c.buy_amount is None and c.factor == _TRADING_VALUE_FACTOR and _same_phrase(c.source_text))]
        notes.append(f"현금 풀 하한={'되묻기' if not verdict.cash_pool.is_complete() else 'ok'} "
                     f"상한={verdict.cash_pool.max_buy_pct}")
    return notes
