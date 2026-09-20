// 지역 라우팅 미들웨어.
//
// - `/us` 트리는 같은 라우트 트리로 rewrite 하고(파일 중복 없음), 지역을 내부 헤더로 실어 준다.
//   단, `US_REGION_BLOCKED`가 켜져 있으면 `/us` 트리 전체를 없는 경로로 취급한다(일시 차단).
// - 한국 트리 요청에는 kr 헤더를 실어 준다.
// - 자동 지역 리다이렉트는 없다. `www.nullstock.im/*`는 무조건 한국 서비스이고, 글로벌 서비스는
//   `/us` 경로로만 진입한다(2026-09-15 — 브라우저 언어가 영어인 한국 방문자가 `/`에서 `/us`로
//   튕기던 사고로 Accept-Language 기반 첫 방문 리다이렉트를 폐지). 되살리지 않는다.
// - 사용자가 입력한 경로를 그대로 존중하고, 마지막 방문 지역을 쿠키에 기억한다.
//
// API·정적 리소스는 제외한다 — API 라우트는 지역 쿠키를 직접 읽는다(lib/geo/server.ts).

import { NextResponse, type NextRequest } from "next/server";
import {
  REGION_COOKIE,
  REGION_HEADER,
  regionFromPathname,
  stripRegionPrefix,
  type Region,
} from "@/lib/geo/region";

const REGION_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

// 글로벌(/us) 서비스 일시 차단 스위치 — 2026-09-20 사용자 지시.
// 재개할 때는 이 상수를 false 로 바꾸고 배포한다(다른 설정 변경 없음).
const US_REGION_BLOCKED = true;

function requestHeadersWithRegion(request: NextRequest, region: Region): Headers {
  const requestHeaders = new Headers(request.headers);
  // 외부에서 위장해 들어온 지역 헤더는 신뢰하지 않는다 — 항상 미들웨어가 다시 쓴다.
  requestHeaders.set(REGION_HEADER, region);
  return requestHeaders;
}

function rememberRegion(response: NextResponse, request: NextRequest, region: Region): void {
  if (request.cookies.get(REGION_COOKIE)?.value === region) return;
  response.cookies.set(REGION_COOKIE, region, {
    path: "/",
    maxAge: REGION_COOKIE_MAX_AGE,
    sameSite: "lax",
  });
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const region = regionFromPathname(pathname);

  if (region === "us") {
    if (US_REGION_BLOCKED) {
      // 없는 경로로 취급한다 — Next 기본 404 페이지를 404 상태로 돌려준다.
      // 지역 쿠키도 남기지 않는다(쿠키는 미들웨어 밖 API 라우트의 지역 폴백이다).
      return NextResponse.rewrite(new URL("/_not-found", request.url));
    }

    const url = request.nextUrl.clone();
    url.pathname = stripRegionPrefix(pathname);
    const response = NextResponse.rewrite(url, {
      request: { headers: requestHeadersWithRegion(request, "us") },
    });
    rememberRegion(response, request, "us");
    return response;
  }

  const response = NextResponse.next({
    request: { headers: requestHeadersWithRegion(request, "kr") },
  });
  rememberRegion(response, request, "kr");
  return response;
}

export const config = {
  // API·Next 내부 리소스·확장자 있는 정적 파일 제외.
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
