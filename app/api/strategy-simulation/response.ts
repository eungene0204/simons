import { NextResponse } from "next/server";

// 공개 철회가 브라우저·CDN 캐시로 남지 않게 모든 응답에 no-store를 붙인다.
export function noStoreJson(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "no-store", ...headers } });
}

export const PUBLIC_ID_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;
