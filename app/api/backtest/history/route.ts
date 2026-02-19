import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
  try {
    const history = await prisma.backtestHistory.findMany({
      orderBy: { createdAt: "desc" },
      take: 50,
    });

    const formattedHistory = history.map((item) => ({
      id: item.id,
      timestamp: item.createdAt.getTime(),
      strategyName: item.strategyName,
      universe: item.universe,
      conditions: JSON.parse(item.conditions),
      metrics: JSON.parse(item.metrics),
    }));

    return NextResponse.json(formattedHistory);
  } catch (error) {
    console.error("Failed to fetch backtest history:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { strategyName, universe, conditions, metrics } = body;

    const newItem = await prisma.backtestHistory.create({
      data: {
        strategyName,
        universe,
        conditions: JSON.stringify(conditions),
        metrics: JSON.stringify(metrics),
      },
    });

    return NextResponse.json({
      id: newItem.id,
      timestamp: newItem.createdAt.getTime(),
      strategyName: newItem.strategyName,
      universe: newItem.universe,
      conditions: JSON.parse(newItem.conditions),
      metrics: JSON.parse(newItem.metrics),
    });
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
      await prisma.backtestHistory.delete({
        where: { id },
      });
    } else {
      await prisma.backtestHistory.deleteMany();
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Failed to delete backtest history:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
