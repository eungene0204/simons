import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

function formatItem(item: any) {
  return {
    id: item.id,
    timestamp: item.createdAt.getTime(),
    strategyName: item.strategyName,
    universe: item.universe,
    conditions: JSON.parse(item.conditions),
    metrics: JSON.parse(item.metrics),
    result: item.result ? JSON.parse(item.result) : undefined,
  };
}

// 저장 목록: isVisible=true 인 항목만 반환
export async function GET() {
  try {
    const history = await prisma.backtestHistory.findMany({
      where: { isVisible: true },
      orderBy: { createdAt: "desc" },
      take: 50,
    });
    return NextResponse.json(history.map(formatItem));
  } catch (error) {
    console.error("Failed to fetch backtest history:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

// 저장 버튼 클릭 시 호출
// cacheKey 가 있으면 기존 숨김 레코드를 isVisible=true 로 업데이트,
// 없거나 레코드가 없으면 새로 생성
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { strategyName, universe, conditions, metrics, result, cacheKey } = body;

    if (cacheKey) {
      const existing = await prisma.backtestHistory.findUnique({ where: { cacheKey } });
      if (existing) {
        const updated = await prisma.backtestHistory.update({
          where: { cacheKey },
          data: {
            strategyName,
            universe,
            conditions: JSON.stringify(conditions),
            metrics: JSON.stringify(metrics),
            result: result ? JSON.stringify(result) : existing.result,
            isVisible: true,
          },
        });
        return NextResponse.json(formatItem(updated));
      }
    }

    // cacheKey 없거나 레코드 없을 때 새 레코드 생성
    const newItem = await prisma.backtestHistory.create({
      data: {
        strategyName,
        universe,
        conditions: JSON.stringify(conditions),
        metrics: JSON.stringify(metrics),
        result: result ? JSON.stringify(result) : null,
        cacheKey: cacheKey ?? null,
        isVisible: true,
      },
    });
    return NextResponse.json(formatItem(newItem));
  } catch (error) {
    console.error("Failed to save backtest history:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get("id");

    if (id) {
      await prisma.backtestHistory.delete({ where: { id } });
    } else {
      await prisma.backtestHistory.deleteMany({ where: { isVisible: true } });
    }
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Failed to delete backtest history:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
