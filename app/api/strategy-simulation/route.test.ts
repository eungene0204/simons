import { beforeEach, describe, expect, it, vi } from "vitest";

import { BoardError } from "@/lib/board/rules";
import {
  NotPublicError, findPublicStrategy, listPublicStrategies, snapshotFromSettings, snapshotHash,
} from "@/lib/server/publicSimulation/access";
import { fetchBackend } from "@/lib/server/backend";
import {
  BaselineChangedError, InvalidParameterError, RateLimitedError, SimulationFailedError, runModified,
} from "@/lib/server/publicSimulation/modified";
import { ensureFresh, getBaseline } from "@/lib/server/publicSimulation/originals";
import { GET as listRoute } from "./route";
import { GET as detailRoute } from "./[publicId]/route";
import { POST as runRoute } from "./[publicId]/run/route";

vi.mock("@/lib/server/backend", () => ({ fetchBackend: vi.fn() }));
vi.mock("@/lib/prisma", () => ({ prisma: {} }));
vi.mock("@/lib/board/server", () => ({ identity: vi.fn(() => "ident-1") }));
vi.mock("@/lib/server/publicSimulation/access", async (importActual) => ({
  ...(await importActual<typeof import("@/lib/server/publicSimulation/access")>()),
  findPublicStrategy: vi.fn(),
  listPublicStrategies: vi.fn(),
}));
vi.mock("@/lib/server/publicSimulation/originals", async (importActual) => ({
  ...(await importActual<typeof import("@/lib/server/publicSimulation/originals")>()),
  getBaseline: vi.fn(),
  ensureFresh: vi.fn(),
}));
vi.mock("@/lib/server/publicSimulation/modified", async (importActual) => ({
  ...(await importActual<typeof import("@/lib/server/publicSimulation/modified")>()),
  runModified: vi.fn(),
}));

const BASELINE = {
  today: "2026-10-27", requestedStart: "2023-10-27", requestedEnd: "2026-10-27", endDate: "2026-10-23",
  dataAsOf: "2026-10-23", stale: true, engineVersion: "16.43.0",
};
const settings = JSON.stringify({
  id: "7:secret-strategy-id", userId: 7, strategy_id: "hashvalue", canonical_strategy_dsl: { a: 1 },
  symbols: ["005930", "000660"], universe_id: "kospi200",
  entry: { conditions: [{ type: "indicator", id: "rsi", params: { period: 14, operator: "<", value: 30 } }] },
  exit: { conditions: [] }, risk: { position_size_pct: 100, init_cash: 10_000_000 },
  options: { fee_rate: 0.00015, slippage_rate: 0.0005 },
});
const HASH = snapshotHash(snapshotFromSettings(settings));
const dates = Array.from({ length: 700 }, (_, i) => `d${i}`);
const stored = {
  status: "ready", dataAsOf: "2026-10-23", engineVersion: "16.43.0", computedAt: "2026-10-27T01:00:00Z",
  window: { requestedStart: "2023-10-27", requestedEnd: "2026-10-27", actualStart: "2023-10-27", actualEnd: "2026-10-23", dataAsOf: "2026-10-23", stale: true, limited: false },
  summary: { initialCapital: 1e7, totalReturnPct: 10, totalProfit: 1e6, maxDrawdownPct: -5, trades: 3, sharpe: 1 },
  curve: { dates, returnPct: dates.map((_, i) => i / 10) },
  contributors: { top: [], bottom: [] },
  editableParams: [{ path: "entry.conditions.0.params.period", original: 14, editable: true }],
};
const item = {
  name: "RSI 전략", description: "설명", settings, assumptions: [],
  row: {
    id: "pubId1234", snapshotHash: HASH, dataAsOf: "2026-10-23", engineVersion: "16.43.0",
    status: "ready", reason: null, result: JSON.stringify(stored), computedAt: new Date(), refreshLeaseUntil: null,
    lastAttemptAt: null, lastError: null,
  },
};
const call = (route: any, url: string, init?: RequestInit, publicId = "pubId1234") =>
  route(new Request(`http://x${url}`, init), { params: { publicId } });
const post = (body: unknown, publicId?: string) =>
  call(runRoute, "/api/strategy-simulation/pubId1234/run", { method: "POST", body: JSON.stringify(body) }, publicId);
const validBody = {
  overrides: [{ path: "entry.conditions.0.params.period", value: 21 }], baseSnapshotHash: HASH, dataAsOf: "2026-10-23",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getBaseline).mockResolvedValue(BASELINE);
  vi.mocked(listPublicStrategies).mockResolvedValue({ items: [item], hasNext: false } as any);
  vi.mocked(findPublicStrategy).mockResolvedValue(item as any);
});

describe("GET /api/strategy-simulation", () => {
  it("로그인 없이 카드 필드만 돌려주고 no-store이며 엔진을 실행하지 않는다", async () => {
    const res = await listRoute(new Request("http://x/api/strategy-simulation"));
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    expect(Object.keys(body.items[0]).sort()).toEqual(
      ["computedAt", "curve", "description", "name", "publicId", "randomAssumed", "status", "summary", "window"].sort());
    expect(body.items[0]).toMatchObject({ publicId: "pubId1234", status: "ready", summary: { totalReturnPct: 10, totalProfit: 1e6, maxDrawdownPct: -5 } });
    expect(body.items[0].summary).not.toHaveProperty("initialCapital");
    const text = JSON.stringify(body);
    for (const leaked of ["secret-strategy-id", "userId", "strategy_id", "symbols", "snapshotHash", "settings", "005930"]) {
      expect(text).not.toContain(leaked);
    }
    expect(runModified).not.toHaveBeenCalled();
    expect(fetchBackend).not.toHaveBeenCalled();
    expect(ensureFresh).toHaveBeenCalledWith(item, BASELINE);
  });

  it("미니 그래프는 저장 곡선을 첫·마지막 점 포함 120점 이하로 줄인다", async () => {
    const body = await (await listRoute(new Request("http://x/api/strategy-simulation"))).json();
    const { dates: d, returnPct } = body.items[0].curve;
    expect(d.length).toBe(120);
    expect([d[0], d[d.length - 1]]).toEqual(["d0", "d699"]);
    expect(returnPct[returnPct.length - 1]).toBeCloseTo(69.9);
  });

  it("검색어·페이지를 검증해 서비스에 넘긴다", async () => {
    await listRoute(new Request("http://x/api/strategy-simulation?q=%20rsi%20&page=3"));
    expect(listPublicStrategies).toHaveBeenCalledWith({ q: "rsi", page: 3 });
    for (const bad of ["page=0", "page=1.5", "page=abc", "page=1001", `q=${"a".repeat(51)}`]) {
      expect((await listRoute(new Request(`http://x/api/strategy-simulation?${bad}`))).status).toBe(400);
    }
  });

  it("결과가 없는 카드는 곡선·요약 없이 상태만 보낸다(임의 그래프 금지)", async () => {
    vi.mocked(listPublicStrategies).mockResolvedValue({
      items: [{ ...item, row: { ...item.row, status: "pending", result: null } }], hasNext: true,
    } as any);
    const body = await (await listRoute(new Request("http://x/api/strategy-simulation"))).json();
    expect(body.items[0]).toMatchObject({ status: "pending" });
    expect(body.items[0].curve).toBeUndefined();
    expect(body.items[0].summary).toBeUndefined();
    expect(body.hasNext).toBe(true);
  });
});

describe("GET /api/strategy-simulation/[publicId]", () => {
  it("비공개·삭제·없음, 형식이 틀린 id는 모두 404이고 형식 오류는 DB를 보지 않는다", async () => {
    vi.mocked(findPublicStrategy).mockResolvedValue(null);
    expect((await call(detailRoute, "/x")).status).toBe(404);
    vi.mocked(findPublicStrategy).mockClear();
    expect((await call(detailRoute, "/x", undefined, "../etc")).status).toBe(404);
    expect(findPublicStrategy).not.toHaveBeenCalled();
  });

  it("공개 허용 목록의 전략 조건과 원본 결과·수정 폼 설명자를 돌려준다", async () => {
    const res = await call(detailRoute, "/x");
    const body = await res.json();
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    expect(body).toMatchObject({ publicId: "pubId1234", name: "RSI 전략", baseSnapshotHash: HASH });
    expect(body.original).toMatchObject({ status: "ready", editableParams: [{ path: "entry.conditions.0.params.period", original: 14 }] });
    expect(body.original.curve.dates).toHaveLength(700);   // 상세는 전체 곡선, 카드와 같은 저장 결과
    expect(body.strategy.entry).toBeTruthy();
    const text = JSON.stringify(body);
    for (const leaked of ["secret-strategy-id", "userId", "strategy_id", "canonical_strategy_dsl", "symbols", "005930"]) {
      expect(text).not.toContain(leaked);
    }
    expect(ensureFresh).toHaveBeenCalled();
  });

  it("설정이 바뀌어 저장된 옛 결과가 맞지 않으면 pending으로 보인다", async () => {
    vi.mocked(findPublicStrategy).mockResolvedValue({ ...item, row: { ...item.row, snapshotHash: "different" } } as any);
    const body = await (await call(detailRoute, "/x")).json();
    expect(body.original).toEqual({ status: "pending" });
  });
});

describe("POST /api/strategy-simulation/[publicId]/run", () => {
  it("검증을 통과한 입력만 서비스에 넘기고 식별자를 함께 보낸다", async () => {
    vi.mocked(runModified).mockResolvedValue({ status: "ready" });
    const res = await post(validBody);
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    expect(runModified).toHaveBeenCalledWith({ publicId: "pubId1234", identity: "ident-1", ...validBody });
  });

  it.each([
    ["본문 없음", undefined],
    ["overrides 누락", { ...validBody, overrides: undefined }],
    ["overrides 21개", { ...validBody, overrides: Array.from({ length: 21 }, () => ({ path: "a", value: 1 })) }],
    ["숫자가 아닌 값", { ...validBody, overrides: [{ path: "a", value: "21" }] }],
    ["경로 과다 길이", { ...validBody, overrides: [{ path: "a".repeat(121), value: 1 }] }],
    ["해시 형식 오류", { ...validBody, baseSnapshotHash: "abc" }],
    ["기준일 형식 오류", { ...validBody, dataAsOf: "2026/10/23" }],
  ])("잘못된 요청(%s)은 400이고 서비스를 부르지 않는다", async (_name, body) => {
    const res = await call(runRoute, "/x", { method: "POST", body: body === undefined ? "not json" : JSON.stringify(body) });
    expect(res.status).toBe(400);
    expect(runModified).not.toHaveBeenCalled();
  });

  it("NaN·Infinity는 JSON에 실리지 않아 누락으로 거절된다", async () => {
    const raw = '{"overrides":[{"path":"a","value":1e999}],"baseSnapshotHash":"' + HASH + '","dataAsOf":"2026-10-23"}';
    expect((await call(runRoute, "/x", { method: "POST", body: raw })).status).toBe(400);
  });

  it.each([
    [new NotPublicError(), 404, "STRATEGY_NOT_PUBLIC"],
    [new BaselineChangedError("REFRESHING"), 409, "BASELINE_CHANGED"],
    [new InvalidParameterError([{ path: "p", code: "OUT_OF_RANGE" }]), 400, "INVALID_PARAMETER"],
    [new RateLimitedError(60), 429, "RATE_LIMITED"],
    [new SimulationFailedError("BUSY", 429, 30), 429, "BUSY"],
    [new SimulationFailedError("TIMEOUT", 504), 504, "TIMEOUT"],
    [new SimulationFailedError("INCONSISTENT_RESULT", 500), 500, "INCONSISTENT_RESULT"],
    [new BoardError("보안 설정 필요", 503), 503, "RATE_LIMIT_UNAVAILABLE"],
    [new Error("db password leaked"), 500, "ENGINE_ERROR"],
  ])("서비스 오류를 상태 코드와 코드로 옮기고 내부 메시지는 싣지 않는다", async (error, status, code) => {
    vi.mocked(runModified).mockRejectedValue(error);
    const res = await post(validBody);
    const body = await res.json();
    expect([res.status, body.code]).toEqual([status, code]);
    expect(JSON.stringify(body)).not.toContain("leaked");
    expect(body).not.toHaveProperty("summary");          // 실패를 성공 모양으로 바꾸지 않는다
    if (status === 429 && code === "RATE_LIMITED") expect(res.headers.get("Retry-After")).toBe("60");
  });

  it("409 사유(갱신 중/낡은 원본)를 구분해 알린다", async () => {
    vi.mocked(runModified).mockRejectedValue(new BaselineChangedError("CHANGED"));
    expect((await (await post(validBody)).json()).reason).toBe("CHANGED");
  });

  it("형식이 틀린 publicId는 서비스를 부르지 않고 404", async () => {
    expect((await post(validBody, "../x")).status).toBe(404);
    expect(runModified).not.toHaveBeenCalled();
  });
});
