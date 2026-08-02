"""백테스트 설정 기본값 질문 — 결정적 답변.

전략 분석실 대화에서 "슬리피지는 몇 %가 기본 값이지?" 같은 설정값 질문이 LLM 일반답변으로
흘러가 근거 없는 값(예: "기본값은 0%")을 답하는 사고를 막는다.

- 값의 SOT는 코드의 실제 기본값이다: ParsedStrategy 필드 default(수수료·슬리피지·초기자금·
  체결 시점), enforce 하한선(MIN_INITIAL_CAPITAL), 시뮬레이터 증권거래세 상수. 여기서
  숫자를 하드코딩하지 않아 기본값이 바뀌어도 답변이 함께 따라간다.
- [feedback_nl_parser_hybrid] 명확한 핵심(설정 용어 + 값 질문)만 결정적으로 잡고,
  개념 설명 같은 긴 꼬리는 LLM에 맡긴다. 단, LLM 답변에도 실제 기본값을 사실 블록으로
  주입해 값 환각을 막는다(facts_block).
"""

from __future__ import annotations

import re
from typing import Optional

# 설정 항목별 언급 cue. 키는 답변 라인 선택에 쓴다.
_SETTING_TERMS: dict[str, re.Pattern] = {
    "slippage": re.compile(r"슬리피지|slippage", re.IGNORECASE),
    "fee": re.compile(r"수수료", re.IGNORECASE),
    "tax": re.compile(r"거래세", re.IGNORECASE),
    "capital": re.compile(
        r"초기\s*자금|초기\s*자본|시작\s*자금|투자\s*원금|초기\s*투자금", re.IGNORECASE
    ),
    "execution": re.compile(r"체결\s*시점|체결\s*가격|체결\s*방식", re.IGNORECASE),
}

# 값을 묻는 표현. '기본값이 뭐야/몇 %야/얼마야', '현재 셋팅된 값은?' 등.
_VALUE_QUESTION = re.compile(
    r"기본\s*값|기본으로|디폴트|default|얼마|몇\s*[%퍼프]|"
    r"[셋세]팅된|[셋세]팅\s*값|설정된|설정되|설정돼|설정\s*값|적용되",
    re.IGNORECASE,
)

# 값을 '바꾸라'는 명령("슬리피지를 0.1%로 설정해줘")은 질문이 아니다 — 수정 경로에 맡긴다.
# "얼마로 설정돼 있어?"(피동형 질문)는 명령이 아니므로 명령형 어미만 잡는다.
_SET_COMMAND = re.compile(
    r"(?:로|으로)\s*(?:설정하|설정해|변경하|변경해|바꾸|바꿔|맞춰|올려|내려|늘려|줄여|해\s*줘|해줘)",
    re.IGNORECASE,
)

# 특정 항목 없이 기본 설정 전반을 묻는 표현("백테스트 기본 설정값 알려줘").
_GENERIC_DEFAULTS = re.compile(
    r"(?:기본|디폴트)\s*(?:설정|[셋세]팅|옵션)|설정\s*값|[셋세]팅\s*값", re.IGNORECASE
)

# 설정 용어 단독 후속 질문("수수료는?", "그럼 거래세는?") — 직전 기본값 답변에 이어
# 다른 항목을 묻는 형태라 값 질문 cue가 없어도 기본값 질문으로 본다.
_BARE_TERM_QUESTION = re.compile(
    r"^\s*(?:그럼|그러면|그리고)?\s*"
    r"(?:슬리피지|수수료|(?:증권)?거래세|초기\s*(?:자금|자본|투자금)|체결\s*(?:시점|가격|방식))"
    r"\s*(?:값)?\s*(?:은|는|이|가)?\s*\??\s*$",
    re.IGNORECASE,
)


def _mentioned_topics(text: str) -> list[str]:
    return [key for key, pat in _SETTING_TERMS.items() if pat.search(text)]


def is_default_question(text: str) -> bool:
    """백테스트 설정 기본값을 묻는 질문인지 결정적으로 판별한다."""
    t = text or ""
    if _SET_COMMAND.search(t):
        return False
    if _BARE_TERM_QUESTION.match(t):
        return True
    if not _VALUE_QUESTION.search(t):
        return False
    return bool(_mentioned_topics(t) or _GENERIC_DEFAULTS.search(t))


def _defaults() -> dict:
    # 지연 import — engine.simulator는 vectorbt를 끌고 오므로 모듈 로드 시점 비용을 피한다.
    from engine.nl_parser import MAX_INITIAL_CAPITAL, MIN_INITIAL_CAPITAL, ParsedStrategy
    from engine.simulator import DEFAULT_SELL_TAX_RATE

    fields = ParsedStrategy.model_fields
    return {
        "capital": fields["initial_capital"].default,          # 원
        "min_capital": MIN_INITIAL_CAPITAL,                    # 원
        "max_capital": MAX_INITIAL_CAPITAL,                    # 원
        "fee_pct": fields["fee_rate"].default,                 # %
        "slippage_pct": fields["slippage_rate"].default,       # %
        "sell_tax_pct": DEFAULT_SELL_TAX_RATE * 100,           # %
        "next_open": fields["execution_timing"].default == "next_open",
    }


def _fmt_pct(value: float) -> str:
    return f"{value:g}%"


def _fmt_manwon(value: float) -> str:
    return f"{value / 10_000:,.0f}만원"


def _fmt_eok(value: float) -> str:
    return f"{value / 100_000_000:,.0f}억원"


def _topic_lines(topics: list[str]) -> list[str]:
    d = _defaults()
    lines = {
        "capital": (
            f"초기자금 기본값은 {_fmt_manwon(d['capital'])}입니다"
            f" (최소 {_fmt_manwon(d['min_capital'])} — 더 작게 입력하면 자동 보정됩니다,"
            f" 최대 {_fmt_eok(d['max_capital'])} — 더 크게 입력하면 설정되지 않습니다)."
        ),
        "fee": (
            f"매매 수수료 기본값은 매수·매도 각 {_fmt_pct(d['fee_pct'])}입니다."
        ),
        "tax": (
            f"증권거래세는 매도 시 {_fmt_pct(d['sell_tax_pct'])}가 기본 적용됩니다"
            f" (ETF 유니버스는 거래세가 없어 0%)."
        ),
        "slippage": f"슬리피지 기본값은 {_fmt_pct(d['slippage_pct'])}입니다.",
        "execution": (
            "체결 시점 기본값은 신호 다음 날 시가입니다"
            if d["next_open"]
            else "체결 시점 기본값은 당일 종가입니다"
        ) + " (당일 종가/다음 날 시가 중 선택 가능).",
    }
    # 수수료를 물으면 매도 시 붙는 거래세도 함께 알려야 총비용 오해가 없다.
    if "fee" in topics and "tax" not in topics:
        topics = topics + ["tax"]
    order = ["capital", "fee", "tax", "slippage", "execution"]
    return [lines[key] for key in order if key in topics]


def reply(text: str) -> Optional[str]:
    """기본값 질문이면 실제 코드 기본값으로 답변을 만든다. 아니면 None."""
    if not is_default_question(text):
        return None
    topics = _mentioned_topics(text or "") or list(_SETTING_TERMS)
    body = "\n".join(f"- {line}" for line in _topic_lines(topics))
    return (
        f"{body}\n이 값들은 요청하시면 변경할 수 있으며"
        "(예: \"슬리피지를 0.1%로 바꿔줘\"), 변경하셨다면 변경한 값이 적용됩니다."
    )


def facts_block(text: str) -> Optional[str]:
    """질문에 설정 용어가 언급되면 LLM 프롬프트에 주입할 실제 기본값 사실 블록을 만든다.

    "슬리피지가 뭐야?" 같은 개념 질문은 LLM이 설명하되, 기본값을 언급한다면
    지어낸 값이 아니라 이 블록의 값을 쓰게 한다.
    """
    topics = _mentioned_topics(text or "")
    if not topics:
        return None
    lines = "\n".join(f"- {line}" for line in _topic_lines(topics))
    return (
        "[이 플랫폼의 실제 기본 설정값 — 설정값·기본값을 언급할 때는 반드시 아래 값만 사용하라. "
        "'설정 패널' 같은 화면 요소는 존재하지 않으니 언급하지 말고, 변경 방법을 안내한다면 "
        "채팅으로 요청하면 된다고만 하라(예: \"슬리피지를 0.1%로 바꿔줘\")]\n"
        + lines
    )
