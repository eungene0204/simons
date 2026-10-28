import { beforeEach, describe, expect, it, vi } from "vitest";

import { prisma } from "@/lib/prisma";
import { fetchBackend } from "@/lib/server/backend";
import {
  findPublicStrategy, listPublicStrategies, publicStrategyFields,
  snapshotFromSettings, snapshotHash, type PublicStrategyRow,
} from "./access";
import { exampleRegistry, type ExampleStrategy } from "./examples";
import {
  ensureFresh, getBaseline, presentOriginal, refreshOne, resetBaselineCache, whenRefreshesSettled, type Baseline,
} from "./originals";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    exampleSimulationResult: { findMany: vi.fn(), createMany: vi.fn(), updateMany: vi.fn() },
  },
}));
vi.mock("@/lib/server/backend", () => ({ fetchBackend: vi.fn() }));
vi.mock("./examples", async (importActual) => ({
  ...(await importActual<typeof import("./examples")>()),
  exampleRegistry: vi.fn(() => new Map()),
}));

const db = prisma.exampleSimulationResult as unknown as Record<string, ReturnType<typeof vi.fn>>;
const backend = vi.mocked(fetchBackend);
const setRegistry = (examples: ExampleStrategy[]) =>
  vi.mocked(exampleRegistry).mockReturnValue(new Map(examples.map((e) => [e.key, e])));
const example = (key: string, title = "RSI 전략", settings = settingsOf()): ExampleStrategy => ({
  key, title, prompt: `${title} 문장`, settings, assumptions: [],
});

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
    name: "RSI 전략", description: "설명", settings, assumptions: [],
    row: {
      id: "pub1", snapshotHash: snapshotHash(snapshotFromSettings(settings)),
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
  db.findMany.mockResolvedValue([]);
  setRegistry([]);
});

describe("예시 등록부와 공개 응답 허용 목록", () => {
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

  it("공개 필드에 전략 ID·종목 코드 전체 목록·해시가 없다", () => {
    const fields = publicStrategyFields(settingsOf());
    const text = JSON.stringify(fields);
    for (const leaked of ["userId", "strategy_id", "canonical_strategy_dsl", "symbols", "7:abc", "secret", "000660"]) {
      expect(text).not.toContain(leaked);
    }
    expect(fields.entry).toBeTruthy();
    expect(fields.target_stocks).toEqual([{ symbol: "005930", name: "삼성전자" }]);
  });

  it("publicId 조회는 예시 등록부에 있는 키만 받고, 없으면 DB를 보지 않고 null이다", async () => {
    expect(await findPublicStrategy("pub1")).toBeNull();
    expect(db.findMany).not.toHaveBeenCalled();

    setRegistry([example("pub1")]);
    db.findMany.mockResolvedValue([item().row]);
    const found = await findPublicStrategy("pub1");
    expect(found).toMatchObject({ name: "RSI 전략", description: "RSI 전략 문장", settings: settingsOf(), row: { id: "pub1" } });
    expect(db.createMany).not.toHaveBeenCalled();
  });

  it("결과 행이 없는 예시는 pending 행을 만든다", async () => {
    setRegistry([example("pub1")]);
    db.findMany.mockResolvedValueOnce([]).mockResolvedValueOnce([item({ status: "pending", result: null }).row]);
    const found = await findPublicStrategy("pub1");
    expect(db.createMany.mock.calls[0][0]).toEqual({
      data: [{ id: "pub1", snapshotHash: snapshotHash(snapshotFromSettings(settingsOf())) }], skipDuplicates: true,
    });
    expect(found?.row.status).toBe("pending");
  });

  it("목록은 예시 이름순·검색을 쓰고 21번째 항목으로 다음 페이지를 판단한다", async () => {
    const examples = Array.from({ length: 41 }, (_, i) => example(`key${String(40 - i).padStart(2, "0")}`, `RSI 전략${String(i).padStart(2, "0")}`));
    setRegistry([...examples, example("other-key", "골든크로스")]);
    // key40만 결과 행이 없다 — createMany 뒤의 재조회에서 생긴다.
    db.findMany.mockImplementation(async ({ where }: any) =>
      where.id.in.filter((id: string) => id !== "key40" || db.createMany.mock.calls.length > 0).map((id: string) => ({ ...item().row, id })));

    const out = await listPublicStrategies({ q: "rsi", page: 1 });
    expect(out.hasNext).toBe(true);
    expect(out.items).toHaveLength(20);
    expect(out.items.map((i) => i.name)).toEqual(examples.slice(0, 20).map((e) => e.title));
    expect(db.createMany.mock.calls[0][0]).toMatchObject({ skipDuplicates: true, data: [{ id: "key40" }] });
    expect(JSON.stringify(out.items)).not.toContain("골든크로스");

    const last = await listPublicStrategies({ q: "rsi", page: 3 });
    expect([last.items.length, last.hasNext]).toEqual([1, false]);
  });

  it("시뮬레이션할 수 없는 예시(실행 설정 없음·불가 판정)는 목록에서 뺀다", async () => {
    setRegistry([example("meta", "가", JSON.stringify({ name: "메타만" })), example("u", "나"), example("ok1", "다")]);
    const unavailable = { ...item().row, id: "u", status: "unavailable" };
    db.findMany.mockResolvedValue([{ ...item().row, id: "meta" }, unavailable, { ...item().row, id: "ok1" }]);

    const out = await listPublicStrategies({ page: 1 });

    expect(out.items.map((i) => i.row.id)).toEqual(["ok1"]);
    expect(out.hasNext).toBe(false);
    expect(db.createMany).not.toHaveBeenCalled();
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
    setRegistry([example("pub1")]);
    db.findMany.mockResolvedValue([item({ status: "pending", result: null }).row]);
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
    expect(backend).not.toHaveBeenCalled();
  });

  it("성공 결과를 그 예시의 결과 행에 저장한다", async () => {
    leaseAndRun();
    mockBackend(() => ({ status: 200, body: { status: "ready", dataAsOf: "2026-10-23", engineVersion: "16.43.0", computedAt: "2026-10-27T01:00:00Z", summary: {}, appliedOverrides: [] } }));
    await refreshOne("pub1");
    const write = db.updateMany.mock.calls[1][0];
    expect(write.where).toEqual({ id: "pub1" });
    expect(write.data).toMatchObject({ status: "ready", snapshotHash: snapshotHash(snapshotFromSettings(settingsOf())), dataAsOf: "2026-10-23", refreshLeaseUntil: null });
    expect(JSON.parse(write.data.result)).not.toHaveProperty("appliedOverrides");
    expect(backend.mock.calls.find((c) => String(c[0]).endsWith("/run"))?.[1]).toMatchObject({ method: "POST" });
  });

  it("결과 행이 사라졌으면 쓰기가 0건이고 오류 없이 끝난다", async () => {
    leaseAndRun(0);
    mockBackend(() => ({ status: 200, body: { status: "ready", summary: {} } }));
    await expect(refreshOne("pub1")).resolves.toBeUndefined();
    expect(db.updateMany).toHaveBeenCalledTimes(2);
  });

  it("실행 불가 스냅샷은 엔진 없이 unavailable로 기록한다", async () => {
    db.updateMany.mockResolvedValue({ count: 1 });
    const meta = JSON.stringify({ id: "9:x", name: "메타", description: "d" });
    setRegistry([example("pub1", "메타", meta)]);
    db.findMany.mockResolvedValue([item({}, meta).row]);
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
    setRegistry([example("pub1")]);
    db.findMany.mockResolvedValue([item().row]);
    mockBackend(() => new Error("down"));
    await refreshOne("pub1");
    const data = db.updateMany.mock.calls[1][0].data;
    expect(data).toMatchObject({ lastError: "BACKEND_UNREACHABLE" });
    expect(data).not.toHaveProperty("result");
    expect(data).not.toHaveProperty("status");
  });
});
