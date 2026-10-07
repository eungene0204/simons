import { createHash } from "crypto";
import { collectQaTurns } from "@/app/analytics/new/qaLog";
import { strategySnapshotJson } from "./qaLogStrategy";

export const RECOVERED_QA_PREFIX = "qa-recovered-v1-";

type Chat = { id: string; userId: number; sessionId: string; snapshot: string; updatedAt: string };
type Log = {
  id: string; userId: number | null; sessionId: string; turnIndex: number;
  question: string; answer: string; answerKind: string; chipAnswer: boolean;
  strategySnapshot: string | null;
};
type User = { id: number; email: string };

export function planConsoleHistoryRecovery(chats: Chat[], logs: Log[], users: User[], recoveredAt: string) {
  const inserts: (Log & { userEmail: string; latencyMs: null; createdAt: string })[] = [];
  const patches: { id: string; strategySnapshot: string }[] = [];
  const skipped = { invalid: 0, pending: 0, missingUser: 0 };
  const known = [...logs];
  for (const chat of chats) {
    const user = users.find((u) => u.id === chat.userId);
    if (!user) { skipped.missingUser++; continue; }
    let snapshot;
    try { snapshot = JSON.parse(chat.snapshot); } catch { skipped.invalid++; continue; }
    if (!Array.isArray(snapshot?.messages) ||
        snapshot.messages.some((m: unknown) => !m || typeof m !== "object") ||
        (snapshot.qaSessionId && snapshot.qaSessionId !== chat.sessionId) ||
        !Number.isFinite(Date.parse(chat.updatedAt))) { skipped.invalid++; continue; }
    let turns;
    try { turns = collectQaTurns(snapshot.messages); } catch { skipped.invalid++; continue; }
    for (const turn of turns) {
      if (turn.pending || !turn.question || !turn.answer || turn.answerKind === "none") {
        skipped.pending++; continue;
      }
      const content = {
        userId: chat.userId, sessionId: chat.sessionId, turnIndex: turn.turnIndex,
        question: turn.question.slice(0, 4000), answer: turn.answer.slice(0, 20000),
        answerKind: turn.answerKind, chipAnswer: turn.chipAnswer,
      };
      const matches = known.filter((log) => Object.entries(content).every(
        ([key, value]) => log[key as keyof Log] === value,
      ));
      const card = strategySnapshotJson(turn.strategy);
      const strategySnapshot = card ? JSON.stringify({
        ...JSON.parse(card),
        recovery: {
          source: "StrategyChatLog", snapshotId: chat.id,
          snapshotUpdatedAt: chat.updatedAt, recoveredAt,
          snapshotHash: createHash("sha256").update(chat.snapshot).digest("hex"),
        },
      }) : null;
      if (matches.length) {
        for (const log of matches) {
          if (log.strategySnapshot === null && strategySnapshot) {
            patches.push({ id: log.id, strategySnapshot });
            // The local copy prevents duplicate patch proposals without mutating inputs.
            known[known.indexOf(log)] = { ...log, strategySnapshot };
          }
        }
        continue;
      }
      const row = {
        ...content,
        id: RECOVERED_QA_PREFIX + createHash("sha256").update(JSON.stringify(content)).digest("hex"),
        userEmail: user.email, latencyMs: null, strategySnapshot,
        // This is evidence of the snapshot save, not a reconstructed response time.
        createdAt: chat.updatedAt,
      };
      inserts.push(row);
      known.push(row);
    }
  }
  return { inserts, patches, skipped };
}
