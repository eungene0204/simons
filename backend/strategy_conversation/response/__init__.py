"""Responder 레이어 — 구조화된 결과를 사용자 텍스트로 서술한다(해석 금지).

계약(Planner → Tool/Engine → Responder Phase 2):
- 입력은 항상 **구조화된 결과**다(StrategyIntent·ValidationReport·notices·되묻기 질문).
  사용자 원문을 입력으로 받아 의미를 판단하는 코드는 이 레이어에 둘 수 없다.
- 사용자에게 나가는 자유 텍스트는 반드시 출력 관문(output_guard.finalize_user_response)을
  통과한다 — 추천·전망·보장 표현의 결정론 문장 제거가 최종 방어선이다. planner가
  도입돼도 이 관문은 우회할 수 없다.
"""
