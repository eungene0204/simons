// '백테스트 실행' 버튼은 마지막 어시스턴트 메시지에 정확히 한 곳에만 보여야 한다.
// 전략 검증(coach) 텍스트가 있으면 검증 블록 아래("coach"), 없으면 전략 요약 바로
// 아래("summary")에 붙인다. 두 위치의 조건이 겹쳐 coachText 도착 후에도 요약 아래
// 버튼이 남아 버튼이 두 개 렌더되던 회귀를 막는다.

export interface RunButtonMessageState {
  coachText?: string;
  coachLoading?: boolean;
  clarification?: string;
}

export type RunButtonPlacement = "summary" | "coach" | null;

export function runButtonPlacement(msg: RunButtonMessageState): RunButtonPlacement {
  if (msg.coachLoading) return null;
  if (msg.coachText) return "coach";
  if (msg.clarification) return null;
  return "summary";
}
