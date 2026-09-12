import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { StrategyDSL } from '@/types/strategy';
import { inferStrategyType } from '@/lib/strategy-type';
import { computeStrategyIdFromDsl } from '@/lib/server/backtestCache';
import { getOwnershipContext, isUnauthorizedAccessError } from '@/lib/get-user';
import {
  assertCanSaveStrategy,
  PLAN_LIMIT_STRATEGIES,
  PLAN_LIMIT_MESSAGES,
} from '@/lib/server/planLimits';
import { buildBacktestResultSummary } from '@/lib/server/backtestResultSummary';

/**
 * 이 경로로 저장된 전략도 저장 전략 목록에 그대로 뜨므로, 실행한 백테스트 결과를 함께
 * 남긴다(없으면 /analytics/[id] 가 "저장된 백테스트 결과가 없습니다"로 떨어진다).
 * 이미 결과 행이 있으면 건드리지 않는다 — AI 리포트까지 붙여 저장한 행을 계좌 생성
 * 시점의 가벼운 결과로 덮어쓰지 않기 위해서다.
 */
async function persistBacktestResult(strategyId: string, backtestResult: any) {
  if (!backtestResult) return;

  const existingRecord = await prisma.backtestResult.findFirst({
    where: { strategyId },
    orderBy: { createdAt: 'desc' },
  });
  if (existingRecord) return;

  await prisma.backtestResult.create({
    data: {
      strategyId,
      summary: JSON.stringify(buildBacktestResultSummary(backtestResult)),
      trades: JSON.stringify(backtestResult.tradesList ?? []),
    },
  });
}

/**
 * 백테스트 결과에서 곧바로 가상계좌를 만들 때 쓰는 "있으면 그대로, 없으면 저장" 경로.
 *
 * 가상계좌는 Strategy 행을 참조해야 추적 종목·자동매매 신호가 붙으므로, 아직 저장하지 않은
 * 백테스트 전략은 계좌 생성 전에 한 번 저장돼야 한다. 이때 POST /api/strategy 는 이름까지
 * 덮어쓰기 때문에, 사용자가 이미 자기 이름으로 저장해 둔 같은 DSL 의 전략을 백테스트 요약
 * 이름으로 개명해 버린다. 이 라우트는 기존 행이 있으면 이름을 건드리지 않고 그대로 돌려준다.
 */
export async function POST(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const { name, description, dsl, backtestResult } = (await request.json()) as {
      name?: string;
      description?: string;
      dsl?: StrategyDSL;
      backtestResult?: any;
    };

    if (!name?.trim()) {
      return NextResponse.json({ error: '전략 이름이 필요합니다.' }, { status: 400 });
    }
    if (!dsl) {
      return NextResponse.json({ error: '전략 설정 정보가 없습니다.' }, { status: 400 });
    }

    const baseId = computeStrategyIdFromDsl(dsl);
    const strategyId = userId == null ? baseId : `${userId}:${baseId}`;

    const existing = await prisma.strategy.findUnique({ where: { id: strategyId } });
    if (existing && existing.isSaved && existing.deletedAt == null) {
      await persistBacktestResult(existing.id, backtestResult);
      return NextResponse.json({ id: existing.id, name: existing.name, created: false });
    }

    if (userId != null) await assertCanSaveStrategy(prisma, userId);

    const strategyName = name.trim();
    const strategyDescription = description?.trim() || '';
    const strategyType = inferStrategyType(strategyName, strategyDescription, dsl);
    const settings = JSON.stringify({
      ...dsl,
      id: strategyId,
      name: strategyName,
      description: strategyDescription,
    });

    const strategy = await prisma.strategy.upsert({
      where: { id: strategyId },
      create: {
        id: strategyId,
        ...(userId != null && { userId }),
        name: strategyName,
        description: strategyDescription || null,
        settings,
        strategyType,
        isSaved: true,
      },
      update: {
        ...(userId != null && { userId }),
        name: strategyName,
        description: strategyDescription || null,
        settings,
        strategyType,
        isSaved: true,
        deletedAt: null,
      },
    });

    await persistBacktestResult(strategy.id, backtestResult);

    return NextResponse.json({ id: strategy.id, name: strategy.name, created: true });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    if (error instanceof Error && error.message === PLAN_LIMIT_STRATEGIES) {
      return NextResponse.json(
        {
          error: 'Strategy limit reached',
          code: PLAN_LIMIT_STRATEGIES,
          message: PLAN_LIMIT_MESSAGES[PLAN_LIMIT_STRATEGIES],
        },
        { status: 403 }
      );
    }
    console.error('Failed to ensure strategy:', error);
    return NextResponse.json({ error: 'Failed to ensure strategy' }, { status: 500 });
  }
}
