import { getSessionUserId, isUnauthorizedAccessError } from "@/lib/get-user";
import { fetchUserBacktestHistory } from "@/lib/server/backtest-history-list";
import BacktestHistoryView from "./BacktestHistoryView";

// 쿠키를 읽고 매 진입마다 최신 목록을 조회한다 — 정적 프리렌더 금지.
export const dynamic = "force-dynamic";

// 목록을 서버에서 조회해 첫 렌더에 담아 보낸다.
// 클라이언트가 페이지를 받은 뒤 목록 API를 다시 호출하던 왕복 한 번이 사라지고,
// 예전 목록이 잠깐 보였다가 교체되는 일도 없다.
export default async function BacktestHistoryPage() {
  const userId = await getSessionUserId();

  return <BacktestHistoryView initialHistory={await loadHistory(userId)} />;
}

// 비로그인·비활성 계정은 빈 목록으로 둔다(기존 클라이언트 조회의 401 처리와 동일).
async function loadHistory(userId: number | null) {
  if (userId == null) return [];

  try {
    return await fetchUserBacktestHistory(userId);
  } catch (error) {
    if (isUnauthorizedAccessError(error)) return [];
    throw error;
  }
}
