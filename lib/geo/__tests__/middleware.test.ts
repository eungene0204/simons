// 미들웨어 — `www.nullstock.im/*`는 무조건 한국 서비스다. 2026-09-15 사고: 브라우저 언어가
// 영어인 한국 방문자가 첫 방문 시 Accept-Language 폴백으로 `/`→`/us`로 튕겼다.
// 자동 지역 리다이렉트는 폐지됐고 글로벌 서비스는 `/us` 경로로만 진입한다.
import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";
import { REGION_COOKIE, REGION_HEADER } from "@/lib/geo/region";

function request(path: string, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(`https://www.nullstock.im${path}`, { headers });
}

describe("middleware 지역 라우팅", () => {
  it("영어 브라우저의 첫 방문도 `/`는 한국 서비스에 남긴다(리다이렉트 없음)", () => {
    const res = middleware(
      request("/", { "accept-language": "en-US,en;q=0.9", "user-agent": "Mozilla/5.0" })
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
    expect(res.headers.get("x-middleware-request-" + REGION_HEADER)).toBe("kr");
    expect(res.cookies.get(REGION_COOKIE)?.value).toBe("kr");
  });

  it("CDN 국가 헤더가 비한국이어도 `/`는 한국 서비스다", () => {
    const res = middleware(request("/", { "cf-ipcountry": "US" }));
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  // 2026-09-20 — `/us` 글로벌 서비스 일시 차단(middleware.ts::US_REGION_BLOCKED).
  // 차단을 해제하면 아래 두 테스트를 `/us` rewrite 검증으로 되돌린다:
  //   x-middleware-rewrite = https://www.nullstock.im/pricing, 지역 헤더·쿠키 = us
  it("차단 중에는 `/us` 트리를 없는 경로(404)로 돌려준다", () => {
    const res = middleware(request("/us/pricing", { "accept-language": "ko-KR" }));
    expect(res.headers.get("x-middleware-rewrite")).toBe("https://www.nullstock.im/_not-found");
    expect(res.headers.get("x-middleware-request-" + REGION_HEADER)).toBeNull();
  });

  it("차단 중에는 지역 쿠키에 us를 남기지 않는다", () => {
    const res = middleware(request("/us"));
    expect(res.headers.get("x-middleware-rewrite")).toBe("https://www.nullstock.im/_not-found");
    expect(res.cookies.get(REGION_COOKIE)?.value).toBeUndefined();
  });
});
