"""종목·상품 표현의 상장 시장 판정 — "이 표현은 어느 나라 시장의 것인가"를 LLM에게 묻는다.

왜 필요한가: KR 레인(표시 언어 ko)은 한국 시장 전용이라 미국 시장 요청을 거절한다
(primary._kr_region_us_market_refusal). 그 판정의 1·2번 근거는 결정론으로 충분하다 —
LLM이 고른 시장 enum(universe.markets ∩ US_MARKETS)과, registry가 미국 티커로 푼 지정
종목이다. 남는 것이 **registry가 못 푼 표현**이다.

2026-09-21 실측(120B, KR 레인): "매월 첫 거래일마다 S&P500 ETF를 100만 원씩 매수합니다…"
→ markets=["ETF"](한국 ETF) + symbols=["S&P500 ETF"]. 미국 신호가 구조화 출력 어디에도
남지 않아 국내 ETF 전략으로 조립됐다. 표현 자체는 미국 상품인데 시장 enum에 없고 registry
정확 일치에도 없다 — 이 공백을 메우는 것이 이 패스다.

원문을 읽지 않는다: 입력은 **LLM이 종목 표현으로 뽑아 놓은 짧은 문자열**이고, 어느 시장의
상품인지는 지식 판정이라 다시 LLM에게 묻는다(대원칙 1 — 어휘 목록·정규식으로 'S&P'·'나스닥'
같은 낱말을 세지 않는다). 결정론 코드의 몫은 ① 정해진 enum인지 확인 ② enum에 따른 분기뿐이다.

호출 범위: registry가 못 푼 지정 종목 표현이 있는 턴만, 한 턴 한 번. 그런 표현이 없으면
호출이 없다(대부분의 턴).

실패 동작: 호출 오류·JSON 불성립·항목 수 불일치는 **판정 없음(None)** — 거절하지 않고
종전대로 진행한다(fail-open, quote_check와 같은 원칙). 개별 항목이 enum 밖이거나 "UNKNOWN"
이면 그 표현은 근거로 쓰지 않는다.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# KR=한국 상장, US=미국 상장, OTHER=그 밖의 해외, UNKNOWN=모르겠음
MARKETS = frozenset({"KR", "US", "OTHER", "UNKNOWN"})

_SYSTEM = """당신은 **조회기**입니다. 사용자가 지목한 종목·상품 이름마다, 그것이 어느 나라 시장에 상장된 것인지 답하세요.

market — 한국 거래소(코스피·코스닥) 종목이면 "KR", 미국 거래소(뉴욕·나스닥) 종목이나 미국 지수를 추종하는 미국 상장 ETF면 "US", 그 밖의 나라(일본·중국·유럽 등)면 "OTHER", 어느 시장인지 모르겠으면 "UNKNOWN".

한국 거래소에 상장된 해외 지수 ETF(예: "TIGER 미국S&P500")는 한국 상장이므로 "KR"입니다.

출력 형식(JSON만, 항목 순서대로):
{"items": [{"market": "US"}]}"""


def build_system_prompt() -> str:
    return _SYSTEM


def check_markets(terms: List[str], chat: Callable[..., str]) -> Optional[Dict[str, str]]:
    """종목 표현 → 시장 판정({표현: "KR"|"US"|"OTHER"}). 실패·enum 밖은 제외, 전체 실패는 None."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object

    if not terms:
        return {}
    rows = "\n".join(f'{i}. "{term}"' for i, term in enumerate(terms, 1))
    with span("Market Region Check · 종목 시장 판정", "chain",
              inputs={"terms": list(terms)}) as trace:
        try:
            raw = chat(_SYSTEM, f"[종목·상품 이름]\n{rows}", max_tokens=32 + 24 * len(terms))
            payload = json.loads(extract_json_object(raw))
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list) or len(items) != len(terms):
                raise ValueError(f"항목 수 불일치: {len(terms)}개 요청")
        except Exception as exc:  # noqa: BLE001 — 보조 판정이 턴을 깨지 않는다(fail-open)
            logger.warning("market region check failed — no verdicts | err=%s", str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        verdicts: Dict[str, str] = {}
        for term, item in zip(terms, items):
            market = (item or {}).get("market") if isinstance(item, dict) else None
            if market in MARKETS and market != "UNKNOWN":
                verdicts[term] = market
        trace.output(verdicts=verdicts)
        return verdicts
