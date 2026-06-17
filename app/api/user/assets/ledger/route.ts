import { NextResponse } from "next/server";
import { getOwnershipContext, isUnauthorizedAccessError } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";

export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    if (userId == null) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const entries = await prisma.assetLedger.findMany({
      where: { userId },
      orderBy: { createdAt: "desc" },
      take: 100,
    });

    return NextResponse.json({
      entries: entries.map((entry) => ({
        id: entry.id,
        userId: entry.userId,
        accountId: entry.accountId,
        type: entry.type,
        amount: entry.amount.toNumber(),
        balanceAfter: entry.balanceAfter.toNumber(),
        createdAt: entry.createdAt.toISOString(),
      })),
    });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch asset ledger:", error);
    return NextResponse.json({ error: "Failed to fetch asset ledger" }, { status: 500 });
  }
}
