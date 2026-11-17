import { afterEach, describe, expect, it, vi } from "vitest";
import { prisma } from "@/lib/prisma";

vi.mock("@/lib/prisma", () => ({ prisma: { user: { count: vi.fn() } } }));

import { notifySignup } from "./signup-notification";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.mocked(prisma.user.count).mockReset();
});

describe("signup notification", () => {
  it("skips delivery without configuration", async () => {
    vi.stubEnv("TELEGRAM_BOT_TOKEN", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await notifySignup("email", 42, "member@example.com");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(["email", "google"] as const)("delivers %s signup", async (method) => {
    vi.stubEnv("TELEGRAM_BOT_TOKEN", "test-token");
    vi.stubEnv("TELEGRAM_CHAT_ID", "123");
    vi.mocked(prisma.user.count).mockResolvedValue(17);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", fetchMock);
    await notifySignup(method, 42, "member@example.com");
    const payload = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(payload.text).toContain("nullStock 신규 가입\n가입 계정: member@example.com\n가입 순서: 17번째 가입자\n가입자 ID: 42\n");
    expect(prisma.user.count).toHaveBeenCalledWith({ where: { id: { lte: 42 } } });
    expect(payload.text).not.toContain("Simons");
    expect(payload.chat_id).toBe("123");
    expect(payload.text).toContain(method === "google" ? "Google" : "이메일");
    expect(fetchMock.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
  });

  it("keeps signup successful when counting fails", async () => {
    vi.stubEnv("TELEGRAM_BOT_TOKEN", "test-token");
    vi.stubEnv("TELEGRAM_CHAT_ID", "123");
    vi.mocked(prisma.user.count).mockRejectedValue(new Error("database unavailable"));
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "warn").mockImplementation(() => {});
    await expect(notifySignup("google", 42, "member@example.com")).resolves.toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("absorbs network failures without exposing secrets", async () => {
    vi.stubEnv("TELEGRAM_BOT_TOKEN", "secret");
    vi.stubEnv("TELEGRAM_CHAT_ID", "123");
    vi.mocked(prisma.user.count).mockResolvedValue(17);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("secret")));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await expect(notifySignup("email", 42, "member@example.com")).resolves.toBeUndefined();
    expect(JSON.stringify(warn.mock.calls)).not.toContain("secret");
  });
});
