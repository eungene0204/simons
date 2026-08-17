import BacktestHistoryView from "./BacktestHistoryView";
import { getRequestLanguage } from "@/lib/i18n/server";

// 목록은 클라이언트가 조회한다(lib/backtest-history-cache).
// 서버에서 조회해 넘기면 탭을 누를 때마다 서버 왕복을 기다려야 해 매번 로딩이 보인다 —
// 캐시가 있으면 즉시 그리고, 목록이 바뀌는 시점(저장·자동 저장·삭제)에 캐시를 버려
// 옛 목록이 노출되지 않게 한다(FR-BT-031c).
export default function BacktestHistoryPage() {
  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return <BacktestHistoryView />;
}
