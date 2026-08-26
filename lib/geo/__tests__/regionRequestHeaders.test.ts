// regionRequestHeaders — 백엔드행 API fetch에 싣는 지역 헤더는 **호출한 탭의 경로**에서
// 파생한다. API 라우트는 미들웨어 밖이라 '마지막 방문 지역' 전역 쿠키로만 폴백했는데,
// KR/US 탭을 오가면 /us 탭의 호출이 kr로 오염됐다(2026-08-26 — /us "hello"에 한국어 인사).
import { afterEach, describe, expect, it } from "vitest";
import { REGION_HEADER } from "@/lib/geo/region";
import { regionRequestHeaders } from "@/lib/geo/useRegion";

describe("regionRequestHeaders", () => {
  afterEach(() => {
    window.history.pushState({}, "", "/");
  });

  it("/us 트리에서는 us 헤더를 싣는다", () => {
    window.history.pushState({}, "", "/us/analytics/new");
    expect(regionRequestHeaders()).toEqual({ [REGION_HEADER]: "us" });
  });

  it("한국 트리에서는 kr 헤더를 싣는다 — 쿠키가 아니라 경로가 정본", () => {
    window.history.pushState({}, "", "/analytics/new");
    expect(regionRequestHeaders()).toEqual({ [REGION_HEADER]: "kr" });
  });

  it("/user처럼 프리픽스가 낱말 경계가 아니면 kr이다", () => {
    window.history.pushState({}, "", "/user");
    expect(regionRequestHeaders()).toEqual({ [REGION_HEADER]: "kr" });
  });
});
