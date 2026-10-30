// 가상계좌 일별 수익률 저장 — 체결·입금 내역과 일별 종가로 장 마감 기준 총 자산을 복원해
// VirtualAccountSnapshot 에 한 날짜 한 줄로 남긴다(화면은 저장된 값만 읽는다).
//
// 스케줄러가 매일 새벽과 서버 시작 때 돌린다. 이미 저장된 날짜는 건드리지 않고 빠진 날짜만 채운다 —
// 개설일부터 어제까지의 과거 구간도, 매일 새로 생기는 어제 하루도 같은 경로로 들어온다.
// 복원한 마지막 현금·보유 수량이 실제 계좌와 다르면(관리자 초기화·기록 누락 등) 그 계좌는
// 저장하지 않는다 — 틀린 곡선을 지어내지 않는다.

import type { PrismaClient } from "@prisma/client";
import { moneyToNumber } from "@/lib/server/assetService";
import { backendPathSegment, fetchBackend } from "@/lib/server/backend";
import { marketDateKey } from "@/app/virtual-account/performanceSeries";
import { replayDailyValues, type ClosesBySymbol } from "@/lib/virtual-account/dailyReplay";

type SnapshotClient = Pick<PrismaClient, "virtualAccount" | "virtualAccountSnapshot">;

/** 종목 일별 종가(날짜 → 종가). 조회에 실패하면 null — 빈 데이터로 계산해 저장하지 않도록 구분한다. */
export type FetchCloses = (symbol: string, sinceDate: string) => Promise<Record<string, number> | null>;

/** 현금 대조 허용 오차 — 금액은 소수 30자리 Decimal 이라 부동소수 누적 오차만 남는다. */
const CASH_TOLERANCE = 0.01;

export function accountTimeZone(currency: string | null | undefined): string {
  return currency === "USD" ? "America/New_York" : "Asia/Seoul";
}

/** 날짜(YYYY-MM-DD)를 저장 키(그날 00:00 UTC)로 바꾼다. */
export function dateToTakenAt(date: string): Date {
  return new Date(`${date}T00:00:00.000Z`);
}

export const fetchBackendCloses: FetchCloses = async (symbol, sinceDate) => {
  const symbolSegment = backendPathSegment(symbol);
  if (!symbolSegment) return null;
  // limit 은 뒤에서부터 센 거래일 수 — 달력 일수면 넉넉하다.
  const days = Math.ceil((Date.now() - dateToTakenAt(sinceDate).getTime()) / 86_400_000) + 10;
  try {
    const res = await fetchBackend(`/stock/${symbolSegment}/ohlcv?limit=${days}`, { timeoutMs: 30_000 });
    if (!res.ok) return null;
    const body = (await res.json()) as { candles?: { date: string; close: number }[] };
    const out: Record<string, number> = {};
    for (const c of body.candles ?? []) if (c.date >= sinceDate && c.close > 0) out[c.date] = Number(c.close);
    return out;
  } catch {
    return null;
  }
};

export type DailySyncResult = {
  accounts: number;
  written: number;
  /** 복원 결과가 실제 계좌와 달라 저장하지 않은 계좌 */
  mismatched: string[];
  /** 종가 조회에 실패해 이번 실행에서 건너뛴 계좌(다음 실행에 다시 시도) */
  fetchFailed: string[];
};

export async function syncAccountDailySnapshots(
  client: SnapshotClient,
  options: { fetchCloses?: FetchCloses; now?: Date; accountIds?: string[] } = {}
): Promise<DailySyncResult> {
  const fetchCloses = options.fetchCloses ?? fetchBackendCloses;
  const now = options.now ?? new Date();
  const accounts = await client.virtualAccount.findMany({
    where: { status: "ACTIVE", ...(options.accountIds ? { id: { in: options.accountIds } } : {}) },
    include: {
      VirtualPosition: { select: { symbol: true, quantity: true } },
      VirtualOrder: true,
      VirtualCashEvent: { select: { date: true, type: true, amount: true } },
      VirtualAccountSnapshot: { select: { takenAt: true } },
    },
  });

  // 종가는 종목마다 한 번만 받되, 모든 계좌 중 가장 이른 개설일부터 받는다 — 처음 요청한 계좌의
  // 개설일부터 받으면 더 일찍 개설한 계좌의 앞쪽 종가가 비어 체결가로 평가된다(2026-10-30 실측 68일치 오염).
  const earliestStart = accounts.reduce<string | null>((min, a) => {
    const d = marketDateKey(a.createdAt.toISOString(), accountTimeZone(a.currency));
    return min == null || d < min ? d : min;
  }, null);
  const closeCache = new Map<string, Promise<Record<string, number> | null>>();
  const result: DailySyncResult = { accounts: accounts.length, written: 0, mismatched: [], fetchFailed: [] };

  for (const account of accounts) {
    const timeZone = accountTimeZone(account.currency);
    const today = marketDateKey(now.toISOString(), timeZone);
    const start = marketDateKey(account.createdAt.toISOString(), timeZone);
    if (start >= today) continue; // 오늘 개설 — 남길 과거가 없다
    const stored = new Set(account.VirtualAccountSnapshot.map((s) => s.takenAt.toISOString().slice(0, 10)));

    const symbols = [...new Set(account.VirtualOrder.map((o) => o.symbol))];
    const closes: ClosesBySymbol = {};
    let fetchFailed = false;
    for (const symbol of symbols) {
      if (!closeCache.has(symbol)) closeCache.set(symbol, fetchCloses(symbol, earliestStart ?? start));
      const series = await closeCache.get(symbol)!;
      if (series == null) {
        fetchFailed = true;
        break;
      }
      closes[symbol] = series;
    }
    if (fetchFailed) {
      // 종가를 못 받은 날은 체결가로 평가돼 틀린 값이 남는다 — 이번엔 저장하지 않고 다음 실행에 다시 시도한다.
      result.fetchFailed.push(account.id);
      continue;
    }

    const replay = replayDailyValues({
      createdAt: account.createdAt.toISOString(),
      initialCash: moneyToNumber(account.initialCash),
      currency: account.currency,
      orders: account.VirtualOrder.map((o) => ({
        side: o.side,
        type: o.type,
        status: o.status,
        symbol: o.symbol,
        quantity: o.quantity,
        price: moneyToNumber(o.price),
        filledPrice: o.filledPrice == null ? null : moneyToNumber(o.filledPrice),
        createdAt: o.createdAt.toISOString(),
        filledAt: o.filledAt ? o.filledAt.toISOString() : null,
      })),
      cashEvents: account.VirtualCashEvent.map((e) => ({ date: e.date, type: e.type, amount: moneyToNumber(e.amount) })),
      closes,
      today,
      timeZone,
    });

    const actual: Record<string, number> = {};
    for (const p of account.VirtualPosition) if (p.quantity !== 0) actual[p.symbol] = p.quantity;
    const positionsMatch =
      Object.keys(actual).length === Object.keys(replay.finalPositions).length &&
      Object.entries(actual).every(([symbol, qty]) => replay.finalPositions[symbol] === qty);
    if (!positionsMatch || Math.abs(replay.finalCash - moneyToNumber(account.currentCash)) > CASH_TOLERANCE) {
      result.mismatched.push(account.id);
      continue;
    }

    const rows = replay.points
      .filter((p) => !stored.has(p.date))
      .map((p) => ({
        accountId: account.id,
        takenAt: dateToTakenAt(p.date),
        totalValue: p.totalValue,
        totalContributed: p.totalContributed,
      }));
    if (rows.length === 0) continue;
    const created = await client.virtualAccountSnapshot.createMany({ data: rows, skipDuplicates: true });
    result.written += created.count;
  }
  return result;
}
