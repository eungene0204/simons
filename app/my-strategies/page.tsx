import MyStrategiesView from "@/components/strategy/MyStrategiesView";
import { getRequestLanguage } from "@/lib/i18n/server";

// 내 전략(2026-10-21) — 전략연구소의 '내 전략' 탭을 상단 메뉴 화면으로 옮겼다.
export default function MyStrategiesPage() {
  // 요청 언어를 서버 렌더에 고정한다(비동기 대기 뒤에 호출해야 다른 요청과 섞이지 않는다).
  getRequestLanguage();
  return <MyStrategiesView />;
}
