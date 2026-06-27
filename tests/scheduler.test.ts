import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// 스케줄러는 더 이상 자기 자신의 /api/scheduler 라우트를 HTTP 로 self-fetch 하지 않고
// runSchedulerAction 을 인-프로세스로 직접 호출한다. 그래서 dev 모드 HMR 재컴파일로
// 라우트가 일시적으로 404(HTML)를 반환해도 "Unexpected token '<'" 가 발생하지 않는다.
vi.mock("@/lib/server/scheduler-actions", () => ({
  runSchedulerAction: vi.fn(),
}));

import { runSchedulerAction } from "@/lib/server/scheduler-actions";
import { callSchedulerAPI } from "@/lib/scheduler";

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
