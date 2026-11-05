import { redirect } from "next/navigation";
import { getSessionUserId } from "@/lib/get-user";
import { getRequestRegion } from "@/lib/geo/server";
import { withRegionPath } from "@/lib/geo/region";
import StrategyLabClientPage from "./new/page";

// 비로그인 방문자는 서버에서 바로 홈(소개 페이지)으로 보낸다.
// 클라이언트 가드(AuthSessionGuard)에만 맡기면 전략연구소가 한 번 그려진 뒤에 튕겨 나간다.
export default async function StrategyLabPage() {
  if ((await getSessionUserId()) == null) {
    redirect(withRegionPath(getRequestRegion(), "/"));
  }
  return <StrategyLabClientPage />;
}
