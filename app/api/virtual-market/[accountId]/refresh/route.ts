/**
 * POST /api/virtual-market/[accountId]/refresh
 *
 * 가상 계좌 시장 새로고침 — 핵심 로직은 lib/server/virtual-market-refresh 에 있고,
 * 이 라우트는 브라우저 호출용 얇은 HTTP 래퍼다.
 * (인-프로세스 스케줄러는 refreshVirtualMarket 를 직접 호출한다.)
 */

import { NextResponse } from "next/server";
import { refreshVirtualMarket } from "@/lib/server/virtual-market-refresh";

export async function POST(
  _request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const result = await refreshVirtualMarket(params.accountId);
    return NextResponse.json(result);
  } catch (error) {
    console.error("Virtual market refresh error:", error);
    return NextResponse.json({ error: "Refresh failed" }, { status: 500 });
  }
}
