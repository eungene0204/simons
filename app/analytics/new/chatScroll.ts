// 고정된 채팅 입력창에 새 메시지가 가리지 않도록 둘 여유 공간(px).
export const CHAT_INPUT_CLEARANCE = 180;

// 메시지 끝(messageEndBottom)이 (뷰포트 하단 - 입력창 여유) 지점에 오도록
// 얼마나 더 아래로 스크롤해야 하는지 계산한다.
// 이미 보이면(여유 안쪽이면) 0을 반환해 위로 과도하게 스크롤되는 것을 막는다.
export function computeChatScrollDelta(
  messageEndBottom: number,
  viewportBottom: number,
  inputClearance: number = CHAT_INPUT_CLEARANCE
): number {
  const delta = messageEndBottom - (viewportBottom - inputClearance);
  return delta > 0 ? delta : 0;
}
