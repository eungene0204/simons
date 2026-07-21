"""투자 용어 정의 사실 블록 — /query/general LLM 답변의 정의 오류 방지.

소형 LLM이 기초 용어 정의를 틀리는 실측 사고(레드팀 QA 6-1 "PER=주가순자산비율",
7-4 "RSI 90=극단적 과매도") 보정. platform_defaults.facts_block(설정 기본값)과 동형으로,
질문에 등장한 용어의 정확한 정의를 프롬프트에 사실로 주입한다 — 정의를 언급한다면
반드시 이 값을 쓰게 한다.
"""

from __future__ import annotations

import re
from typing import Optional

# 용어 → (감지 패턴, 정의 한 줄). 정의는 검증된 표준 정의만 담는다(해석·추천 금지).
_TERM_FACTS: tuple[tuple[str, str, str], ...] = (
    ("PER", r"\bper\b|퍼|피이알|주가수익비율",
     "PER(주가수익비율) = 주가 ÷ 주당순이익(EPS). 낮을수록 이익 대비 주가가 낮게 평가된 것이다."),
    ("PBR", r"\bpbr\b|주가순자산비율",
     "PBR(주가순자산비율) = 주가 ÷ 주당순자산(BPS). 낮을수록 순자산 대비 주가가 낮게 평가된 것이다."),
    ("ROE", r"\broe\b|자기자본이익률",
     "ROE(자기자본이익률) = 순이익 ÷ 자기자본. 높을수록 자본을 효율적으로 굴려 이익을 낸 것이다."),
    ("RSI", r"\brsi\b|상대강도지수",
     "RSI(상대강도지수)는 0~100 범위이며 통상 70 이상을 과매수, 30 이하를 과매도로 본다. "
     "90은 극단적인 과매수(과매도가 아님)다."),
    ("MACD", r"\bmacd\b",
     "MACD는 단기·장기 지수이동평균의 차이로, 종목 가격 수준에 따라 값의 크기가 달라 "
     "'100 이상' 같은 절대 기준값은 보편적으로 성립하지 않는다. 통상 시그널선 교차를 신호로 본다."),
    ("부채비율", r"부채비율",
     "부채비율 = 부채 ÷ 자기자본. 높을수록 레버리지가 커져 이익과 손실 변동이 모두 커진다 — "
     "높다고 수익이 보장되지 않으며 재무 위험이 커진다."),
    ("PSR", r"\bpsr\b|주가매출액?비율",
     "PSR(주가매출비율) = 시가총액 ÷ 매출액. 낮을수록 매출 대비 주가가 낮게 평가된 것이다."),
    ("골든크로스", r"골든\s*크로스|데드\s*크로스",
     "골든크로스는 단기 이동평균이 장기 이동평균을 위로 교차하는 사건이다. 추세 신호일 뿐 "
     "상승을 보장하지 않는다."),
)

_COMPILED = tuple(
    (name, re.compile(pattern, re.IGNORECASE), fact) for name, pattern, fact in _TERM_FACTS
)


def facts_block(text: str) -> Optional[str]:
    """질문에 등장한 용어의 정의 사실 블록을 만든다(없으면 None)."""
    t = text or ""
    lines = [fact for _, pattern, fact in _COMPILED if pattern.search(t)]
    if not lines:
        return None
    body = "\n".join(f"- {line}" for line in lines)
    return (
        "[용어 정의 사실 — 아래 용어를 설명하거나 언급할 때는 반드시 이 정의를 그대로 따르라. "
        "정의와 모순되는 서술 금지]\n" + body
    )
