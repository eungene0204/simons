// 수익 퍼널 집계(2026-11-26) — 관리자 콘솔 개요가 쓴다.
//
// ① 한도 도달 → 14일 안 유료 전환(docs/KPI.md §4.5 '한도 도달 → 전환율')
// ② 가입 유입 경로(first-touch UTM)별 가입 → 첫 백테스트 → 유료 결제
//
// 집계는 DB가 이미 기록한 구조화 값(PlanLimitHit·User·PaymentOrder)만 쓴다 — 사용자 문장은 읽지 않는다.
// 계산은 순수 함수로 두고(테스트 가능), 조회는 loadRevenueFunnel 한 곳에서 한다.

export const FUNNEL_WINDOW_DAYS = 30;
export const LIMIT_CONVERSION_DAYS = 14;
const DAY_MS = 24 * 60 * 60 * 1000;

/** 유입 경로가 없는 가입(직접 방문·UTM 없는 링크·기록 도입 전 가입) */
export const DIRECT_SOURCE = "(direct)";

export interface LimitHitRow {
  userId: number;
  code: string;
  createdAt: Date;
}

export interface PaidOrderRow {
  userId: number;
  createdAt: Date;
}

export interface LimitConversion {
  /** 기간 안에 한도에 한 번이라도 막힌 사용자 수 */
  users: number;
  /** 그중 첫 도달 뒤 14일 안에 결제를 완료한 사용자 수 */
  converted: number;
  /** 한도별 도달 사용자 수 */
  byCode: Record<string, number>;
}

/** 사용자별 첫 도달 시각 기준으로, 그 뒤 14일 안에 결제(DONE)가 있으면 전환으로 센다. */
export function computeLimitConversion(
  hits: LimitHitRow[],
  paidOrders: PaidOrderRow[]
): LimitConversion {
  const firstHit = new Map<number, Date>();
  const usersByCode = new Map<string, Set<number>>();
  for (const hit of hits) {
    const prev = firstHit.get(hit.userId);
    if (!prev || hit.createdAt < prev) firstHit.set(hit.userId, hit.createdAt);
    if (!usersByCode.has(hit.code)) usersByCode.set(hit.code, new Set());
    usersByCode.get(hit.code)!.add(hit.userId);
  }

  let converted = 0;
  for (const [userId, hitAt] of firstHit) {
    const deadline = hitAt.getTime() + LIMIT_CONVERSION_DAYS * DAY_MS;
    const paid = paidOrders.some(
      (o) =>
        o.userId === userId &&
        o.createdAt.getTime() >= hitAt.getTime() &&
        o.createdAt.getTime() <= deadline
    );
    if (paid) converted += 1;
  }

  const byCode: Record<string, number> = {};
  for (const [code, users] of usersByCode) byCode[code] = users.size;
  return { users: firstHit.size, converted, byCode };
}

export interface SignupRow {
  id: number;
  signupUtmSource: string | null;
  backtestRunTotal: number;
}

export interface SourceFunnelRow {
  source: string;
  signups: number;
  /** 백테스트를 1회 이상 실행한 가입자(실패 요청 포함 — User.backtestRunTotal 기준) */
  backtested: number;
  /** 결제를 1회 이상 완료한 가입자 */
  paid: number;
}

/** 유입 경로별 가입 → 백테스트 → 결제. 가입 수가 많은 경로부터. */
export function computeSourceFunnel(
  signups: SignupRow[],
  paidUserIds: Set<number>
): SourceFunnelRow[] {
  const rows = new Map<string, SourceFunnelRow>();
  for (const user of signups) {
    const source = user.signupUtmSource?.trim() || DIRECT_SOURCE;
    const row = rows.get(source) ?? { source, signups: 0, backtested: 0, paid: 0 };
    row.signups += 1;
    if (user.backtestRunTotal > 0) row.backtested += 1;
    if (paidUserIds.has(user.id)) row.paid += 1;
    rows.set(source, row);
  }
  return [...rows.values()].sort((a, b) => b.signups - a.signups || a.source.localeCompare(b.source));
}

export interface RevenueFunnel {
  windowDays: number;
  limitConversion: LimitConversion;
  signupSources: SourceFunnelRow[];
}

type FunnelClient = {
  planLimitHit: { findMany: (args: any) => Promise<LimitHitRow[]> };
  paymentOrder: { findMany: (args: any) => Promise<PaidOrderRow[]> };
  user: { findMany: (args: any) => Promise<any[]> };
};

/** 최근 30일 퍼널. 한도 도달 전환은 도달 뒤 14일을 더 봐야 하므로 결제는 오늘까지 모두 읽는다. */
export async function loadRevenueFunnel(
  client: FunnelClient,
  now: Date = new Date()
): Promise<RevenueFunnel> {
  const since = new Date(now.getTime() - FUNNEL_WINDOW_DAYS * DAY_MS);
  const [hits, paidOrders, signups] = await Promise.all([
    client.planLimitHit.findMany({
      where: { createdAt: { gte: since } },
      select: { userId: true, code: true, createdAt: true },
    }),
    client.paymentOrder.findMany({
      where: { status: "DONE", createdAt: { gte: since } },
      select: { userId: true, createdAt: true },
    }),
    client.user.findMany({
      where: { status: { not: "DELETED" }, createdAt: { gte: since } },
      select: { id: true, signupUtmSource: true, backtestRunTotal: true },
    }),
  ]);

  return {
    windowDays: FUNNEL_WINDOW_DAYS,
    limitConversion: computeLimitConversion(hits, paidOrders),
    signupSources: computeSourceFunnel(signups, new Set(paidOrders.map((o) => o.userId))),
  };
}
