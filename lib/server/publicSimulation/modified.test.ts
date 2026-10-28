import { beforeEach, describe, expect, it, vi } from "vitest";

import { BoardError } from "@/lib/board/rules";
import { limit } from "@/lib/board/server";
import { fetchBackend } from "@/lib/server/backend";
import { NotPublicError, findPublicStrategy, snapshotFromSettings, snapshotHash } from "./access";
import {
  BaselineChangedError, InvalidParameterError, RateLimitedError, SimulationFailedError, resetModifiedCache, runModified,
} from "./modified";
import { resetBaselineCache } from "./originals";

vi.mock("@/lib/prisma", () => ({ prisma: {} }));
vi.mock("./access", async (importActual) => ({
  ...(await importActual<typeof import("./access")>()),
  findPublicStrategy: vi.fn(),
}));
vi.mock("@/lib/server/backend", () => ({ fetchBackend: vi.fn() }));
vi.mock("@/lib/board/server", () => ({ limit: vi.fn() }));

const findFirst = vi.mocked(findPublicStrategy);
const backend = vi.mocked(fetchBackend);
const rateLimit = vi.mocked(limit);

const BASELINE = {
  today: "2026-10-27", requestedStart: "2023-10-27", requestedEnd: "2026-10-27", endDate: "2026-10-23",
  dataAsOf: "2026-10-23", stale: true, engineVersion: "16.43.0",
};
const settings = JSON.stringify({
  id: "7:abc", symbols: ["005930"],
  entry: { conditions: [{ type: "indicator", id: "rsi", params: { period: 14, operator: "<", value: 30 } }] },
  exit: { conditions: [] }, risk: { position_size_pct: 100, init_cash: 10_000_000 },
  options: { fee_rate: 0.00015, slippage_rate: 0.0005 },
});
const HASH = snapshotHash(snapshotFromSettings(settings));
const PERIOD = "entry.conditions.0.params.period";
const stored = {
  status: "ready", dataAsOf: "2026-10-23", engineVersion: "16.43.0",
  window: { requestedStart: "2023-10-27" }, summary: { totalReturnPct: 10 },
  editableParams: [{ path: PERIOD, original: 14, editable: true }],
};
const row = (over: Record<string, unknown> = {}) => ({
  name: "n", description: null, settings, assumptions: [],
  row: {
    id: "pub1", snapshotHash: HASH, dataAsOf: "2026-10-23", engineVersion: "16.43.0",
    status: "ready", reason: null, result: JSON.stringify(stored), computedAt: new Date(), refreshLeaseUntil: null,
    lastAttemptAt: null, lastError: null, ...over,
  },
});
const input = (overrides = [{ path: PERIOD, value: 21 }]) => ({
  publicId: "pub1", overrides, baseSnapshotHash: HASH, dataAsOf: "2026-10-23", identity: "id1",
});

function respond(status: number, body: unknown) {
  return { ok: status < 400, status, json: async () => body } as Response;
}
const RESULT = { status: "ready", summary: { totalReturnPct: -4 }, appliedOverrides: [{ path: PERIOD, value: 21 }] };
const runCalls = () => backend.mock.calls.filter((c) => String(c[0]).endsWith("/run"));

beforeEach(() => {
  vi.clearAllMocks();
  resetModifiedCache();
  resetBaselineCache();
  findFirst.mockResolvedValue(row());
  rateLimit.mockResolvedValue(undefined);
  backend.mockImplementation((async (path: string) =>
    path.endsWith("/baseline") ? respond(200, BASELINE) : respond(200, RESULT)) as any);
});

describe("예시 등록부와 원본 일치", () => {
  it("등록부에 없는 전략은 엔진을 부르지 않고 거절한다", async () => {
    findFirst.mockResolvedValue(null);
    await expect(runModified(input())).rejects.toBeInstanceOf(NotPublicError);
    expect(backend).not.toHaveBeenCalled();
    expect(rateLimit).not.toHaveBeenCalled();
  });

  it("같은 입력은 캐시를 쓰되, 등록부 확인은 매 호출마다 한다", async () => {
    expect(await runModified(input())).toEqual(RESULT);
    expect(await runModified(input())).toEqual(RESULT);
    expect(runCalls()).toHaveLength(1);          // 두 번째는 캐시
    expect(findFirst).toHaveBeenCalledTimes(2);
  });

  it("클라이언트가 가진 원본이 낡았으면(해시·기준일 불일치) 409 성격의 오류다", async () => {
    await expect(runModified({ ...input(), baseSnapshotHash: "old" })).rejects.toMatchObject({ reason: "CHANGED" });
    await expect(runModified({ ...input(), dataAsOf: "2026-10-20" })).rejects.toBeInstanceOf(BaselineChangedError);
    expect(runCalls()).toHaveLength(0);
  });

  it("원본이 새 기준일·새 '오늘' 창으로 갱신 중이면 수정 계산을 하지 않는다", async () => {
    backend.mockImplementation((async (path: string) =>
      path.endsWith("/baseline") ? respond(200, { ...BASELINE, requestedStart: "2023-10-28" }) : respond(200, RESULT)) as any);
    await expect(runModified(input())).rejects.toMatchObject({ reason: "REFRESHING" });
    expect(runCalls()).toHaveLength(0);
  });

  it("원본 결과가 아직 없으면(pending) 수정 계산을 하지 않는다", async () => {
    findFirst.mockResolvedValue(row({ status: "pending", result: null }));
    await expect(runModified(input())).rejects.toMatchObject({ reason: "REFRESHING" });
  });
});

describe("실행·캐시·제한", () => {
  it("오버라이드를 경로순으로 정렬해 백엔드에 보내고, 값이 다르면 캐시 키도 다르다", async () => {
    const two = [{ path: "z.path", value: 1 }, { path: PERIOD, value: 21 }];
    findFirst.mockResolvedValue(row({ result: JSON.stringify({ ...stored, editableParams: [...stored.editableParams, { path: "z.path", original: 5 }] }) }));
    await runModified(input(two));
    expect(JSON.parse(String(runCalls()[0][1]?.body))).toMatchObject({ overrides: [{ path: PERIOD, value: 21 }, { path: "z.path", value: 1 }] });
    await runModified(input([{ path: PERIOD, value: 22 }]));
    expect(runCalls()).toHaveLength(2);
  });

  it("같은 요청이 동시에 오면 하나로 합친다", async () => {
    let release!: (r: Response) => void;
    backend.mockImplementation((async (path: string) =>
      path.endsWith("/baseline") ? respond(200, BASELINE) : new Promise<Response>((resolve) => (release = resolve))) as any);
    const a = runModified(input());
    const b = runModified(input());
    await vi.waitFor(() => expect(runCalls()).toHaveLength(1));
    release(respond(200, RESULT));
    expect(await Promise.all([a, b])).toEqual([RESULT, RESULT]);
    expect(runCalls()).toHaveLength(1);
  });

  it("모든 값이 원본과 같으면 계산·제한 소비 없이 원본 결과를 돌려준다", async () => {
    const out = await runModified(input([{ path: PERIOD, value: 14 }]));
    expect(out).toMatchObject({ status: "ready", appliedOverrides: [], summary: { totalReturnPct: 10 } });
    expect(runCalls()).toHaveLength(0);
    expect(rateLimit).not.toHaveBeenCalled();
  });

  it("요청 제한에 걸리면 엔진을 부르지 않고 재시도 시간을 알린다", async () => {
    rateLimit.mockRejectedValue(new BoardError("요청이 너무 많습니다.", 429));
    await expect(runModified(input())).rejects.toMatchObject({ retryAfterSeconds: expect.any(Number) });
    await expect(runModified(input())).rejects.toBeInstanceOf(RateLimitedError);
    expect(runCalls()).toHaveLength(0);
    expect(rateLimit.mock.calls[0][0]).toBe("sim-run:id1");
  });

  it("제한 서비스 자체의 오류는 429로 바꾸지 않고 그대로 던진다", async () => {
    rateLimit.mockRejectedValue(new BoardError("보안 설정 필요", 503));
    await expect(runModified(input())).rejects.toMatchObject({ status: 503 });
  });
});

describe("백엔드 오류 매핑", () => {
  const failWith = (res: Response | Error) =>
    backend.mockImplementation((async (path: string) => {
      if (path.endsWith("/baseline")) return respond(200, BASELINE);
      if (res instanceof Error) throw res;
      return res;
    }) as any);

  it("400은 항목별 사유를 담은 InvalidParameterError", async () => {
    failWith(respond(400, { code: "INVALID_PARAMETER", errors: [{ path: PERIOD, code: "OUT_OF_RANGE" }] }));
    const err = await runModified(input()).catch((e) => e);
    expect(err).toBeInstanceOf(InvalidParameterError);
    expect(err.errors[0].code).toBe("OUT_OF_RANGE");
  });

  it.each([
    [respond(429, { code: "BUSY", retryAfterSeconds: 30 }), "BUSY", 429],
    [respond(504, { code: "TIMEOUT" }), "TIMEOUT", 504],
    [respond(500, { code: "INCONSISTENT_RESULT" }), "INCONSISTENT_RESULT", 500],
    [respond(500, null), "ENGINE_ERROR", 500],
    [new Error("connect"), "BACKEND_UNREACHABLE", 502],
  ])("실패는 0%나 거래 없음이 아니라 구분된 오류이며 캐시되지 않는다", async (res, code, status) => {
    failWith(res as Response | Error);
    await expect(runModified(input())).rejects.toMatchObject({ code, status });
    await expect(runModified(input())).rejects.toBeInstanceOf(SimulationFailedError);
    expect(runCalls()).toHaveLength(2);          // 실패 응답은 캐시하지 않아 매번 다시 시도
  });
});
