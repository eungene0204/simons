"""공용 안내 문구 — guardrails·/query/general이 사용한다.

[규제 안전] 개별 종목 분석 파이프라인(agent·recommendation_engine 등)은 제거됐다.
특정 종목 질문은 intent 분류의 suggested_reply(추천 불가 안내 + 전략 설계 전환)로 응답한다.
"""

from __future__ import annotations

DISCLAIMER = (
    "이 분석은 투자 판단을 위한 참고 정보이며, 최종 투자 결정은 본인의 책임입니다."
)
