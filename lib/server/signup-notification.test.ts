import { afterEach, describe, expect, it, vi } from "vitest";
import { notifySignup } from "./signup-notification";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("signup notification", () => {
  it("skips delivery without configuration", async () => {
    vi.stubEnv("TELEGRAM_BOT_TOKEN", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await notifySignup("email");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(["email", "google"] as const)("delivers %s signup", async (method) => {
    vi.stubEnv("TELEGRAM_BOT_TOKEN", "test-token");
    vi.stubEnv("TELEGRAM_CHAT_ID", "123");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", fetchMock);
    await notifySignup(method);
    const payload = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(payload.chat_id).toBe("123");
    expect(payload.text).toContain(method === "google" ? "Google" : "이메일");
    expect(fetchMock.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
  });

  it("absorbs network failures without exposing secrets", async () => {
    vi.stubEnv("TELEGRAM_BOT_TOKEN", "secret");
    vi.stubEnv("TELEGRAM_CHAT_ID", "123");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("secret")));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await expect(notifySignup("email")).resolves.toBeUndefined();
    expect(JSON.stringify(warn.mock.calls)).not.toContain("secret");
  });
});
