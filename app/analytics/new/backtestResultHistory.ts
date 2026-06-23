// 백테스트 결과 화면은 채팅 라우트 안에서 상태로만 렌더되므로(별도 URL 없음),
// 브라우저 뒤로가기를 누르면 페이지를 완전히 떠나 버린다.
// 결과 화면 진입 시 가짜 히스토리 엔트리를 push하고 popstate를 가로채,
// 뒤로가기를 "대화창으로 복귀"로 동작하게 한다.
type HistoryWindow = Pick<
  Window,
  "history" | "addEventListener" | "removeEventListener"
>;

export function installBacktestResultBackHandler(
  onBack: () => void,
  win: HistoryWindow = window
): () => void {
  win.history.pushState({ simonsBacktestResult: true }, "");
  const handlePopState = () => onBack();
  win.addEventListener("popstate", handlePopState);
  return () => win.removeEventListener("popstate", handlePopState);
}
