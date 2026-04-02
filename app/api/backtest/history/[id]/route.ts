import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const item = await prisma.backtestHistory.findUnique({
      where: { id: params.id },
    });

    if (!item) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    return NextResponse.json({
      id: item.id,
      timestamp: item.createdAt.getTime(),
      strategyName: item.strategyName,
      universe: item.universe,
      conditions: JSON.parse(item.conditions),
      metrics: JSON.parse(item.metrics),
      result: item.result ? JSON.parse(item.result) : undefined,
    });
  } catch (error) {
    console.error("Failed to fetch backtest history item:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
