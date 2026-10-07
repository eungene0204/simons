import { newQaSessionId, sendQaLog, type QaLogPayload, type QaTurn } from "./qaLog";

export type QaDelivery = QaLogPayload & { deliveryId: string; ownerId: number | null };

// A turn can be edited by going back; an ordinal alone is not an identity.
export function qaTurnKey(turn: Pick<QaTurn, "turnIndex" | "question" | "answer" | "answerKind" | "chipAnswer" | "strategy">): string {
  return JSON.stringify([turn.turnIndex, turn.question, turn.answer, turn.answerKind, turn.chipAnswer, turn.strategy]);
}

export function createQaLogOutbox(
  ownerId: number | null,
  storage: Storage,
  send: (payload: QaDelivery) => Promise<boolean> = sendQaLog,
) {
  const prefix = `simons.qaOutbox.${ownerId ?? "anonymous"}.`;
  const pending = new Map<string, QaDelivery>();
  let busy = false;
  let stopped = false;
  try {
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (!key?.startsWith(prefix)) continue;
      try {
        const item = JSON.parse(storage.getItem(key)!);
        if (item.ownerId === ownerId && typeof item.deliveryId === "string" &&
            key === prefix + item.deliveryId) pending.set(item.deliveryId, item);
      } catch { /* Ignore malformed storage entries. */ }
    }
  } catch { /* Memory delivery still works if storage is unavailable. */ }

  async function flush() {
    if (busy || stopped) return;
    busy = true;
    try {
      for (const [id, item] of pending) {
        if (stopped || !(await send(item))) break;
        pending.delete(id);
        try { storage.removeItem(prefix + id); } catch { /* Retrying is idempotent. */ }
      }
    } catch { /* Preserve pending entries for the next retry. */ }
    finally { busy = false; }
  }

  return {
    enqueue(payload: QaLogPayload) {
      if (stopped) return;
      const key = qaTurnKey(payload);
      if ([...pending.values()].some((item) => item.sessionId === payload.sessionId && qaTurnKey(item) === key)) return;
      const item = { ...payload, ownerId, deliveryId: newQaSessionId() };
      pending.set(item.deliveryId, item);
      try { storage.setItem(prefix + item.deliveryId, JSON.stringify(item)); }
      catch { /* Keep the pending entry in memory when storage is full. */ }
      void flush();
    },
    flush,
    stop() { stopped = true; },
  };
}
