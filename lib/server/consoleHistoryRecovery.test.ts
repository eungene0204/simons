import { describe, expect, it } from "vitest";
import { planConsoleHistoryRecovery } from "./consoleHistoryRecovery";

const users = [{ id: 7, email: "guest_1234@guest.nullstock.im" }];
const messages = [{ role: "user", content: "question" }, { role: "assistant", parsed: { rsi: 30 } }];
const chat = {
  id: "chat", userId: 7, sessionId: "session", updatedAt: "2026-10-01T00:00:00Z",
  snapshot: JSON.stringify({ qaSessionId: "session", messages }),
};
const now = "2026-10-07T00:00:00Z";
const plan = (logs: any[] = [], chats = [chat]) => planConsoleHistoryRecovery(chats, logs, users, now);

describe("evidence-based console recovery", () => {
  it("restores a guest's completed turn with provenance and unknown latency", () => {
    const row = plan().inserts[0];
    expect(row).toMatchObject({ userId: 7, userEmail: users[0].email, latencyMs: null, createdAt: chat.updatedAt });
    expect(JSON.parse(row.strategySnapshot!).recovery).toMatchObject({ source: "StrategyChatLog", snapshotId: "chat" });
  });
  it("is idempotent and does not mutate its evidence", () => {
    const logs = plan().inserts;
    const before = JSON.stringify(logs);
    expect(plan(logs)).toMatchObject({ inserts: [], patches: [] });
    expect(JSON.stringify(logs)).toBe(before);
  });
  it("fills only missing cards on exact matching content", () => {
    const original = { ...plan().inserts[0], id: "original", strategySnapshot: null };
    const result = plan([original]);
    expect(result.inserts).toHaveLength(0);
    expect(result.patches).toHaveLength(1);
    expect(original.strategySnapshot).toBeNull();
    expect(plan([{ ...original, answer: "older answer" }])).toMatchObject({ patches: [] });
  });
  it("preserves the old response and adds a distinct recovered revision", () => {
    const original = { ...plan().inserts[0], question: "older question" };
    expect(plan([original]).inserts).toHaveLength(1);
    expect(plan([original]).patches).toHaveLength(0);
  });
  it("does not assign anonymous or other users' logs to the guest", () => {
    const original = { ...plan().inserts[0], userId: null };
    expect(plan([original]).inserts).toHaveLength(1);
    expect(plan([original]).patches).toHaveLength(0);
  });
  it("skips incomplete, corrupt and mismatched-session evidence", () => {
    expect(plan([], [{ ...chat, snapshot: "invalid" }]).skipped.invalid).toBe(1);
    expect(plan([], [{ ...chat, snapshot: JSON.stringify({ qaSessionId: "other", messages }) }]).skipped.invalid).toBe(1);
    expect(plan([], [{ ...chat, snapshot: JSON.stringify({ messages: [messages[0], { role: "assistant", isLoading: true }] }) }]).skipped.pending).toBe(1);
  });
});
