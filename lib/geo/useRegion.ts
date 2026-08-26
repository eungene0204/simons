"use client";

import { usePathname } from "next/navigation";
import { useCallback } from "react";
import {
  REGION_HEADER,
  regionFromPathname,
  withRegionPath,
  type Region,
} from "./region";

/** 현재 브라우저 경로에서 파생한 지역. 라우터 컨텍스트 밖(테스트 등)에선 kr. */
export function useRegion(): Region {
  return regionFromPathname(usePathname());
}

/**
 * 내부 링크·router.push 경로에 지역 프리픽스를 부여하는 헬퍼.
 * 사용: `const regionHref = useRegionHref(); <Link href={regionHref("/pricing")} />`
 */
export function useRegionHref(): (href: string) => string {
  const region = useRegion();
  return useCallback((href: string) => withRegionPath(region, href), [region]);
}

/**
 * 백엔드로 가는 API 호출(fetch)에 실을 지역 헤더 — **호출한 탭의 경로**에서 파생한다.
 *
 * API 라우트는 미들웨어 밖이라(matcher 제외) 종전에는 '마지막 방문 지역' 쿠키로만
 * 폴백했는데, 쿠키는 브라우저 전역이라 KR/US 탭을 오가면 /us 탭의 호출이 kr로
 * 오염됐다(2026-08-26 — /us에서 "hello"에 한국어 인사). 요청을 보내는 화면의 경로가
 * 그 요청의 지역 정본이다. 서버(lib/server/backend.ts·lib/geo/server.ts)는 이미 이
 * 헤더를 쿠키보다 먼저 읽으므로, 호출부는 headers에 펼쳐 넣기만 하면 된다.
 * (미들웨어가 도는 페이지 요청은 미들웨어가 이 헤더를 다시 쓰므로 위장 걱정이 없고,
 *  API 라우트에서 이 헤더가 정하는 것은 표시 언어뿐이다.)
 */
export function regionRequestHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  return { [REGION_HEADER]: regionFromPathname(window.location.pathname) };
}
