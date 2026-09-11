import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// 스케줄러는 더 이상 자기 자신의 /api/scheduler 라우트를 HTTP 로 self-fetch 하지 않고
// runSchedulerAction 을 인-프로세스로 직접 호출한다. 그래서 dev 모드 HMR 재컴파일로
// 라우트가 일시적으로 404(HTML)를 반환해도 "Unexpected token '<'" 가 발생하지 않는다.
vi.mock("@/lib/server/scheduler-actions", () => ({
  runSchedulerAction: vi.fn(),
}));

vi.mock("@/lib/server/dataRetention", () => ({
  purgeExpiredRecords: vi.fn(),
}));

// 같은 분(정각)에 구독 갱신 잡도 함께 발화하므로, 그 잡이 조용히 끝나도록 최소 형태만 준다.
vi.mock("@/lib/prisma", () => ({
  prisma: { user: { findMany: async () => [] } },
}));

import { runSchedulerAction } from "@/lib/server/scheduler-actions";
import { purgeExpiredRecords } from "@/lib/server/dataRetention";
import { callSchedulerAPI, startScheduler, stopScheduler } from "@/lib/scheduler";

const mockedRun = vi.mocked(runSchedulerAction);

describe("callSchedulerAPI", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(global, "fetch");
    mockedRun.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("HTTP self-fetch 없이 runSchedulerAction 을 직접 호출한다", async () => {
    mockedRun.mockResolvedValue({ action: "market-refresh", results: [] });

    await callSchedulerAPI("market-refresh");

    expect(mockedRun).toHaveBeenCalledWith("market-refresh");
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("runSchedulerAction 이 throw 해도 콘솔 error 로만 남기고 다시 throw 하지 않는다", async () => {
    mockedRun.mockRejectedValue(new Error("boom"));

    await expect(callSchedulerAPI("market-close")).resolves.toBeUndefined();
    expect(console.error).toHaveBeenCalledTimes(1);
  });

  it("market-close 결과의 paused 개수를 로그로 남긴다", async () => {
    mockedRun.mockResolvedValue({ action: "market-close", paused: 3 });

    await callSchedulerAPI("market-close");

    expect(console.log).toHaveBeenCalledWith(
      expect.stringContaining("3개 계좌 일시정지")
    );
    expect(console.error).not.toHaveBeenCalled();
  });
});

// USD 계좌 생명주기는 ET 시계로 발화한다 — KST 시계만 보던 종전 구조에서는 미국
// 정규장(KST 밤)에 계좌가 항상 paused 라 자동매매가 한 번도 돌지 않았다.
describe("tick — 미국장(ET) 생명주기 발화", () => {
  beforeEach(() => {
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockedRun.mockReset();
    mockedRun.mockResolvedValue({ action: "noop" });
    vi.useFakeTimers();
  });

  afterEach(() => {
    stopScheduler();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("09:30 ET(평일)에 us-market-open 을 발화한다", () => {
    // 2026-09-02(수) 09:30 EDT = 13:30 UTC = 22:30 KST
    vi.setSystemTime(new Date("2026-09-02T13:30:10Z"));

    startScheduler(); // 시작 직후 tick 1회 실행

    expect(mockedRun).toHaveBeenCalledWith("us-market-open");
  });

  it("금요일 16:00 ET 마감은 KST 로 토요일 새벽이어도 발화한다 (KST 주말 가드에 막히면 안 됨)", () => {
    // 2026-09-04(금) 16:00 EDT = 20:00 UTC = 09-05(토) 05:00 KST
    vi.setSystemTime(new Date("2026-09-04T20:00:20Z"));

    startScheduler();

    expect(mockedRun).toHaveBeenCalledWith("us-market-close");
    // 한국장 이벤트는 발화하지 않는다 (KST 기준 주말 + 시각 불일치)
    expect(mockedRun).not.toHaveBeenCalledWith("market-close");
  });

  it("ET 주말에는 미국장 이벤트를 발화하지 않는다", () => {
    // 2026-09-05(토) 09:30 EDT
    vi.setSystemTime(new Date("2026-09-05T13:30:10Z"));

    startScheduler();

    expect(mockedRun).not.toHaveBeenCalledWith("us-market-open");
  });
});

// 보존기간 파기는 주말에도 돌아야 한다 — 개인정보 파기는 장 달력과 무관하다.
describe("tick — 보존기간 파기 발화", () => {
  const mockedPurge = vi.mocked(purgeExpiredRecords);

  beforeEach(() => {
    vi.spyOn(console, "log").mockImplementation(() => {});
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockedRun.mockReset();
    mockedRun.mockResolvedValue({ action: "noop" });
    mockedPurge.mockReset();
    mockedPurge.mockResolvedValue({
      chatQaLog: 0,
      emailVerification: 0,
      paymentWebhookEvent: 0,
      adminAuditLog: 0,
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    stopScheduler();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("04:00 KST에 파기 잡을 발화한다", async () => {
    // 2026-09-09(수) 04:00 KST = 2026-09-08 19:00 UTC
    vi.setSystemTime(new Date("2026-09-08T19:00:05Z"));

    startScheduler();
    await vi.waitFor(() => expect(mockedPurge).toHaveBeenCalledTimes(1));
  });

  it("주말에도 발화한다", async () => {
    // 2026-09-13(일) 04:00 KST = 2026-09-12 19:00 UTC
    vi.setSystemTime(new Date("2026-09-12T19:00:05Z"));

    startScheduler();
    await vi.waitFor(() => expect(mockedPurge).toHaveBeenCalledTimes(1));
  });

  it("다른 시각에는 발화하지 않는다", () => {
    // 2026-09-09(수) 05:00 KST
    vi.setSystemTime(new Date("2026-09-08T20:00:05Z"));

    startScheduler();

    expect(mockedPurge).not.toHaveBeenCalled();
  });
});
