import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getOwnershipContext, isUnauthorizedAccessError, withOwnership } from "@/lib/get-user";
import { moneyToNumber } from "@/lib/server/assetService";
import { fetchLivePriceMap, positionsMarketValue } from "@/lib/server/accountValuation";
import { accountTimeZone, dateToTakenAt } from "@/lib/server/accountDailySnapshots";
import { marketDateKey } from "@/app/virtual-account/performanceSeries";
import { totalContributed } from "@/lib/virtual-account/contributions";
import {
  buildReturnSeries,
  isReturnRange,
  RETURN_RANGE_DAYS,
  type ReturnRange,
  type SnapshotPoint,
} from "@/lib/virtual-account/returnSeries";

// GET: 계좌 전체 수익률의 일별 계열 (?range=1m|3m|all, 기본 all) — 저장된 일별 값 + 오늘의 현재 값
export async function GET(request: Request, { params }: { params: { id: string } }) {
  try {
    const { userId } = await getOwnershipContext();
    const account = await prisma.virtualAccount.findFirst({
      where: withOwnership({ id: params.id }, userId),
      include: { VirtualPosition: true },
    });
    if (!account) {
      return NextResponse.json({ error: "Account not found" }, { status: 404 });
    }

    const rangeParam = new URL(request.url).searchParams.get("range");
    const range: ReturnRange = isReturnRange(rangeParam) ? rangeParam : "all";
    const now = new Date();
    const today = marketDateKey(now.toISOString(), accountTimeZone(account.currency));
    const since =
      range === "all"
        ? null
        : dateToTakenAt(marketDateKey(new Date(now.getTime() - RETURN_RANGE_DAYS[range] * 86_400_000).toISOString(), accountTimeZone(account.currency)));

    const rows = await prisma.virtualAccountSnapshot.findMany({
      where: { accountId: account.id, ...(since ? { takenAt: { gte: since } } : {}) },
      orderBy: { takenAt: "asc" },
      select: { takenAt: true, totalValue: true, totalContributed: true },
    });

    // 닫은 계좌는 현금·포지션이 비어 현재 값이 0이라 오늘 점을 붙이지 않는다.
    let todayPoint: SnapshotPoint | undefined;
    if (account.status !== "CLOSED") {
      const priceMap = await fetchLivePriceMap(account.VirtualPosition.map((p) => p.symbol));
      todayPoint = {
        date: today,
        totalValue: moneyToNumber(account.currentCash) + positionsMarketValue(account.VirtualPosition, priceMap),
        totalContributed: totalContributed(account.initialCash, account.contributedCash),
      };
    }

    const points = buildReturnSeries(
      rows.map((s) => ({
        date: s.takenAt.toISOString().slice(0, 10),
        totalValue: moneyToNumber(s.totalValue),
        totalContributed: moneyToNumber(s.totalContributed),
      })),
      todayPoint
    );
    return NextResponse.json({ range, points });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch account return series:", error);
    return NextResponse.json({ error: "Failed to fetch return series" }, { status: 500 });
  }
}
