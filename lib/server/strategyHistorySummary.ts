import { prisma } from "@/lib/prisma";
import { buildHistorySummary, historySummaryHasContent } from "@/lib/backtest-history";

// 전략 상세(소유자 API)와 공개 계좌 열람 API가 함께 쓰는 백테스트 기록 요약 조회.

function parseJsonField(value: string | null | undefined, fallback: any) {
  if (!value) return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function historyToSummary(history: any, settings?: Record<string, unknown> | null) {
  if (!history) return null;
  const conditions = parseJsonField(history.conditions, {});
  // 기간·초기 자본은 conditions(2026-08-18부터 저장)에서, 그 전 행은 원천 Strategy.settings
  // (실행 요청과 같은 키: period/startDate/endDate/risk.init_cash)에서 되살린다.
  const summary = buildHistorySummary({
    conditions,
    universeName: history.universe,
    strategyName: history.strategyName,
    executedRequest: settings ?? null,
  });
  // 표시용 배지를 만들지 못하는 행(raw DSL conditions만 가진 save-with-backtest 행 등)은
  // SOT로 채택하지 않고 다음 후보(표시용 names를 가진 auto-save 행)로 넘긴다.
  if (!historySummaryHasContent(summary)) return null;

  return { id: history.id, ...summary, conditions };
}

export async function findBacktestHistorySummary(
  strategy: any,
  strategyId: string,
  userId: number | null,
  settings: Record<string, unknown> | null
) {
  const directHistory = await prisma.backtestHistory.findFirst({
    where: { OR: [{ strategyId }, { cacheKey: strategyId }] },
    orderBy: { createdAt: "desc" },
  });
  const directSummary = historyToSummary(directHistory, settings);
  if (directSummary) return directSummary;

  if (userId != null) {
    const userHistoryLink = await prisma.userBacktestHistory.findFirst({
      where: {
        userId,
        BacktestHistory: {
          strategyName: strategy.name,
          isVisible: true,
        },
      },
      orderBy: { savedAt: "desc" },
      include: { BacktestHistory: true },
    });
    const userSummary = historyToSummary(userHistoryLink?.BacktestHistory, settings);
    if (userSummary) return userSummary;
  }

  // 전략 이름만으로 전역 BacktestHistory를 뒤지던 마지막 폴백은 제거했다(2026-09-11).
  // 이름이 겹치기만 하면 남의 기록 id와 조건이 응답에 실려 나갔고, 그 id로
  // /api/backtest/history/[id]를 부르면 남의 결과 본문까지 열렸다.
  return null;
}
