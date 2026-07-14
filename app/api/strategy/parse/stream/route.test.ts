import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const fetchBackend = vi.fn();

vi.mock("@/lib/server/backend", () => ({
  fetchBackend,
}));

const { POST } = await import("./route");

// 백엔드 /strategy/parse-stream 의 SSE 응답을 흉내내는 ReadableStream을 만든다.
function sseBackendResponse(events: Array<object | string>) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) {
        const payload = typeof event === "string" ? event : JSON.stringify(event);
        controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
      }
      controller.close();
    },
  });
  return { ok: true, body };
}

function backendResultEvents(data: object) {
  return [
    { type: "stage", stage: "parsing" },
    { type: "result", data },
    "[DONE]",
  ];
}

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

  it("emits accepted, skeleton, and stage before final parse events", async () => {
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(
        backendResultEvents({
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
        })
      )
    );

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
    expect(JSON.parse(events[2])).toEqual({ type: "stage", stage: "parsing" });
    expect(JSON.parse(events[3])).toMatchObject({
      type: "parsed_final",
      parsed: {
        description: "pbr 1이하 10개 1년 보유",
      },
    });
    expect(JSON.parse(events[4])).toMatchObject({
      type: "dsl_ready",
      symbol_count: 1,
    });
    expect(events[5]).toBe("[DONE]");
  });

  it("forwards a thinking stage event when the backend falls back to the LLM", async () => {
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse([
        { type: "stage", stage: "parsing" },
        { type: "stage", stage: "thinking" },
        {
          type: "result",
          data: {
            parsed: { description: "복잡한 전략", universe: ["KOSPI"] },
            backtest_request: { strategy_id: "h", symbols: ["005930"], symbol_count: 1 },
            symbol_count: 1,
          },
        },
        "[DONE]",
      ])
    );

    const response = await POST(makeRequest({ prompt: "복잡한 서술형 전략", backend: "ollama" }));
    const events = await readEvents(response);
    const stages = events
      .map((e) => {
        try {
          return JSON.parse(e);
        } catch {
          return null;
        }
      })
      .filter((e) => e?.type === "stage")
      .map((e) => e.stage);
    expect(stages).toEqual(["parsing", "thinking"]);
  });

  it("uses previous parsed universe for modification skeleton when prompt omits universe", async () => {
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(
        backendResultEvents({
          parsed: {
            description: "KOSPI PBR strategy",
            universe: ["KOSPI"],
            trailing_stop_pct: 15,
          },
          backtest_request: {
            strategy_id: "hash_value",
            universe_id: "kospi",
            symbols: ["005930"],
            symbol_count: 1,
          },
          symbol_count: 1,
        })
      )
    );

    const response = await POST(makeRequest({
      prompt: "트레일링 15% 추가해줘",
      backend: "mlx",
      previous_parsed: {
        universe: ["KOSPI"],
      },
    }));

    const events = await readEvents(response);
    expect(JSON.parse(events[1])).toMatchObject({
      type: "skeleton",
      data: {
        universe: ["KOSPI"],
      },
    });
  });

  it("uses explicit prompt universe over previous parsed universe", async () => {
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse(
        backendResultEvents({
          parsed: {
            description: "KOSPI200 strategy",
            universe: ["KOSPI200"],
          },
          backtest_request: {
            strategy_id: "hash_value",
            universe_id: "kospi200",
            symbols: ["069500"],
            symbol_count: 1,
          },
          symbol_count: 1,
        })
      )
    );

    const response = await POST(makeRequest({
      prompt: "KOSPI200으로 바꿔줘",
      backend: "mlx",
      previous_parsed: {
        universe: ["KOSPI"],
      },
    }));

    const events = await readEvents(response);
    expect(JSON.parse(events[1])).toMatchObject({
      type: "skeleton",
      data: {
        universe: ["KOSPI200"],
      },
    });
  });

  it("forwards a deferred validation correction as a parsed_updated event", async () => {
    // 비차단 검증: 백엔드가 result를 먼저 보내고, 후행 LLM 검증 교정본을 result_update로
    // 후속 전송한다. 프록시는 이를 parsed_updated 단일 이벤트로 변환해야 한다.
    fetchBackend.mockResolvedValueOnce(
      sseBackendResponse([
        { type: "stage", stage: "parsing" },
        {
          type: "result",
          data: {
            parsed: { description: "반도체 위주 PBR 전략", universe: ["KOSPI", "KOSDAQ"] },
            backtest_request: { strategy_id: "h1", symbols: ["005930"], symbol_count: 1 },
            symbol_count: 1,
          },
        },
        {
          type: "result_update",
          data: {
            parsed: {
              description: "반도체 위주 PBR 전략",
              universe: ["KOSPI", "KOSDAQ"],
              sector: "반도체",
            },
            backtest_request: { strategy_id: "h2", symbols: ["005930", "000660"], symbol_count: 2 },
            symbol_count: 2,
          },
        },
        "[DONE]",
      ])
    );

    const response = await POST(makeRequest({ prompt: "반도체 위주 PBR 전략", backend: "ollama" }));
    const events = await readEvents(response);
    const parsedEvents = events
      .map((e) => {
        try {
          return JSON.parse(e);
        } catch {
          return null;
        }
      })
      .filter(Boolean);

    const updated = parsedEvents.find((e) => e.type === "parsed_updated");
    expect(updated).toMatchObject({
      parsed: { sector: "반도체" },
      backtest_request: { strategy_id: "h2" },
      symbol_count: 2,
    });
    // 순서: parsed_final/dsl_ready(즉답) 이후에 parsed_updated가 온다.
    const order = parsedEvents.map((e) => e.type);
    expect(order.indexOf("parsed_updated")).toBeGreaterThan(order.indexOf("dsl_ready"));
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
