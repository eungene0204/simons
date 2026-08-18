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
  // 뒤로가기로 대화 항목에 돌아오면 브라우저가 그 항목에 저장해 둔 스크롤 위치(백테스트
  // 실행 버튼을 누르던 자리)를 우리 '맨 위' 스크롤 뒤에 비동기로 되살린다(Chrome 실측,
  // 2026-08-17). scrollRestoration은 항목별 속성이므로 push 전에 — 아직 대화 항목 위에
  // 있을 때 — manual로 바꿔 두고, 복귀 후 정리 시 원래 값으로 되돌린다.
  const previousScrollRestoration = win.history.scrollRestoration;
  try {
    win.history.scrollRestoration = "manual";
  } catch {
    // 지원하지 않는 환경(테스트 더블 등)은 무시 — 되돌리기 동작 자체엔 영향 없다.
  }
  win.history.pushState({ simonsBacktestResult: true }, "");
  const handlePopState = () => onBack();
  win.addEventListener("popstate", handlePopState);
  return () => {
    win.removeEventListener("popstate", handlePopState);
    if (previousScrollRestoration) {
      try {
        win.history.scrollRestoration = previousScrollRestoration;
      } catch {
        // 위와 같다.
      }
    }
  };
}
