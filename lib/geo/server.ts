import { cookies, headers } from "next/headers";
import {
  DEFAULT_REGION,
  isRegion,
  REGION_COOKIE,
  REGION_HEADER,
  type Region,
} from "./region";

/**
 * 서버 컴포넌트·라우트 핸들러 전용 — 현재 요청의 지역.
 * 페이지 요청은 미들웨어가 실어 준 헤더(경로 파생)를 읽고, 미들웨어가 안 도는
 * API 라우트는 페이지 방문 때 심어 둔 지역 쿠키로 폴백한다.
 */
export function getRequestRegion(): Region {
  try {
    const headerValue = headers().get(REGION_HEADER);
    if (isRegion(headerValue)) return headerValue;
  } catch {
    // 요청 컨텍스트 밖(정적 렌더 등) — 쿠키 폴백으로.
  }
  try {
    const cookieValue = cookies().get(REGION_COOKIE)?.value;
    if (isRegion(cookieValue)) return cookieValue;
  } catch {
    // 요청 컨텍스트 밖 — 기본 지역.
  }
  return DEFAULT_REGION;
}
