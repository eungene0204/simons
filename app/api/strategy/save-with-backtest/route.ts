import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { inferStrategyType } from "@/lib/strategy-type";
import { buildBacktestResultSummary } from "@/lib/server/backtestResultSummary";
import { computeStrategyIdFromDsl, triggerVectorMemoryBacktestUpsert } from "@/lib/server/backtestCache";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
} from "@/lib/get-user";
import {
  assertCanSaveStrategy,
  PLAN_LIMIT_MESSAGES,
  PLAN_LIMIT_STRATEGIES,
} from "@/lib/server/planLimits";

function buildOwnedStrategyId(userId: number | null, dsl: any) {
  const baseId = computeStrategyIdFromDsl(dsl);
  return userId == null ? baseId : `${userId}:${baseId}`;
}

// POST: 전략 DSL + 백테스트 결과를 한 번에 저장
export async function POST(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const body = await request.json();
    const {
      name,
      description,
      dsl,
      backtestResult,
      aiSummary,
      aiScore,
      aiStrengths,
      aiWeaknesses,
      aiImprovements,
      aiRisks,
      advisorScore,
      riskScore,
      overfitRisk,
      score,
    } = body;

    if (!name?.trim()) {
      return NextResponse.json({ error: "전략 이름을 입력해주세요." }, { status: 400 });
    }
    if (!dsl) {
      return NextResponse.json({ error: "전략 설정 정보가 없습니다." }, { status: 400 });
    }

    const strategyId = buildOwnedStrategyId(userId, dsl);

    // 중복 저장 차단: strategyId 는 DSL(이름/설명/타임스탬프 제외)을 정규화해 해시한 값이므로
    // DSL 이 완전히 같으면 이름이 달라도 동일한 strategyId 가 된다. 이미 다른 이름으로 저장된
    // 전략이 있으면 새 이름으로 덮어쓰지 않고 저장을 막는다(같은 이름 재저장은 갱신으로 허용).
    const existing =
      typeof prisma.strategy?.findUnique === "function"
        ? await prisma.strategy.findUnique({ where: { id: strategyId } })
        : null;
    const isAlreadySaved = existing != null && existing.isSaved && existing.deletedAt == null;
    if (isAlreadySaved && existing.name.trim() !== name.trim()) {
      return NextResponse.json(
        {
          error: `이미 저장된 '${existing.name}' 전략과 같은 전략이라 저장하지 못했습니다.`,
          duplicate: true,
          existingStrategyId: existing.id,
          existingStrategyName: existing.name,
        },
        { status: 409 }
      );
    }

    // 신규 저장(이미 저장된 전략의 갱신이 아닌 경우)만 플랜의 저장 전략 수 한도를 검사한다.
    // 결과 화면의 "저장" 버튼이 이 라우트를 쓰므로, 여기서 빠지면 한도가 사실상 없는 것과 같다.
    if (userId != null && !isAlreadySaved) {
      await assertCanSaveStrategy(prisma, userId);
    }

    // 전략 DSL에 이름/설명 반영
    const dslToSave = {
      ...dsl,
      id: strategyId,
      name: name.trim(),
      description: description?.trim() || "",
      updated_at: new Date().toISOString(),
    };

    const strategyType = inferStrategyType(name.trim(), description?.trim() ?? "", dsl);

    // Strategy + BacktestResult 트랜잭션으로 함께 저장
    const result = await prisma.$transaction(async (tx) => {
      const strategy =
        typeof tx.strategy.upsert === "function"
          ? await tx.strategy.upsert({
              where: { id: strategyId },
              create: {
                id: strategyId,
                ...(userId != null && { userId }),
                name: name.trim(),
                description: description?.trim() || null,
                settings: JSON.stringify(dslToSave),
                strategyType,
                isSaved: true,
              },
              update: {
                ...(userId != null && { userId }),
                name: name.trim(),
                description: description?.trim() || null,
                settings: JSON.stringify(dslToSave),
                strategyType,
                isSaved: true,
                deletedAt: null,
              },
            })
          : await tx.strategy.create({
              data: {
                id: strategyId,
                ...(userId != null && { userId }),
                name: name.trim(),
                description: description?.trim() || null,
                settings: JSON.stringify(dslToSave),
                strategyType,
                isSaved: true,
              },
            });

      let backtestRecord = null;
      if (backtestResult) {
        const summary = buildBacktestResultSummary(backtestResult, {
          score,
          aiSummary,
          aiScore,
          aiStrengths,
          aiWeaknesses,
          aiImprovements,
          aiRisks,
          advisorScore,
          riskScore,
          overfitRisk,
        });

        if (
          typeof tx.backtestResult.findFirst === "function" &&
          typeof tx.backtestResult.update === "function"
        ) {
          const existingBacktestRecord = await tx.backtestResult.findFirst({
            where: { strategyId: strategy.id },
            orderBy: { createdAt: "desc" },
          });

          if (existingBacktestRecord) {
            backtestRecord = await tx.backtestResult.update({
              where: { id: existingBacktestRecord.id },
              data: {
                summary: JSON.stringify(summary),
                trades: JSON.stringify(backtestResult.tradesList ?? []),
              },
            });
          } else {
            backtestRecord = await tx.backtestResult.create({
              data: {
                strategyId: strategy.id,
                summary: JSON.stringify(summary),
                trades: JSON.stringify(backtestResult.tradesList ?? []),
              },
            });
          }
        } else {
          backtestRecord = await tx.backtestResult.create({
            data: {
              strategyId: strategy.id,
              summary: JSON.stringify(summary),
              trades: JSON.stringify(backtestResult.tradesList ?? []),
            },
          });
        }

        const metrics = {
          totalReturn: backtestResult.totalReturn ?? 0,
          cagr: backtestResult.cagr ?? 0,
          mdd: backtestResult.maxDrawdown ?? 0,
          winRate: backtestResult.winRate ?? 0,
          profitFactor: backtestResult.profitFactor ?? null,
          buyHold: backtestResult.buyAndHoldReturn ?? 0,
          trades: backtestResult.trades ?? 0,
          executionTime: backtestResult.executionTime ?? 0,
          score: score ?? null,
          aiSummary: aiSummary ?? null,
          aiScore: aiScore ?? null,
          aiStrengths: aiStrengths ?? [],
          aiWeaknesses: aiWeaknesses ?? [],
          aiImprovements: aiImprovements ?? [],
          aiRisks: aiRisks ?? [],
          advisorScore: advisorScore ?? null,
          riskScore: riskScore ?? null,
          overfitRisk: overfitRisk ?? null,
          perAssetStats: backtestResult.perAssetStats ?? null,
          topSymbols: summary.topSymbols,
        };

        if (tx.backtestHistory) {
          const existingHistory =
            backtestResult.cacheKey && typeof tx.backtestHistory.findUnique === "function"
              ? await tx.backtestHistory.findUnique({ where: { cacheKey: backtestResult.cacheKey } })
              : typeof tx.backtestHistory.findFirst === "function"
                ? await tx.backtestHistory.findFirst({
                    where: { strategyId: strategy.id },
                    orderBy: { createdAt: "desc" },
                  })
                : null;

          const historyData = {
            strategyId: strategy.id,
            strategyName: name.trim(),
            universe: dslToSave?.universe?.id ?? (backtestResult.symbols ?? []).slice(0, 3).join(","),
            conditions: JSON.stringify({ entry: dslToSave.entry ?? null, exit: dslToSave.exit ?? null }),
            metrics: JSON.stringify(metrics),
            result: JSON.stringify({
              ...backtestResult,
              strategyId: strategy.id,
            }),
            cacheKey: backtestResult.cacheKey ?? strategy.id,
            isVisible: true,
          };

          let savedHistory: { id: string } | null = null;
          if (existingHistory && typeof tx.backtestHistory.update === "function") {
            savedHistory = await tx.backtestHistory.update({
              where: { id: existingHistory.id },
              data: historyData,
            });
          } else if (typeof tx.backtestHistory.create === "function") {
            savedHistory = await tx.backtestHistory.create({
              data: historyData,
            });
          }

          // 저장한 백테스트를 로그인 사용자의 "내 목록"에 연결한다.
          if (
            userId != null &&
            savedHistory &&
            tx.userBacktestHistory &&
            typeof tx.userBacktestHistory.upsert === "function"
          ) {
            await tx.userBacktestHistory.upsert({
              where: { userId_backtestHistoryId: { userId, backtestHistoryId: savedHistory.id } },
              create: { userId, backtestHistoryId: savedHistory.id },
              update: {},
            });
          }
        }
      }

      return { strategy, backtestRecord };
    }, {
      // 원격 Supabase(us-west-1) 왕복 지연 + 대형 유니버스 결과(수천 종목 perAssetStats·
      // equity 곡선을 summary/result JSON으로 두 번 업로드)로 기본 5초를 초과한다 —
      // 2701종목 저장이 트랜잭션 내부만 6초를 넘어 "Transaction already closed"로 실패했다.
      maxWait: 10_000,
      timeout: 60_000,
    });

    if (result.backtestRecord) {
      triggerVectorMemoryBacktestUpsert();
    }

    return NextResponse.json({
      strategyId: result.strategy.id,
      backtestResultId: result.backtestRecord?.id ?? null,
      message: "전략과 백테스트 결과가 저장되었습니다.",
    });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (error instanceof Error && error.message === PLAN_LIMIT_STRATEGIES) {
      return NextResponse.json(
        {
          error: "Strategy limit reached",
          code: PLAN_LIMIT_STRATEGIES,
          message: PLAN_LIMIT_MESSAGES[PLAN_LIMIT_STRATEGIES],
        },
        { status: 403 }
      );
    }
    console.error("Failed to save strategy with backtest:", error);
    return NextResponse.json(
      { error: "저장에 실패했습니다." },
      { status: 500 }
    );
  }
}
