import { prisma } from "@/lib/prisma";
import { assertActiveUser } from "@/lib/get-user";
import type { BacktestHistoryItem } from "@/types/strategy";

// 목록 카드는 result(자산곡선·전체 거래내역이 담긴 대용량 JSON blob)를 쓰지 않는다.
// 50개 기록의 result까지 읽어 파싱/전송하면 응답이 수 MB로 불어나 로딩이 크게 지연되므로,
// 목록 조회에서는 카드가 실제로 쓰는 컬럼만 select 하고 result는 제외한다.
export const BACKTEST_LIST_SELECT = {
  id: true,
  createdAt: true,
  strategyName: true,
  universe: true,
  conditions: true,
  metrics: true,
} as const;

export function formatBacktestListItem(item: any): BacktestHistoryItem {
  return {
    id: item.id,
    timestamp: item.createdAt.getTime(),
    strategyName: item.strategyName,
    universe: item.universe,
    conditions: JSON.parse(item.conditions),
    metrics: JSON.parse(item.metrics),
  };
}

// 로그인 사용자가 자신의 목록에 담은 기록(UserBacktestHistory 조인)만 최신순 50개.
// /api/backtest/history GET과 /backtest 서버 렌더가 같은 조회를 공유한다.
// 원격 DB 왕복을 줄이기 위해 계정 상태 검증과 목록 조회를 병렬로 실행한다.
export async function fetchUserBacktestHistory(
  userId: number
): Promise<BacktestHistoryItem[]> {
  const [, links] = await Promise.all([
    assertActiveUser(userId),
    prisma.userBacktestHistory.findMany({
      where: { userId },
      orderBy: { savedAt: "desc" },
      take: 50,
      select: { BacktestHistory: { select: BACKTEST_LIST_SELECT } },
    }),
  ]);
  return links.map((link) => formatBacktestListItem(link.BacktestHistory));
}
