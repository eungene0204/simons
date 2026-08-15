// 대화 기록(Q&A 로그) — 사용자가 무엇을 묻고 우리가 무엇을 답했는지 한 턴에 한 건으로 남긴다.
// 운영 콘솔에서 답변을 되짚어 보기 위한 기록이며, 화면 표시에는 쓰이지 않는다.
//
// 여기서 하는 일은 **이미 화면에 그려진 우리 메시지 객체**를 텍스트로 옮겨 적는 것뿐이다.
// 사용자 원문의 의미를 판정하지 않는다(대원칙 1) — 질문은 원문 그대로 싣고, 답변의 종류
// (answerKind)는 우리가 채운 필드가 무엇인지만 보고 정한다.

export type QaChatMessage = {
  role: string;
  content?: string;
  parsed?: unknown;
  coachText?: string;
  infoText?: string;
  clarification?: string;
  clarificationSuggestions?: string[];
  infoSuggestions?: string[];
  notices?: string[];
  error?: string;
  isLoading?: boolean;
  coachLoading?: boolean;
  chipAnswer?: boolean;
};

export type QaTurn = {
  /** 이 대화 세션 안에서 몇 번째 질문인가(0부터). 기록의 순서이자 중복 판정 기준. */
  turnIndex: number;
  question: string;
  /** 칩을 눌러 답한 턴 — 버블이 그려지지 않으므로 원문만으로는 구분되지 않는다. */
  chipAnswer: boolean;
  answer: string;
  answerKind: QaAnswerKind;
  /** 아직 응답이 진행 중(로딩 자리표시자가 남아 있음). 기록하지 않는다. */
  pending: boolean;
};

export type QaAnswerKind =
  | "error"          // 오류 안내
  | "clarification"  // 되묻기
  | "strategy"       // 전략 요약(파싱 결과)
  | "coach"          // 코치 산문
  | "info"           // 일반 투자 지식·전환 안내
  | "text"           // 그 밖의 산문
  | "none";          // 답변 없음(아직 응답 전)

// 한 턴이 여러 블록으로 답할 때(요약 카드 + 되묻기 등) 대표 종류를 고르는 순서.
// 앞에 있을수록 우선한다 — 사용자가 지금 응답해야 하는 것이 앞에 온다.
const KIND_PRIORITY: QaAnswerKind[] = [
  "error",
  "clarification",
  "strategy",
  "coach",
  "info",
  "text",
];

// 전략 요약은 카드로 그려져 텍스트가 없다. 기록에서 빈칸으로 보이지 않도록 자리를 남긴다.
const STRATEGY_CARD_MARKER = "[전략 요약 카드]";

/** 어시스턴트 메시지 하나가 화면에 띄운 텍스트. 그린 순서대로 잇는다. */
export function answerTextOf(message: QaChatMessage): string {
  const parts: string[] = [];
  if (message.content?.trim()) parts.push(message.content.trim());
  for (const notice of message.notices ?? []) {
    if (notice?.trim()) parts.push(`안내: ${notice.trim()}`);
  }
  if (message.parsed) parts.push(STRATEGY_CARD_MARKER);
  if (message.coachText?.trim()) parts.push(message.coachText.trim());
  if (message.infoText?.trim()) parts.push(message.infoText.trim());
  if (message.clarification?.trim()) parts.push(message.clarification.trim());
  const suggestions = [
    ...(message.clarificationSuggestions ?? []),
    ...(message.infoSuggestions ?? []),
  ].filter((s) => s?.trim());
  if (suggestions.length > 0) parts.push(`선택지: ${suggestions.join(" / ")}`);
  if (message.error?.trim()) parts.push(`오류: ${message.error.trim()}`);
  return parts.join("\n");
}

/** 어시스턴트 메시지 하나의 종류. 채워진 필드만 보고 정한다. */
export function answerKindOf(message: QaChatMessage): QaAnswerKind {
  if (message.error?.trim()) return "error";
  if (message.clarification?.trim()) return "clarification";
  if (message.parsed) return "strategy";
  if (message.coachText?.trim()) return "coach";
  if (message.infoText?.trim()) return "info";
  if (message.content?.trim()) return "text";
  return "none";
}

/**
 * 화면 메시지 목록을 턴 단위로 묶는다 — 사용자 발화 하나 + 그 다음 사용자 발화 전까지의
 * 어시스턴트 응답 전부가 한 턴이다.
 *
 * 사용자 발화 없이 시작된 어시스턴트 메시지(첫 진입 안내 등)는 질문이 없으므로 버린다.
 */
export function collectQaTurns(messages: QaChatMessage[]): QaTurn[] {
  const turns: QaTurn[] = [];
  let question: string | null = null;
  let chipAnswer = false;
  let parts: string[] = [];
  let kinds: QaAnswerKind[] = [];
  let pending = false;

  const close = () => {
    if (question === null) return;
    turns.push({
      turnIndex: turns.length,
      question,
      chipAnswer,
      answer: parts.join("\n\n"),
      answerKind: KIND_PRIORITY.find((k) => kinds.includes(k)) ?? "none",
      pending,
    });
  };

  for (const message of messages) {
    if (message.role === "user") {
      close();
      question = (message.content ?? "").trim();
      chipAnswer = Boolean(message.chipAnswer);
      parts = [];
      kinds = [];
      pending = false;
      continue;
    }
    if (question === null) continue;
    if (message.isLoading || message.coachLoading) {
      pending = true;
      continue;
    }
    const text = answerTextOf(message);
    if (text) parts.push(text);
    const kind = answerKindOf(message);
    if (kind !== "none") kinds.push(kind);
  }
  close();

  return turns;
}

/**
 * 아직 기록하지 않은 턴 중 **연속으로** 기록 가능한 것만 고른다.
 *
 * 응답이 끝나지 않은 턴에서 멈춘다 — 건너뛰고 뒤엣것을 먼저 기록하면 그 턴은 영영
 * 기록되지 않는다(진행 카운터가 넘어가 버린다).
 */
export function selectLoggableQaTurns(
  messages: QaChatMessage[],
  loggedTurnCount: number,
): QaTurn[] {
  const turns = collectQaTurns(messages);
  const loggable: QaTurn[] = [];
  for (let i = loggedTurnCount; i < turns.length; i++) {
    const turn = turns[i];
    if (turn.pending || !turn.question || !turn.answer) break;
    loggable.push(turn);
  }
  return loggable;
}

export type QaLogPayload = {
  sessionId: string;
  turnIndex: number;
  question: string;
  answer: string;
  answerKind: QaAnswerKind;
  chipAnswer: boolean;
  latencyMs: number | null;
};

/** 기록 전송은 대화를 막지 않는다 — 실패해도 조용히 버린다. */
export function sendQaLog(payload: QaLogPayload): void {
  try {
    void fetch("/api/chat-log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "same-origin",
      keepalive: true,
    }).catch(() => {});
  } catch {
    // 기록 실패가 대화를 깨뜨리지 않는다.
  }
}

export function newQaSessionId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `qa-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }
}
