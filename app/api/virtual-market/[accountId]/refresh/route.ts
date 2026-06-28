/**
 * POST /api/virtual-market/[accountId]/refresh
 *
 * 가상 계좌 시장 새로고침(표시 전용) — 핵심 로직은 lib/server/virtual-market-refresh 에 있고,
 * 이 라우트는 브라우저 호출용 얇은 HTTP 래퍼다. 가격/포지션 표시만 갱신하며 매매는
 * 하지 않는다 — 자동매매 체결의 정본은 백엔드 VirtualTrader 단일 엔진이다.
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
