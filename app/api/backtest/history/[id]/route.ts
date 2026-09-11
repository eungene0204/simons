import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  assertActiveUser,
  getSessionUserId,
  isUnauthorizedAccessError,
} from "@/lib/get-user";
import { resolveStrategyPrompt } from "@/lib/strategy-summary";

// 백테스트 기록에는 프롬프트/DSL이 직접 저장되지 않으므로 원천 Strategy(직결
// strategyId 우선, 없으면 동일 이름 전략)에서 SOT를 끌어온다. /analytics/[id]와
// 같은 resolveStrategyPrompt 로직을 써서 두 경로가 같은 프롬프트를 보여준다.
// 워크포워드 실행에 필요한 settings(전략 DSL)도 이 조회에서 함께 얻는다.
async function resolveHistoryStrategy(
  item: {
    prompt?: string | null;
    strategyId: string | null;
    strategyName: string;
  },
  userId: number
): Promise<{ prompt: string; settings: any }> {
  const strategy =
    (item.strategyId != null
      ? await prisma.strategy.findUnique({
          where: { id: item.strategyId },
          select: { description: true, settings: true },
        })
      : null) ??
    // 이름만으로 전역을 뒤지면 이름이 겹치는 남의 전략 원문·DSL이 딸려 나온다.
    // 백테스트가 자동 생성한 전략 행은 주인이 없으므로(userId=null) 그것과
    // 요청자 본인 전략만 후보로 둔다.
    (await prisma.strategy.findFirst({
      where: {
        name: item.strategyName,
        OR: [{ userId: null }, { userId }],
      },
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
    // 기록 본문에는 사용자가 입력한 원문 프롬프트·전략 DSL·전체 거래 내역이 들어 있다.
    // BacktestHistory 자체는 cacheKey 기준 공유 행이므로, 자기 목록(UserBacktestHistory)에
    // 담은 사람만 열 수 있다. 남의 기록은 존재 여부도 알리지 않고 404로 답한다.
    const userId = await getSessionUserId();
    if (userId == null) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // 원격 DB 왕복을 줄이려고 계정 상태 검증·소유 확인·본문 조회를 함께 실행한다.
    const [, link, item] = await Promise.all([
      assertActiveUser(userId),
      prisma.userBacktestHistory.findUnique({
        where: {
          userId_backtestHistoryId: { userId, backtestHistoryId: params.id },
        },
        select: { id: true },
      }),
      prisma.backtestHistory.findUnique({
        where: { id: params.id },
      }),
    ]);

    if (!link || !item) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const { prompt, settings } = await resolveHistoryStrategy(item, userId);

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
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch backtest history item:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
