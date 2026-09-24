import { prisma } from "@/lib/prisma";

/**
 * 내 전략 버전 이력(2026-09-23).
 *
 * `Strategy.id`는 DSL 해시라 전략 내용을 고치면 **다른 행**이 된다(같은 행이 갱신되지 않는다).
 * 그래서 이력은 사용자가 '같은 전략'이라고 여기는 단위, 즉 사용자+이름으로 묶는다.
 * 같은 설정을 다시 저장하면 새 버전을 만들지 않는다 — 누르는 횟수만큼 이력이 불어나면 읽을 수 없다.
 */
export function lineageKeyFor(userId: number | null, name: string): string {
  return `${userId ?? "anon"}::${name.trim()}`;
}

export interface StrategyVersionRow {
  id: string;
  version: number;
  strategyId: string;
  name: string;
  description: string | null;
  createdAt: string;
  isCurrent: boolean;
}

/** 저장 시 호출 — 직전 버전과 설정이 다를 때만 한 줄 남긴다. 실패해도 저장 자체는 막지 않는다. */
export async function recordStrategyVersion(params: {
  userId: number | null;
  strategyId: string;
  name: string;
  description: string | null;
  settings: string;
}): Promise<void> {
  const lineageKey = lineageKeyFor(params.userId, params.name);
  try {
    const latest = await prisma.strategyVersion.findFirst({
      where: { lineageKey },
      orderBy: { version: "desc" },
      select: { version: true, settings: true },
    });
    if (latest?.settings === params.settings) return;
    await prisma.strategyVersion.create({
      data: {
        userId: params.userId ?? undefined,
        lineageKey,
        strategyId: params.strategyId,
        version: (latest?.version ?? 0) + 1,
        name: params.name,
        description: params.description,
        settings: params.settings,
      },
    });
  } catch (error) {
    // 이력은 부가 기능이다 — 실패가 전략 저장을 막으면 안 된다(사용자가 작업을 잃는다).
    console.error("Failed to record strategy version:", error);
  }
}

export async function listStrategyVersions(
  userId: number | null,
  name: string,
  currentStrategyId: string | null,
): Promise<StrategyVersionRow[]> {
  const rows = await prisma.strategyVersion.findMany({
    where: { lineageKey: lineageKeyFor(userId, name) },
    orderBy: { version: "desc" },
    take: 50,
    select: { id: true, version: true, strategyId: true, name: true, description: true, createdAt: true },
  });
  return rows.map((row) => ({
    id: row.id,
    version: row.version,
    strategyId: row.strategyId,
    name: row.name,
    description: row.description,
    createdAt: row.createdAt.toISOString(),
    isCurrent: currentStrategyId != null && row.strategyId === currentStrategyId,
  }));
}
