"""
안전장치 — 금지 표현 필터 + 면책 문구 강제(스펙 §7).

LLM 설명 출력에서 확정적 수익·책임 전가·"무조건 사세요" 류 표현을 제거하고,
면책 문구가 없으면 덧붙인다. coach_routes의 `_strip_*` 후처리 패턴과 동일한 접근.
"""

from __future__ import annotations

import re
from typing import Optional

from .schemas import DISCLAIMER

# 금지 표현(스펙 §7) — 한 문장 단위로 제거한다.
# ① 확정적 수익/손실 표현, ② [규제 안전] 매수·매도·시점 등 '행동 지시'(개별 종목 추천 회피).
#    설명은 지표의 객관적 상태만 서술해야 하며, 무엇을 언제 사고팔지는 절대 지시하지 않는다.
_FORBIDDEN = re.compile(
    r"무조건\s*사|반드시\s*오릅?니다|반드시\s*오른|지금\s*사면\s*수익|"
    r"수익\s*(?:이\s*)?납니다|손실\s*가능성\s*없|손실\s*(?:이\s*)?없|"
    r"확실한\s*종목|확실히\s*오|수익\s*보장|원금\s*보장|손해\s*볼\s*일\s*없|"
    r"매수하세요|매도하세요|매수\s*하시|매도\s*하시|사세요|파세요|팔세요|"
    r"분할\s*매수|매수\s*시점|매도\s*시점|지금\s*매수|지금\s*매도|"
    r"진입하세요|청산하세요|매수를\s*권|매도를\s*권|매수\s*추천|매도\s*추천",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。\n])\s+")


def contains_forbidden(text: str) -> bool:
    return bool(_FORBIDDEN.search(text or ""))


def sanitize(text: str) -> str:
    """금지 표현이 든 문장을 제거한다."""
    if not text:
        return ""
    sentences = _SENTENCE_SPLIT.split(text)
    kept = [s for s in sentences if not _FORBIDDEN.search(s)]
    return " ".join(part.strip() for part in kept if part.strip()).strip()


# [규제 안전] 지표·성과에 **등급을 매기는** 표현. _FORBIDDEN(행동 지시)과 축이 다르므로
# 별도로 둔다 — 여기 합치면 AI 리포트·종목 설명 등 기존 호출부의 출력까지 바뀐다.
#
# 결과 수치 질문 답변 전용이다. 프롬프트로 "등급 매기지 마라"를 지시해도 9B가 완전히
# 지키지는 못한다(실측 2026-08-11: '샤프 지수 1.21은 위험 조정 후 수익성이 긍정적인
# 수준'). CLAUDE.md 금지 예시 "좋은 투자 전략입니다"와 같은 종류라 문장째 걷어낸다.
#
# 입력은 우리 LLM의 출력이지 사용자 원문이 아니다 — 자연어 해석 계약의 금지 대상이 아니다.
#
# '위험이 높다' 류는 넣지 않는다 — "최대 낙폭 -35%는 손실 폭이 컸음을 뜻한다"처럼
# 과거 데이터의 사실 서술과 구분되지 않아, 넣으면 정당한 설명까지 지워진다.
_METRIC_GRADING = re.compile(
    r"양호|우수|훌륭|뛰어난|탁월|바람직|이상적|긍정적|부정적|저조|"
    r"안정적(?:이|인|으로)|효율적(?:이|인|으로)|"
    r"좋(?:은|다|습니다|네요|음)|나쁘(?:다|지|네요)|나쁜"
)


def strip_metric_grading(text: str) -> str:
    """지표에 등급을 매기는 문장을 제거한다(결과 수치 설명 전용).

    지표 사이의 **관계** 설명("승률이 높아도 평균 손실이 크면 총손익은 마이너스")은
    남기고, 수치 하나를 두고 잘하고 못했다고 말하는 문장만 걷어낸다.
    """
    if not text:
        return ""
    sentences = _SENTENCE_SPLIT.split(text)
    kept = [s for s in sentences if not _METRIC_GRADING.search(s)]
    return " ".join(part.strip() for part in kept if part.strip()).strip()


# 없는 데이터를 거론하는 일반 표현 — 해당 문장을 통째로 제거한다(INSUFFICIENT_DATA 설명에는 적용 안 함).
_UNAVAILABLE = re.compile(
    r"데이터\s*없음|데이터(?:가|는)?\s*(?:없|부족|확보되지|제공되지|포함(?:되어|하고)?\s*있지\s*않|포함(?:되지|하지)\s*않)|"
    r"정보(?:가|는)?\s*(?:없|부족|확보되지|제공되지|포함(?:되어|하고)?\s*있지\s*않|포함(?:되지|하지)\s*않)|"
    r"확보되지\s*않|확보하지\s*못|제공되지\s*않|포함되어\s*있지\s*않|포함되지\s*않|"
    r"분석하지\s*않|분석(?:할|하지)\s*(?:수\s*)?없|다루지\s*않|언급하지\s*않|반영하지\s*않|"
    r"파악(?:하는\s*데|에)?\s*한계|알\s*수\s*없"
)


def strip_unavailable_data_mentions(text: str, missing_topics: Optional[list[str]] = None) -> str:
    """없는 데이터를 거론하는 문장을 제거한다.

    - `_UNAVAILABLE`: '데이터가 포함되어 있지 않아 분석하지 않습니다' 류 일반 표현.
    - `missing_topics`: 실제로 데이터가 없는 주제(뉴스·AI 예측 등)의 정규식 목록.
      해당 주제를 언급하는 문장은 표현과 무관하게 통째로 제거한다(아예 언급 금지).
    """
    if not text:
        return ""
    topic_res = [re.compile(p) for p in (missing_topics or [])]
    sentences = _SENTENCE_SPLIT.split(text)
    kept = []
    for s in sentences:
        if _UNAVAILABLE.search(s):
            continue
        if any(tr.search(s) for tr in topic_res):
            continue
        kept.append(s)
    return " ".join(part.strip() for part in kept if part.strip()).strip()


def ensure_disclaimer(text: str) -> str:
    """면책 문구가 없으면 덧붙인다(항상 포함 보장)."""
    body = (text or "").strip()
    if "본인의 책임" in body or "투자 판단을 위한 참고" in body:
        return body
    if not body:
        return DISCLAIMER
    return f"{body}\n\n{DISCLAIMER}"


def attach_news_link(text: str, url: Optional[str]) -> str:
    """설명이 '뉴스'를 언급하고 실제 출처 URL이 있으면 첫 '뉴스'를 마크다운 링크로 만든다.
    프론트(parseCoachSegments)가 [뉴스](url)을 클릭 가능한 링크로 렌더한다."""
    if not text or not url or "뉴스" not in text:
        return text
    if "](http" in text:  # 이미 링크가 있으면 중복 처리하지 않는다
        return text
    if not str(url).startswith("http"):
        return text
    return text.replace("뉴스", f"[뉴스]({url})", 1)


def apply(text: str) -> str:
    """금지 표현 제거 + 면책 문구 강제를 한 번에 적용한다."""
    return ensure_disclaimer(sanitize(text))
