import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const backtestHistoryFindUnique = vi.fn();
const strategyFindUnique = vi.fn();
const strategyFindFirst = vi.fn();
const userBacktestHistoryFindUnique = vi.fn();
const getSessionUserId = vi.fn();
const assertActiveUser = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    backtestHistory: { findUnique: backtestHistoryFindUnique },
    strategy: { findUnique: strategyFindUnique, findFirst: strategyFindFirst },
    userBacktestHistory: { findUnique: userBacktestHistoryFindUnique },
  },
}));

vi.mock("@/lib/get-user", () => ({
  getSessionUserId: () => getSessionUserId(),
  assertActiveUser: (userId: number) => assertActiveUser(userId),
  isUnauthorizedAccessError: () => false,
}));

let GET: any;

beforeAll(async () => {
  GET = (await import("./route")).GET;
});

const baseRow = {
  id: "hist-1",
  strategyId: null as string | null,
  prompt: null as string | null,
  strategyName: "골드 크로스",
  universe: "KOSPI",
  conditions: JSON.stringify({ entry: { logic: "AND", names: ["MA 크로스"] } }),
  metrics: JSON.stringify({ totalReturn: 1 }),
  result: null,
  createdAt: new Date("2026-06-14T15:00:00Z"),
};

describe("app/api/backtest/history/[id] GET prompt 해석", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSessionUserId.mockResolvedValue(7);
    assertActiveUser.mockResolvedValue(undefined);
    userBacktestHistoryFindUnique.mockResolvedValue({ id: "link-1" });
  });

  it("기록에 스냅샷된 prompt가 있으면 그대로 반환하되, 워크포워드용 settings는 Strategy에서 가져온다", async () => {
    backtestHistoryFindUnique.mockResolvedValue({
      ...baseRow,
      strategyId: "strat-1",
      prompt: "  스냅샷 원문 프롬프트  ",
    });
    strategyFindUnique.mockResolvedValue({
      description: "무시됨",
      settings: JSON.stringify({ risk: { stop_loss_pct: 10 } }),
    });

    const response = await GET(new Request("http://localhost/api/backtest/history/hist-1"), {
      params: { id: "hist-1" },
    });
    const payload = await response.json();

    // 프롬프트는 스냅샷 SOT를 그대로 사용(Strategy의 description으로 덮어쓰지 않음)
    expect(payload.prompt).toBe("스냅샷 원문 프롬프트");
    expect(payload.settings).toEqual({ risk: { stop_loss_pct: 10 } });
    expect(strategyFindUnique).toHaveBeenCalledWith({
      where: { id: "strat-1" },
      select: { description: true, settings: true },
    });
  });

  it("strategyId 직결이 없으면 동일 이름 Strategy에서 원문 프롬프트를 끌어온다", async () => {
    backtestHistoryFindUnique.mockResolvedValue({ ...baseRow, strategyId: null });
    strategyFindFirst.mockResolvedValue({
      description: "골드 크로스",
      settings: JSON.stringify({ description: "KOSPI 골든크로스가 나오면 매수하는 전략" }),
    });

    const response = await GET(new Request("http://localhost/api/backtest/history/hist-1"), {
      params: { id: "hist-1" },
    });
    const payload = await response.json();

    expect(response.status).toBe(200);
    // strategyId가 없으므로 findUnique(strategy)는 호출하지 않고 findFirst(by name)만 호출
    expect(strategyFindUnique).not.toHaveBeenCalled();
    expect(strategyFindFirst).toHaveBeenCalledWith({
      where: { name: "골드 크로스", OR: [{ userId: null }, { userId: 7 }] },
      orderBy: { createdAt: "desc" },
      select: { description: true, settings: true },
    });
    expect(payload.prompt).toBe("KOSPI 골든크로스가 나오면 매수하는 전략");
    expect(payload.settings).toEqual({ description: "KOSPI 골든크로스가 나오면 매수하는 전략" });
  });

  it("strategyId 직결이 있으면 해당 Strategy로 프롬프트를 해석한다", async () => {
    backtestHistoryFindUnique.mockResolvedValue({ ...baseRow, strategyId: "strat-1" });
    strategyFindUnique.mockResolvedValue({
      description: "원문 프롬프트",
      settings: JSON.stringify({}),
    });

    const response = await GET(new Request("http://localhost/api/backtest/history/hist-1"), {
      params: { id: "hist-1" },
    });
    const payload = await response.json();

    expect(strategyFindUnique).toHaveBeenCalledWith({
      where: { id: "strat-1" },
      select: { description: true, settings: true },
    });
    expect(strategyFindFirst).not.toHaveBeenCalled();
    expect(payload.prompt).toBe("원문 프롬프트");
    expect(payload.settings).toEqual({});
  });

  it("원천 Strategy를 못 찾으면 prompt는 빈 문자열이고 settings는 null", async () => {
    backtestHistoryFindUnique.mockResolvedValue({ ...baseRow, strategyId: null });
    strategyFindFirst.mockResolvedValue(null);

    const response = await GET(new Request("http://localhost/api/backtest/history/hist-1"), {
      params: { id: "hist-1" },
    });
    const payload = await response.json();

    expect(payload.prompt).toBe("");
    expect(payload.strategyName).toBe("골드 크로스");
    expect(payload.settings).toBeNull();
  });
});

describe("app/api/backtest/history/[id] GET 소유권", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSessionUserId.mockResolvedValue(7);
    assertActiveUser.mockResolvedValue(undefined);
    userBacktestHistoryFindUnique.mockResolvedValue({ id: "link-1" });
    backtestHistoryFindUnique.mockResolvedValue({ ...baseRow });
    strategyFindFirst.mockResolvedValue(null);
  });

  it("비로그인 요청은 기록을 조회하지 않고 401", async () => {
    getSessionUserId.mockResolvedValue(null);

    const response = await GET(new Request("http://localhost/api/backtest/history/hist-1"), {
      params: { id: "hist-1" },
    });

    expect(response.status).toBe(401);
    expect(backtestHistoryFindUnique).not.toHaveBeenCalled();
  });

  it("내 목록에 담기지 않은 남의 기록은 본문을 돌려주지 않고 404", async () => {
    userBacktestHistoryFindUnique.mockResolvedValue(null);

    const response = await GET(new Request("http://localhost/api/backtest/history/hist-1"), {
      params: { id: "hist-1" },
    });
    const payload = await response.json();

    expect(response.status).toBe(404);
    expect(payload.prompt).toBeUndefined();
    expect(payload.result).toBeUndefined();
    expect(userBacktestHistoryFindUnique).toHaveBeenCalledWith({
      where: { userId_backtestHistoryId: { userId: 7, backtestHistoryId: "hist-1" } },
      select: { id: true },
    });
  });

  it("내 목록에 담긴 기록은 그대로 연다", async () => {
    const response = await GET(new Request("http://localhost/api/backtest/history/hist-1"), {
      params: { id: "hist-1" },
    });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ id: "hist-1" });
  });
});
