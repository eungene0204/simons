import type { BacktestHistoryItem } from "@/types/strategy";

// 백테스트 기록 목록의 클라이언트 캐시.
// 탭을 다시 눌렀을 때 목록을 즉시 그리기 위한 것이며, 목록이 바뀔 수 있는 시점
// (저장·자동 저장·삭제)에는 반드시 버려야 한다 — 방금 실행한 백테스트가 빠진
// 옛 목록이 노출되는 것을 막는 유일한 장치다(FR-BT-031c).
let cachedHistory: BacktestHistoryItem[] | null = null;
let inFlightRequest: Promise<BacktestHistoryItem[]> | null = null;

export function getCachedBacktestHistory() {
  return cachedHistory;
}

export function setCachedBacktestHistory(history: BacktestHistoryItem[]) {
  cachedHistory = history;
}

// 목록이 바뀌는 순간 호출한다. 다음 진입은 캐시 없이 서버에서 새로 받는다.
export function invalidateBacktestHistoryCache() {
  cachedHistory = null;
  inFlightRequest = null;
}

export async function refreshBacktestHistoryCache(): Promise<BacktestHistoryItem[]> {
  if (inFlightRequest) return inFlightRequest;

  // 비로그인·비활성 계정은 401 — 서버 렌더가 빈 목록을 내려주던 것과 같게 empty state로 둔다.
  inFlightRequest = fetch("/api/backtest/history")
    .then((response) => (response.ok ? response.json() : []))
    .then((history: unknown) => {
      const nextHistory = Array.isArray(history)
        ? (history as BacktestHistoryItem[])
        : [];
      cachedHistory = nextHistory;
      return nextHistory;
    })
    .finally(() => {
      inFlightRequest = null;
    });

  return inFlightRequest;
}
