import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const computeCacheKey = vi.fn(() => "cache_key_1");
const fetchBackend = vi.fn();
const resolveStrategyId = vi.fn(() => "strategy_1");
const saveCachedResult = vi.fn();
let consoleLogSpy: ReturnType<typeof vi.spyOn>;

vi.mock("@/lib/server/backend", () => ({
  fetchBackend,
}));

vi.mock("@/lib/server/backtestCache", () => ({
  computeCacheKey,
  resolveStrategyId,
  saveCachedResult,
}));

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
});
