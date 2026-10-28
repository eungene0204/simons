// 전략연구소 화면을 맨 위(스크롤 0)로 되돌린다 — 백테스트 결과 화면에서 대화 화면으로
// 돌아올 때 항상 위에서부터 보이도록(2026-08-17 지시). 결과 화면 진입 시의 스크롤 초기화와
// 같은 컨테이너(main 또는 window) 규칙을 쓴다.
export function scrollChatViewToTop(
  doc: Pick<Document, "querySelector"> = document,
  win: Pick<Window, "scrollTo"> = window
): void {
  const main = doc.querySelector("main");
  if (main && main.scrollHeight > main.clientHeight) {
    main.scrollTo({ top: 0, behavior: "auto" });
    return;
  }
  win.scrollTo({ top: 0, behavior: "auto" });
}
