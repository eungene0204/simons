export const PENDING_STRATEGY_PROMPT_KEY = "simons.pendingStrategyPrompt";
// 진행 중인 전략 채팅 상태 — 다른 페이지로 갔다가 돌아와도 대화를 복원하기 위함.
export const STRATEGY_CHAT_STATE_KEY = "simons.strategyChatState";

// 백테스트 결과 화면은 전략연구소 라우트 안에서 상태로만 렌더된다(별도 URL 없음).
// 탑메뉴 '전략연구소'를 눌렀을 때 이미 떠 있는 화면에 "결과 화면을 내리라"고 알리는 신호.
export const STRATEGY_LAB_CHAT_VIEW_EVENT = "simons:strategy-lab-chat-view";

// 탑메뉴 '전략연구소' 클릭 → 결과 화면 대신 대화 화면으로 이동한다.
// 같은 라우트에 이미 마운트된 화면에는 이벤트로, 새로 마운트되는 화면에는
// 세션 스냅샷의 stage 강등으로 알린다(대화·결과 데이터 자체는 그대로 보존).
export function requestStrategyLabChatView() {
  try {
    const raw = sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY);
    if (raw) {
      const snapshot = JSON.parse(raw);
      if (snapshot?.stage === "done") {
        sessionStorage.setItem(
          STRATEGY_CHAT_STATE_KEY,
          JSON.stringify({ ...snapshot, stage: "ready" })
        );
      }
    }
  } catch {
    // 스냅샷 접근·파싱 실패는 무시 — 같은 라우트 전환은 이벤트가 담당한다.
  }
  window.dispatchEvent(new Event(STRATEGY_LAB_CHAT_VIEW_EVENT));
}
