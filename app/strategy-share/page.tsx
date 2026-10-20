import StrategyShareView from "@/components/strategy-share/StrategyShareView";
import { getRequestLanguage } from "@/lib/i18n/server";

// 전략공유(2026-10-20) — 사용자들이 공개한 전략과, 그 전략을 쓰는 공개 모의투자 계좌의 수익률.
export default function StrategySharePage() {
  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return <StrategyShareView />;
}
