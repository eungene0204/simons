import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { resolveStrategyPrompt } from "@/lib/strategy-summary";

// 백테스트 기록에는 프롬프트/DSL이 직접 저장되지 않으므로 원천 Strategy(직결
// strategyId 우선, 없으면 동일 이름 전략)에서 SOT를 끌어온다. /analytics/[id]와
// 같은 resolveStrategyPrompt 로직을 써서 두 경로가 같은 프롬프트를 보여준다.
// 워크포워드 실행에 필요한 settings(전략 DSL)도 이 조회에서 함께 얻는다.
async function resolveHistoryStrategy(item: {
  prompt?: string | null;
  strategyId: string | null;
  strategyName: string;
}): Promise<{ prompt: string; settings: any }> {
  const strategy =
    (item.strategyId != null
      ? await prisma.strategy.findUnique({
          where: { id: item.strategyId },
          select: { description: true, settings: true },
        })
      : null) ??
    (await prisma.strategy.findFirst({
      where: { name: item.strategyName },
      orderBy: { createdAt: "desc" },
      select: { description: true, settings: true },
    }));

  let settings: any = null;
  if (strategy) {
    try {
      settings = JSON.parse(strategy.settings);
    } catch {}
  }

  // 기록에 스냅샷된 프롬프트가 있으면 그대로 사용한다(SOT). 구버전 기록만 원천 Strategy로 역추적.
  const snapshot = typeof item.prompt === "string" ? item.prompt.trim() : "";
  const prompt = snapshot || (strategy ? resolveStrategyPrompt(settings, strategy.description) : "");

  return { prompt, settings };
}

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

    const { prompt, settings } = await resolveHistoryStrategy(item);

    return NextResponse.json({
      id: item.id,
      timestamp: item.createdAt.getTime(),
      strategyName: item.strategyName,
      prompt,
      settings,
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
