import { afterEach, expect, it, vi } from "vitest";
import { notifyWithdrawal } from "./notification";

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("sends withdrawal details with original account email", async () => {
  vi.stubEnv("TELEGRAM_BOT_TOKEN", "test-token");
  vi.stubEnv("TELEGRAM_CHAT_ID", "123");
  const send = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
  vi.stubGlobal("fetch", send);
  await notifyWithdrawal(7, "member@example.com");
  const body = JSON.parse(send.mock.calls[0][1].body);
  expect(body.chat_id).toBe("123");
  expect(body.text).toContain("nullStock 회원 탈퇴\n탈퇴 계정: member@example.com\n사용자 ID: 7");
});

it("skips unconfigured notifications", async () => {
  vi.stubEnv("TELEGRAM_BOT_TOKEN", "");
  const send = vi.fn(); vi.stubGlobal("fetch", send);
  await notifyWithdrawal(7, "member@example.com");
  expect(send).not.toHaveBeenCalled();
});

it.each(["network", "api"])("absorbs %s failures without leaking secrets", async (kind) => {
  vi.stubEnv("TELEGRAM_BOT_TOKEN", "private-token");
  vi.stubEnv("TELEGRAM_CHAT_ID", "123");
  vi.stubGlobal("fetch", kind === "network"
    ? vi.fn().mockRejectedValue(new Error("private-token"))
    : vi.fn().mockResolvedValue({ ok: false, json: async () => ({ ok: false }) }));
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  await expect(notifyWithdrawal(7, "member@example.com")).resolves.toBeUndefined();
  expect(warn).toHaveBeenCalled();
  expect(JSON.stringify(warn.mock.calls)).not.toContain("private-token");
});
