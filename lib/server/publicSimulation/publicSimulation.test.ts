import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { fetchBackend } from "@/lib/server/backend";
import {
  PUBLIC_STRATEGY_WHERE, findPublicStrategy, listPublicStrategies, publicStrategyFields,
  snapshotFromSettings, snapshotHash, type PublicStrategyRow,
} from "./access";
import {
  ensureFresh, getBaseline, presentOriginal, refreshOne, resetBaselineCache, whenRefreshesSettled, type Baseline,
} from "./originals";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    strategy: { findMany: vi.fn() },
    publicSimulationResult: { findFirst: vi.fn(), findMany: vi.fn(), createMany: vi.fn(), updateMany: vi.fn() },
  },
}));
vi.mock("@/lib/server/backend", () => ({ fetchBackend: vi.fn() }));

const db = prisma.publicSimulationResult as unknown as Record<string, ReturnType<typeof vi.fn>>;
const strategyDb = prisma.strategy as unknown as Record<string, ReturnType<typeof vi.fn>>;
const backend = vi.mocked(fetchBackend);

const BASELINE: Baseline = {
  today: "2026-10-27", requestedStart: "2023-10-27", requestedEnd: "2026-10-27", endDate: "2026-10-23",
  dataAsOf: "2026-10-23", stale: true, engineVersion: "16.43.0",
};
const settingsOf = (rsiPeriod = 14) =>
  JSON.stringify({
    id: "7:abc", userId: 7, strategy_id: "hash", canonical_strategy_dsl: { x: 1 }, name: "RSI 전략", description: "설명",
    symbols: ["005930", "000660"], universe_id: "kospi200", sector: null,
    target_stocks: [{ symbol: "005930", name: "삼성전자", secret: "x" }],
    entry: { conditions: [{ type: "indicator", id: "rsi", params: { period: rsiPeriod, operator: "<", value: 30 } }] },
    exit: { conditions: [] },
    risk: { position_size_pct: 100, init_cash: 10_000_000 },
    options: { fee_rate: 0.00015, slippage_rate: 0.0005 }, period: "5y",
  });
const stored = (over: Record<string, unknown> = {}) =>
  JSON.stringify({
    status: "ready", dataAsOf: "2026-10-23", engineVersion: "16.43.0",
    window: { requestedStart: "2023-10-27", actualStart: "2023-10-27", actualEnd: "2026-10-23" },
    summary: { totalReturnPct: 10 }, curve: { dates: ["2023-10-27"], returnPct: [0] }, ...over,
  });
export function item(over: Partial<PublicStrategyRow["row"]> = {}, settings = settingsOf()): PublicStrategyRow {
  return {
    name: "RSI 전략", description: "설명", settings,
    row: {
      id: "pub1", strategyId: "7:abc", snapshotHash: snapshotHash(snapshotFromSettings(settings)),
      dataAsOf: "2026-10-23", engineVersion: "16.43.0", status: "ready", reason: null, result: stored(),
      computedAt: new Date("2026-10-27T01:00:00Z"), refreshLeaseUntil: null, lastAttemptAt: null, lastError: null, ...over,
    },
  };
}

function mockBackend(run: (init: any) => { status: number; body: unknown } | Error) {
  backend.mockImplementation((async (path: string, init: any) => {
    const out = path.endsWith("/baseline") ? { status: 200, body: BASELINE } : run(init);
    if (out instanceof Error) throw out;
    return { ok: out.status < 400, status: out.status, json: async () => out.body } as Response;
  }) as any);
}

beforeEach(() => {
  vi.clearAllMocks();
  resetBaselineCache();
  db.updateMany.mockResolvedValue({ count: 0 });
});

describe("공개 조건과 공개 응답 허용 목록", () => {
  it("엔진 요청형 키만 스냅샷으로 고르고, 메타만 저장된 전략은 null이다", () => {
    const snap = snapshotFromSettings(settingsOf()) as Record<string, unknown>;
    expect(Object.keys(snap).sort()).toEqual(["entry", "exit", "options", "period", "risk", "sector", "symbols", "target_stocks", "universe_id"].sort());
    expect(snapshotFromSettings(JSON.stringify({ id: "x", name: "메타", description: "d", updated_at: "t" }))).toBeNull();
    expect(snapshotFromSettings("not json")).toBeNull();
  });

  it("해시는 키 순서와 무관하고 파라미터가 바뀌면 달라진다", () => {
    expect(snapshotHash({ a: 1, b: { c: 2, d: 3 } })).toBe(snapshotHash({ b: { d: 3, c: 2 }, a: 1 }));
    expect(snapshotHash(snapshotFromSettings(settingsOf(14)))).not.toBe(snapshotHash(snapshotFromSettings(settingsOf(21))));
  });

  it("공개 필드에 소유자·전략 ID·종목 코드 전체 목록·해시가 없다", () => {
    const fields = publicStrategyFields(settingsOf());
    const text = JSON.stringify(fields);
    for (const leaked of ["userId", "strategy_id", "canonical_strategy_dsl", "symbols", "7:abc", "secret", "000660"]) {
      expect(text).not.toContain(leaked);
    }
    expect(fields.entry).toBeTruthy();
    expect(fields.target_stocks).toEqual([{ symbol: "005930", name: "삼성전자" }]);
  });

  it("publicId 조회는 공개·저장·미삭제 조건을 함께 걸고, 비공개·삭제는 null이다", async () => {
    db.findFirst.mockResolvedValue(null);
    expect(await findPublicStrategy("pub1")).toBeNull();
    expect(db.findFirst.mock.calls[0][0].where).toEqual({ id: "pub1", Strategy: { is: PUBLIC_STRATEGY_WHERE } });

    db.findFirst.mockResolvedValue({ ...item().row, Strategy: { name: "RSI 전략", description: null, settings: settingsOf() } });
    const found = await findPublicStrategy("pub1");
    expect(found?.row.id).toBe("pub1");
    expect(found).not.toHaveProperty("Strategy");
  });

  it("목록은 공개 조건·전략명순·검색을 쓰고 21번째 행으로 다음 페이지를 판단한다", async () => {
    const rows = Array.from({ length: 21 }, (_, i) => ({
      id: `s${i}`, name: `전략${String(i).padStart(2, "0")}`, description: null, settings: settingsOf(),
      PublicSimulationResult: i === 0 ? null : { ...item().row, id: `p${i}`, strategyId: `s${i}` },
    }));
    strategyDb.findMany.mockResolvedValue(rows);
    db.findMany.mockResolvedValue([{ ...item().row, id: "pnew", strategyId: "s0" }]);

    const out = await listPublicStrategies({ q: "rsi", page: 2 });
    const args = strategyDb.findMany.mock.calls[0][0];
    expect(args.where).toMatchObject({ ...PUBLIC_STRATEGY_WHERE, name: { contains: "rsi", mode: "insensitive" } });
    expect(args.orderBy).toEqual([{ name: "asc" }, { id: "asc" }]);
    expect([args.skip, args.take]).toEqual([20, 21]);
    expect(JSON.stringify(args.select)).not.toContain("userId");
    expect(out.hasNext).toBe(true);
    expect(out.items).toHaveLength(20);
    expect(db.createMany.mock.calls[0][0]).toMatchObject({ skipDuplicates: true, data: [{ strategyId: "s0" }] });
    expect(out.items[0].row.id).toBe("pnew");
  });
});

describe("원본 결과 표시 상태", () => {
  it("결과가 없으면 pending, 실패 행은 failed로 구분한다", () => {
    expect(presentOriginal(item({ status: "pending", result: null }), BASELINE).status).toBe("pending");
    expect(presentOriginal(item({ status: "failed", reason: "TIMEOUT", result: null }), BASELINE)).toEqual({ status: "failed", reason: "TIMEOUT" });
  });

  it("최신 결과는 그대로, 기준일·엔진·오늘 창이 바뀌면 이전 결과를 유지한 채 refreshing이다", () => {
    expect(presentOriginal(item(), BASELINE)).toMatchObject({ status: "ready", dataAsOf: "2026-10-23" });
    const newerData = presentOriginal(item(), { ...BASELINE, dataAsOf: "2026-10-26" });
    expect(newerData).toMatchObject({ status: "refreshing", dataAsOf: "2026-10-23", summary: { totalReturnPct: 10 } });
    expect(presentOriginal(item(), { ...BASELINE, engineVersion: "16.44.0" }).status).toBe("refreshing");
    expect(presentOriginal(item(), { ...BASELINE, requestedStart: "2023-10-28" }).status).toBe("refreshing");
  });

  it("설정이 바뀌면 옛 결과를 새 조건 옆에 보이지 않는다", () => {
    const changed = item({}, settingsOf(21));
    changed.row.snapshotHash = snapshotHash(snapshotFromSettings(settingsOf(14)));
    expect(presentOriginal(changed, BASELINE)).toEqual({ status: "pending" });
  });

  it("실행 불가 판정은 창이 바뀌어도 unavailable을 유지한다", () => {
    const unavailable = item({ status: "unavailable", result: stored({ status: "unavailable", reason: "MISSING_RUN_CONDITION", window: undefined }) });
    expect(presentOriginal(unavailable, { ...BASELINE, dataAsOf: "2026-10-26" })).toMatchObject({ status: "unavailable", reason: "MISSING_RUN_CONDITION" });
  });
});

describe("기준일 캐시", () => {
  it("5분 동안 재사용하고, 백엔드가 실패하면 마지막 값을 쓴다", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    mockBackend(() => ({ status: 200, body: {} }));
    expect(await getBaseline()).toEqual(BASELINE);
    await getBaseline();
    expect(backend).toHaveBeenCalledTimes(1);
    vi.setSystemTime(Date.now() + 6 * 60_000);
    backend.mockRejectedValue(new Error("down"));
    expect(await getBaseline()).toEqual(BASELINE);
    vi.useRealTimers();
  });

  it("값이 한 번도 없고 백엔드가 내려가 있으면 null", async () => {
    backend.mockRejectedValue(new Error("down"));
    expect(await getBaseline()).toBeNull();
  });
});

describe("갱신 예약과 실행", () => {
  const leaseAndRun = (n = 1) => {
    db.updateMany.mockResolvedValueOnce({ count: 1 }).mockResolvedValue({ count: n });
    db.findFirst.mockResolvedValue({ ...item({ status: "pending", result: null }).row, Strategy: { name: "n", description: null, settings: settingsOf() } });
  };

  it("낡은 항목만 같은 id당 한 번 예약하고, 리스가 살아 있으면 건너뛴다", async () => {
    ensureFresh(item({ id: "fresh-1" }), BASELINE);
    await whenRefreshesSettled();
    expect(db.updateMany).not.toHaveBeenCalled();

    const stale = item({ id: "stale-1", status: "pending", result: null });
    ensureFresh(stale, BASELINE);
    ensureFresh(stale, BASELINE);
    await whenRefreshesSettled();
    expect(db.updateMany).toHaveBeenCalledTimes(1);   // 리스 시도 1회(중복 예약 없음)

    db.updateMany.mockClear();
    ensureFresh(item({ id: "leased-1", status: "pending", result: null, refreshLeaseUntil: new Date(Date.now() + 60_000) }), BASELINE);
    await whenRefreshesSettled();
    expect(db.updateMany).not.toHaveBeenCalled();
  });

  it("리스를 못 잡으면 엔진을 부르지 않는다", async () => {
    db.updateMany.mockResolvedValue({ count: 0 });
    await refreshOne("pub1");
    const where = db.updateMany.mock.calls[0][0].where;
    expect(where.OR).toEqual([{ refreshLeaseUntil: null }, { refreshLeaseUntil: { lt: expect.any(Date) } }]);
    expect(where.Strategy).toEqual({ is: PUBLIC_STRATEGY_WHERE });
    expect(backend).not.toHaveBeenCalled();
  });

  it("성공 결과는 '실행한 설정 그대로 아직 공개 중'일 때만 저장한다", async () => {
    leaseAndRun();
    mockBackend(() => ({ status: 200, body: { status: "ready", dataAsOf: "2026-10-23", engineVersion: "16.43.0", computedAt: "2026-10-27T01:00:00Z", summary: {}, appliedOverrides: [] } }));
    await refreshOne("pub1");
    const write = db.updateMany.mock.calls[1][0];
    expect(write.where).toEqual({ id: "pub1", Strategy: { is: { ...PUBLIC_STRATEGY_WHERE, settings: settingsOf() } } });
    expect(write.data).toMatchObject({ status: "ready", snapshotHash: snapshotHash(snapshotFromSettings(settingsOf())), dataAsOf: "2026-10-23", refreshLeaseUntil: null });
    expect(JSON.parse(write.data.result)).not.toHaveProperty("appliedOverrides");
    expect(backend.mock.calls.find((c) => String(c[0]).endsWith("/run"))?.[1]).toMatchObject({ method: "POST" });
  });

  it("저장 조건이 더는 맞지 않으면(실행 중 철회) 쓰기가 0건이고 오류 없이 끝난다", async () => {
    leaseAndRun(0);
    mockBackend(() => ({ status: 200, body: { status: "ready", summary: {} } }));
    await expect(refreshOne("pub1")).resolves.toBeUndefined();
    expect(db.updateMany).toHaveBeenCalledTimes(2);
  });

  it("실행 불가 스냅샷은 엔진 없이 unavailable로 기록한다", async () => {
    db.updateMany.mockResolvedValue({ count: 1 });
    const meta = JSON.stringify({ id: "9:x", name: "메타", description: "d" });
    db.findFirst.mockResolvedValue({ ...item({}, meta).row, Strategy: { name: "n", description: null, settings: meta } });
    mockBackend(() => ({ status: 200, body: {} }));
    await refreshOne("pub1");
    expect(backend.mock.calls.some((c) => String(c[0]).endsWith("/run"))).toBe(false);
    expect(db.updateMany.mock.calls[1][0].data).toMatchObject({ status: "unavailable", reason: "NO_EXECUTABLE_SNAPSHOT" });
  });

  it("BUSY는 실패로 표시하지 않고 곧 재시도하도록 리스만 둔다", async () => {
    leaseAndRun();
    mockBackend(() => ({ status: 429, body: { code: "BUSY" } }));
    await refreshOne("pub1");
    const data = db.updateMany.mock.calls[1][0].data;
    expect(data.lastError).toBe("BUSY");
    expect(data.refreshLeaseUntil.getTime() - Date.now()).toBeLessThan(2 * 60_000);
  });

  it("결과가 없던 항목의 실패는 failed로, 이전 결과가 있으면 그 결과를 지우지 않는다", async () => {
    leaseAndRun();
    mockBackend(() => ({ status: 500, body: { code: "INCONSISTENT_RESULT" } }));
    await refreshOne("pub1");
    expect(db.updateMany.mock.calls[1][0].data).toMatchObject({ status: "failed", reason: "INCONSISTENT_RESULT", result: null });

    vi.clearAllMocks();
    db.updateMany.mockResolvedValueOnce({ count: 1 }).mockResolvedValue({ count: 1 });
    db.findFirst.mockResolvedValue({ ...item().row, Strategy: { name: "n", description: null, settings: settingsOf() } });
    mockBackend(() => new Error("down"));
    await refreshOne("pub1");
    const data = db.updateMany.mock.calls[1][0].data;
    expect(data).toMatchObject({ lastError: "BACKEND_UNREACHABLE" });
    expect(data).not.toHaveProperty("result");
    expect(data).not.toHaveProperty("status");
  });
});
