import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { resolveTrackedSymbolsForStrategy } from '@/lib/strategy-tracked-symbols';
import { createFundedAccount, moneyToNumber, toMoney } from '@/lib/server/assetService';
import { fetchLivePriceMap, positionsMarketValue } from '@/lib/server/accountValuation';
import { getPlan } from '@/lib/plans';
import { getRequestRegion } from '@/lib/geo/server';
import { US_PRICING } from '@/lib/pricing/us';
import { contributionStartCapital, totalContributed } from '@/lib/virtual-account/contributions';
import {
  assertCanCreateAccount,
  getUserPlan,
  PLAN_LIMIT_ACCOUNTS,
  PLAN_LIMIT_MESSAGES,
  planUpgradeHref,
  recordAccountLimitHit,
} from '@/lib/server/planLimits';
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from '@/lib/get-user';

function mapAccount(a: any, priceMap: Record<string, number>) {
  const currentCash = moneyToNumber(a.currentCash);
  const positions = a.VirtualPosition ?? [];
  const holdingsValue = positionsMarketValue(positions, priceMap);
  const holdingsCost = positions.reduce(
    (sum: number, p: any) => sum + p.quantity * moneyToNumber(p.avgPrice),
    0
  );
  const totalValue = currentCash + holdingsValue;
  return {
    id: a.id,
    name: a.name,
    initialAmount: moneyToNumber(a.initialCash),
    totalContributed: totalContributed(a.initialCash, a.contributedCash),
    currency: (a.currency ?? "KRW") as "KRW" | "USD",
    currentBalance: currentCash,
    totalValue,
    holdingsCost,
    holdingsProfit: holdingsValue - holdingsCost,
    status: a.status ?? "ACTIVE",
    strategyId: a.strategyId ?? undefined,
    strategyName: a.strategyName ?? undefined,
    tradingMode: (a.tradingMode ?? "manual") as "auto" | "manual",
    isPublic: a.isPublic === true,
    createdAt: a.createdAt.toISOString(),
    updatedAt: a.updatedAt.toISOString(),
  };
}

// GET: 모든 가상계좌 목록
export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    const accounts = await prisma.virtualAccount.findMany({
      where: withOwnership({ status: "ACTIVE" }, userId),
      include: { VirtualPosition: true },
      orderBy: { createdAt: 'desc' },
    });

    const priceMap = await fetchLivePriceMap(
      accounts.flatMap((account) => account.VirtualPosition.map((position) => position.symbol))
    );

    return NextResponse.json(accounts.map((account) => mapAccount(account, priceMap)));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    console.error('Failed to fetch virtual accounts:', error);
    return NextResponse.json({ error: 'Failed to fetch accounts' }, { status: 500 });
  }
}

// POST: 가상계좌 생성
export async function POST(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const { name, strategyId, strategyName, tradingMode } = await request.json();

    if (!name) {
      return NextResponse.json(
        { error: 'name is required' },
        { status: 400 }
      );
    }

    const strategy = strategyId
      ? userId == null
        ? await prisma.strategy.findUnique({
            where: { id: strategyId },
          })
        : await prisma.strategy.findFirst({
            where: withOwnership({ id: strategyId }, userId),
          })
      : null;
    // 남의 전략·없는 전략은 연결하지 않는다 — 찾지 못한 id를 그대로 저장하던 구멍(2026-11-17).
    if (strategyId && !strategy) {
      return NextResponse.json({ error: 'Strategy not found' }, { status: 404 });
    }

    // 초기 투자금은 사용자의 현재 플랜에서 서버가 결정한다(클라이언트 금액 무시).
    // 비로그인은 FREE 플랜 기준. /us 요청은 미국 가격표(USD 모의 자금)로 시드하고
    // 계좌 통화를 USD로 기록한다 — 금액 숫자는 계좌 통화 단위 그대로다(2026-08-26).
    const plan = userId == null ? getPlan("FREE") : await getUserPlan(prisma, userId);
    const region = getRequestRegion();
    const currency = region === "us" ? "USD" : "KRW";
    const planAmount =
      region === "us"
        ? US_PRICING.initialInvestmentAmount[plan.planId]
        : plan.initialInvestmentAmount;
    // 정액 적립식 전략(2026-09-21): 플랜 투자금 전액으로 시작하면 납입할 여유가 없다 — 전략의 초기
    // 자본으로 시작하고, 초기 자본 + 누적 납입이 플랜 투자금을 넘지 않게 상한을 계좌에 적는다.
    const contributionStart = contributionStartCapital(strategy?.settings, planAmount);
    const amount = contributionStart ?? planAmount;
    const contributionCap = contributionStart == null ? null : planAmount;

    const account =
      userId == null
        ? await prisma.virtualAccount.create({
            data: {
              id: crypto.randomUUID(),
              name,
              initialCash: toMoney(amount),
              currentCash: toMoney(amount),
              currency,
              contributionCap: contributionCap == null ? null : toMoney(contributionCap),
              status: "ACTIVE",
              strategyId: strategy?.id ?? null,
              strategyName: strategyName || null,
              tradingMode: tradingMode || "manual",
              updatedAt: new Date(),
            },
            include: { VirtualPosition: true },
          })
        : await prisma.$transaction(async (tx) => {
            await assertCanCreateAccount(tx, userId);
            return createFundedAccount(tx, {
              userId,
              name,
              initialAmount: amount,
              currency,
              contributionCap,
              strategyId: strategy?.id ?? null,
              strategyName: strategyName || null,
              tradingMode: tradingMode || "manual",
            });
          }).catch(async (error) => {
            // 한도 도달은 롤백 뒤 트랜잭션 밖에서 기록한다(KPI '한도 도달 → 전환율'의 분모).
            if (error instanceof Error && error.message === PLAN_LIMIT_ACCOUNTS) {
              await recordAccountLimitHit(prisma, userId);
            }
            throw error;
          });

    if (strategy) {
      const resolved = await resolveTrackedSymbolsForStrategy({
        strategyId,
        strategyName: strategy.name,
        strategySettings: strategy.settings,
        currency,
      });

      if (resolved.symbols.length > 0) {
        const today = new Date().toISOString().split("T")[0];
        await prisma.virtualMarketState.upsert({
          where: { accountId: account.id },
          create: {
            id: crypto.randomUUID(),
            accountId: account.id,
            startDate: today,
            status: tradingMode === "auto" ? "running" : "paused",
            symbols: JSON.stringify(resolved.symbols),
            updatedAt: new Date(),
          },
          update: {
            startDate: today,
            status: tradingMode === "auto" ? "running" : "paused",
            symbols: JSON.stringify(resolved.symbols),
            updatedAt: new Date(),
          },
        });
      }
    }

    return NextResponse.json(mapAccount(account, {}));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    if (error instanceof Error && error.message === PLAN_LIMIT_ACCOUNTS) {
      return NextResponse.json(
        { error: 'Account limit reached', code: PLAN_LIMIT_ACCOUNTS, message: PLAN_LIMIT_MESSAGES[PLAN_LIMIT_ACCOUNTS], upgradeHref: planUpgradeHref(PLAN_LIMIT_ACCOUNTS) },
        { status: 403 }
      );
    }
    console.error('Failed to create virtual account:', error);
    return NextResponse.json({ error: 'Failed to create account' }, { status: 500 });
  }
}
