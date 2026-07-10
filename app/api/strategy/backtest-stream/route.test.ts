import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PLAN_LIMIT_BACKTESTS } from "@/lib/server/planLimits";

const computeCacheKey = vi.fn(() => "cache_key_1");
const fetchBackend = vi.fn();
const resolveStrategyId = vi.fn(() => "strategy_1");
const saveCachedResult = vi.fn();
// vi.mock 팩토리는 호이스팅되므로, 팩토리에서 참조하는 목 함수는 vi.hoisted로 선언한다.
const { getCurrentUser, consumeBacktestQuota } = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  consumeBacktestQuota: vi.fn(),
}));
let consoleLogSpy: ReturnType<typeof vi.spyOn>;

vi.mock("@/lib/server/backend", () => ({
  fetchBackend,
}));

vi.mock("@/lib/server/backtestCache", () => ({
  computeCacheKey,
  resolveStrategyId,
  saveCachedResult,
}));

vi.mock("@/lib/get-user", () => ({
  getCurrentUser,
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {},
}));

vi.mock("@/lib/server/planLimits", async () => {
  const actual = await vi.importActual<typeof import("@/lib/server/planLimits")>(
    "@/lib/server/planLimits"
  );
  return {
    ...actual,
    consumeBacktestQuota,
  };
});

const route = await import("./route");

function makeRequest(body: object) {
  return new NextRequest(
    new Request("http://localhost/api/strategy/backtest-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
}

function makeSseResponse(text: string) {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ "Content-Type": "text/event-stream" }),
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text));
        controller.close();
      },
    }),
  };
}

function makeSplitSseResponse(chunks: string[]) {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ "Content-Type": "text/event-stream" }),
    body: new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        for (const chunk of chunks) {
          controller.enqueue(encoder.encode(chunk));
        }
        controller.close();
      },
    }),
  };
}

describe("strategy backtest stream route", () => {
  beforeEach(() => {
    computeCacheKey.mockReturnValue("cache_key_1");
    fetchBackend.mockReset();
    resolveStrategyId.mockReturnValue("strategy_1");
    saveCachedResult.mockReset();
    getCurrentUser.mockReset();
    getCurrentUser.mockResolvedValue(null);
    consumeBacktestQuota.mockReset();
    consumeBacktestQuota.mockResolvedValue(undefined);
    consoleLogSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
  });

  it("sends final SSE before async cache persistence finishes", async () => {
    let resolveSave!: () => void;
    const savePromise = new Promise<void>((resolve) => {
      resolveSave = resolve;
    });
    fetchBackend.mockResolvedValueOnce(makeSseResponse([
      'data: {"type":"result","data":{"totalReturn":12.3}}\n\n',
      "data: [DONE]\n\n",
    ].join("")));
    saveCachedResult.mockReturnValueOnce(savePromise);

    const response = await route.POST(makeRequest({
      symbols: ["005930"],
      canonical_strategy_dsl: { universe: "KOSPI" },
    }));

    const text = await response.text();
    expect(text).toContain('"type":"result"');
    expect(text).toContain("[DONE]");
    resolveSave();
    await savePromise;

    expect(saveCachedResult).toHaveBeenCalledWith(
      "cache_key_1",
      expect.objectContaining({ symbols: ["005930"] }),
      expect.objectContaining({
        totalReturn: 12.3,
        strategy_id: "strategy_1",
      })
    );
    const logLines = consoleLogSpy.mock.calls.map(([message]) => String(message));
    expect(logLines.some((line) => line.includes("request_received"))).toBe(true);
    expect(logLines.some((line) => line.includes("python_backend_request_start"))).toBe(true);
    expect(logLines.some((line) => line.includes("python_result_received"))).toBe(true);
    expect(logLines.some((line) => line.includes("cache_save_queued"))).toBe(true);
    expect(logLines.some((line) => line.includes("sse_done_sent"))).toBe(true);
    expect(logLines.some((line) => line.includes("stream_closed"))).toBe(true);
  });

  it("always calls the Python backend even for a request matching a prior cacheKey", async () => {
    fetchBackend.mockResolvedValueOnce(makeSseResponse([
      'data: {"type":"result","data":{"totalReturn":1.2}}\n\n',
      "data: [DONE]\n\n",
    ].join("")));

    const response = await route.POST(makeRequest({
      symbols: ["005930"],
      canonical_strategy_dsl: { universe: "KOSPI" },
    }));

    await response.text();

    expect(fetchBackend).toHaveBeenCalledTimes(1);
  });

  it("forwards a result when result and done remain in the final backend buffer", async () => {
    fetchBackend.mockResolvedValueOnce(makeSplitSseResponse([
      'data: {"type":"status","message":"분석 완료!"}\n\n',
      'data: {"type":"result","data":{"totalReturn":7.7,"signals":[]}}\n\ndata: [DONE]',
    ]));
    saveCachedResult.mockResolvedValueOnce(undefined);

    const response = await route.POST(makeRequest({
      symbols: ["005930"],
      canonical_strategy_dsl: { universe: "KOSPI" },
    }));

    const text = await response.text();

    expect(text).toContain('"message":"분석 완료!"');
    expect(text).toContain('"type":"result"');
    expect(text).toContain('"totalReturn":7.7');
    expect(text).toContain("[DONE]");
    expect(saveCachedResult).toHaveBeenCalled();
  });

  it("consumes one backtest quota for a logged-in user", async () => {
    getCurrentUser.mockResolvedValue({ id: 42 });
    fetchBackend.mockResolvedValueOnce(makeSseResponse([
      'data: {"type":"result","data":{"totalReturn":1.2}}\n\n',
      "data: [DONE]\n\n",
    ].join("")));

    const response = await route.POST(makeRequest({
      symbols: ["005930"],
      canonical_strategy_dsl: { universe: "KOSPI" },
    }));
    await response.text();

    expect(consumeBacktestQuota).toHaveBeenCalledTimes(1);
    expect(consumeBacktestQuota).toHaveBeenCalledWith(expect.anything(), 42);
    expect(fetchBackend).toHaveBeenCalledTimes(1);
  });

  it("returns 429 without running the engine when the monthly limit is reached", async () => {
    getCurrentUser.mockResolvedValue({ id: 42 });
    consumeBacktestQuota.mockRejectedValueOnce(new Error(PLAN_LIMIT_BACKTESTS));

    const response = await route.POST(makeRequest({
      symbols: ["005930"],
      canonical_strategy_dsl: { universe: "KOSPI" },
    }));

    expect(response.status).toBe(429);
    const body = await response.json();
    expect(body.code).toBe(PLAN_LIMIT_BACKTESTS);
    expect(body.detail).toBeTruthy();
    expect(fetchBackend).not.toHaveBeenCalled();
  });

  it("does not consume quota for an anonymous (logged-out) user", async () => {
    getCurrentUser.mockResolvedValue(null);
    fetchBackend.mockResolvedValueOnce(makeSseResponse([
      'data: {"type":"result","data":{"totalReturn":1.2}}\n\n',
      "data: [DONE]\n\n",
    ].join("")));

    const response = await route.POST(makeRequest({
      symbols: ["005930"],
      canonical_strategy_dsl: { universe: "KOSPI" },
    }));
    await response.text();

    expect(consumeBacktestQuota).not.toHaveBeenCalled();
    expect(fetchBackend).toHaveBeenCalledTimes(1);
  });
});
