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

// 전략연구소 화면을 대화 끝까지 끝까지 올려서 보여준다 — 대화를 복원하거나 결과 화면에서
// 돌아왔을 때 마지막 버블('백테스트 시작하기' 버튼 등)이 고정 입력창 뒤에 걸리지 않도록.
// 최대 스크롤 위치에서는 대화 컨테이너의 하단 여백(pb-56 = 224px)이 입력창(≈135px)보다
// 커서 마지막 버블이 항상 입력창 위에 놓인다.
// 스크롤 컨테이너는 레이아웃의 <main>이며, main이 스크롤되지 않는 레이아웃에서는 윈도우다.
export function scrollChatViewToEnd(
  doc: Pick<Document, "querySelector" | "documentElement"> = document,
  win: Pick<Window, "scrollTo"> = window
): void {
  const main = doc.querySelector("main");
  if (main && main.scrollHeight > main.clientHeight) {
    main.scrollTo({ top: main.scrollHeight, behavior: "auto" });
    return;
  }
  win.scrollTo({ top: doc.documentElement.scrollHeight, behavior: "auto" });
}
