import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const fetchBackend = vi.fn();

vi.mock("@/lib/server/backend", () => ({
  fetchBackend,
}));

const coachRoute = await import("./route");
const coachStreamRoute = await import("./stream/route");
const { __resetCoachCacheForTests } = await import("./cache");

function makeRequest(body: object, path = "/api/strategy/coach") {
  return new NextRequest(
    new Request(`http://localhost${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
}

function makeStreamResponse(text: string) {
  return {
    ok: true,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text));
        controller.close();
      },
    }),
  };
}

describe("strategy coach proxy cache", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    __resetCoachCacheForTests();
  });

  it("reuses cached non-stream coach responses for identical payloads", async () => {
    fetchBackend.mockResolvedValue({
      ok: true,
      json: async () => ({ message: "중복 없는 코치", suggestions: [] }),
    });

    const body = {
      user_prompt: "pbr 전략",
      parsed_strategy: { universe: ["KOSPI200"] },
      advisor_insight: { strategy_score: 70 },
    };

    const first = await coachRoute.POST(makeRequest(body));
    const second = await coachRoute.POST(makeRequest(body));

    expect(fetchBackend).toHaveBeenCalledOnce();
    await expect(first.json()).resolves.toMatchObject({ message: "중복 없는 코치", cached: false });
    await expect(second.json()).resolves.toMatchObject({ message: "중복 없는 코치", cached: true });
  });

  it("proxies coach session creation without exposing advisor payloads", async () => {
    fetchBackend.mockResolvedValue({
      ok: true,
      headers: new Headers({ "X-Coach-Session-Id": "session_1" }),
      json: async () => ({ message: "세션 코치" }),
    });

    const response = await coachRoute.POST(makeRequest({
      action: "create_session",
      user_prompt: "rsi 전략",
      parsed_strategy: { entry_signals: [{ indicator: "rsi" }] },
    }));

    expect(fetchBackend).toHaveBeenCalledWith("/strategy/coach/sessions", expect.objectContaining({
      method: "POST",
      timeoutMs: 560_000,
      body: JSON.stringify({
        user_prompt: "rsi 전략",
        parsed_strategy: { entry_signals: [{ indicator: "rsi" }] },
      }),
    }));
    expect(response.headers.get("X-Coach-Session-Id")).toBe("session_1");
    await expect(response.json()).resolves.toEqual({ message: "세션 코치" });
  });

  it("falls back to legacy coach when session creation is unavailable", async () => {
    fetchBackend
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: "not found" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: "legacy coach" }),
      });

    const response = await coachRoute.POST(makeRequest({
      action: "create_session",
      user_prompt: "rsi 전략",
      parsed_strategy: { entry_signals: [{ indicator: "rsi" }] },
    }));

    expect(fetchBackend).toHaveBeenNthCalledWith(1, "/strategy/coach/sessions", expect.any(Object));
    expect(fetchBackend).toHaveBeenNthCalledWith(2, "/strategy/coach", expect.objectContaining({
      timeoutMs: 560_000,
      body: JSON.stringify({
        user_prompt: "rsi 전략",
        parsed_strategy: { entry_signals: [{ indicator: "rsi" }] },
      }),
    }));
    await expect(response.json()).resolves.toEqual({ message: "legacy coach" });
  });

  it("proxies coach session follow-ups by session id", async () => {
    fetchBackend.mockResolvedValue({
      ok: true,
      headers: new Headers(),
      json: async () => ({ message: "후속 코치" }),
    });

    const response = await coachRoute.POST(makeRequest({
      action: "follow_up",
      session_id: "session_1",
      user_prompt: "쉽게 설명해줘",
    }));

    expect(fetchBackend).toHaveBeenCalledWith("/strategy/coach/sessions/follow-up", expect.objectContaining({
      method: "POST",
      timeoutMs: 560_000,
      body: JSON.stringify({
        user_prompt: "쉽게 설명해줘",
        session_id: "session_1",
      }),
    }));
    await expect(response.json()).resolves.toEqual({ message: "후속 코치" });
  });

  it("replays cached coach streams for identical payloads", async () => {
    const streamText = 'data: {"type":"delta","message":"요약"}\n\ndata: {"type":"done","message":"요약"}\n\n';
    fetchBackend.mockResolvedValue(makeStreamResponse(streamText));

    const body = {
      user_prompt: "rsi 전략",
      parsed_strategy: { entry_signals: [{ indicator: "rsi" }] },
    };

    const first = await coachStreamRoute.POST(makeRequest(body, "/api/strategy/coach/stream"));
    expect(await first.text()).toBe(streamText);

    const second = await coachStreamRoute.POST(makeRequest(body, "/api/strategy/coach/stream"));
    expect(await second.text()).toBe(streamText);
    expect(fetchBackend).toHaveBeenCalledOnce();
  });
});
