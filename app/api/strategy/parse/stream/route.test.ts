import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const fetchBackend = vi.fn();

vi.mock("@/lib/server/backend", () => ({
  fetchBackend,
}));

const { POST } = await import("./route");

function makeRequest(body: object) {
  return new NextRequest(
    new Request("http://localhost/api/strategy/parse/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
}

async function readEvents(response: Response) {
  const text = await response.text();
  return text
    .split("\n\n")
    .filter(Boolean)
    .map((chunk) => chunk.replace(/^data: /, ""));
}

describe("POST /api/strategy/parse/stream", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("emits accepted and skeleton before final parse events", async () => {
    fetchBackend.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        parsed: {
          description: "pbr 1이하 10개 1년 보유",
          universe: ["KOSPI200"],
          fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
        },
        backtest_request: {
          strategy_id: "hash_value",
          symbols: ["005930"],
          symbol_count: 1,
        },
        symbol_count: 1,
      }),
    });

    const response = await POST(makeRequest({ prompt: "pbr 1이하 10개 1년 보유", backend: "mlx" }));

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toContain("text/event-stream");

    const events = await readEvents(response);
    expect(JSON.parse(events[0])).toEqual({ type: "accepted" });
    expect(JSON.parse(events[1])).toMatchObject({
      type: "skeleton",
      data: {
        universe: ["KOSPI200"],
        max_positions: 10,
        confidence: "partial",
      },
    });
    expect(JSON.parse(events[2])).toMatchObject({
      type: "parsed_final",
      parsed: {
        description: "pbr 1이하 10개 1년 보유",
      },
    });
    expect(JSON.parse(events[3])).toMatchObject({
      type: "dsl_ready",
      symbol_count: 1,
    });
    expect(events[4]).toBe("[DONE]");
  });

  it("forwards backend parse errors as SSE error events", async () => {
    fetchBackend.mockResolvedValueOnce({
      ok: false,
      statusText: "Bad Request",
      json: async () => ({ detail: "parse failed" }),
    });

    const response = await POST(makeRequest({ prompt: "bad prompt", backend: "mlx" }));
    const events = await readEvents(response);

    expect(JSON.parse(events[0])).toEqual({ type: "accepted" });
    expect(JSON.parse(events[2])).toEqual({ type: "error", detail: "parse failed" });
    expect(events[3]).toBe("[DONE]");
  });

  it("returns 400 for invalid JSON", async () => {
    const response = await POST(
      new NextRequest(
        new Request("http://localhost/api/strategy/parse/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{",
        })
      )
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ detail: "Invalid JSON" });
    expect(fetchBackend).not.toHaveBeenCalled();
  });
});
