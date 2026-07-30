// 되돌리기(설계 스펙 § 19) — 변경 이력과 결정론 복원.
//
// 판정("어디로 되돌리는가")은 백엔드 LLM 레인이 하고, 여기서는 **적용만** 한다.
// 스냅샷을 들고 있는 쪽이 프론트이기 때문이다(대화는 무상태 — 백엔드에 세션이 없다).
//
// 원문을 해석하지 않는다. 이 파일에 되돌리기 표현("아까", "취소")을 찾는 정규식이
// 생기면 그것은 계약 위반이다(자연어 해석 구조 원칙) — 대상 판정은 전적으로 LLM이다.

import type { ParsedSummary } from "@/lib/strategy-summary";

/** 변경 이력 한 항목. parsed는 **그 턴이 끝난 뒤**의 전략이다. */
export type ChangeLogEntry = {
  index: number;
  userText: string;
  parsed: ParsedSummary;
  // 그 시점의 백테스트 요청. 턴 단위 복원은 재컴파일 없이 이것을 그대로 되돌린다.
  backtestReq: any;
  explicitFields: string[];
  // 이 턴이 바꾼 필드 이름(백엔드 산출). 최초 파스는 빈 배열 — 되돌릴 이전 상태가 없다.
  changedFields: string[];
};

/** 백엔드 /strategy/rollback/resolve 판정. */
export type RollbackDecision = {
  action: "turn" | "fields" | "clarify" | "unsupported";
  turn_index?: number | null;
  fields?: string[];
  question?: string | null;
  reason?: string;
};

export type RollbackResult =
  | {
      status: "restored";
      parsed: ParsedSummary;
      // 턴 단위는 그때의 요청을 그대로 쓴다. 필드 단위는 전략이 새 조합이라 재컴파일이
      // 필요하므로 null이다 — 호출자가 /strategy/compile로 다시 만든다.
      backtestReq: any | null;
      explicitFields: string[];
      // 실제로 되돌린 필드(사용자 안내 문구 구성용).
      restoredFields: string[];
      scope: "turn" | "fields";
    }
  | { status: "clarify"; question: string };

const FALLBACK_QUESTION = "어떤 변경을 되돌릴까요? 되돌릴 항목을 말씀해 주세요.";

/** 이력에 다음 턴을 더한다. 같은 index가 다시 오면 덮어쓴다(재시도·교정본). */
export function appendChangeLog(
  log: ChangeLogEntry[],
  entry: ChangeLogEntry,
): ChangeLogEntry[] {
  const without = log.filter((e) => e.index !== entry.index);
  return [...without, entry].sort((a, b) => a.index - b.index);
}

/** 판정 LLM에 보낼 요약 — 전략 값은 싣지 않는다(판정에 필요 없고 오해만 만든다). */
export function toResolvePayload(
  log: ChangeLogEntry[],
): Array<{ index: number; user_text: string; changed_fields: string[] }> {
  return log.map((entry) => ({
    index: entry.index,
    user_text: entry.userText,
    changed_fields: entry.changedFields,
  }));
}

/** 그 변경 **직전** 상태 = 바로 앞 항목이 끝난 시점의 스냅샷. */
function stateBefore(
  log: ChangeLogEntry[],
  turnIndex: number,
): ChangeLogEntry | null {
  const ordered = [...log].sort((a, b) => a.index - b.index);
  const position = ordered.findIndex((e) => e.index === turnIndex);
  if (position <= 0) return null; // 최초 턴 이전은 '전략 없음'이라 되돌릴 대상이 아니다
  return ordered[position - 1];
}

/**
 * 판정대로 복원한다. 되돌릴 수 없으면 되묻기로 강등한다 — 추측으로 전략을 바꾸지 않는다.
 *
 * provenance(explicitFields)도 함께 되돌린다. 남겨두면 되돌아온 질문을 이미 답한 것으로
 * 보고 건너뛴다 — 조건 옵션 되돌리기(previousStepState)가 이미 겪은 함정이다.
 */
export function applyRollback(
  current: ParsedSummary | null,
  currentExplicitFields: string[],
  log: ChangeLogEntry[],
  decision: RollbackDecision,
): RollbackResult {
  if (decision.action === "clarify" || decision.action === "unsupported") {
    return { status: "clarify", question: decision.question || FALLBACK_QUESTION };
  }
  const turnIndex = decision.turn_index;
  if (typeof turnIndex !== "number") {
    return { status: "clarify", question: decision.question || FALLBACK_QUESTION };
  }
  const before = stateBefore(log, turnIndex);
  if (!before) {
    return { status: "clarify", question: FALLBACK_QUESTION };
  }

  if (decision.action === "turn") {
    return {
      status: "restored",
      parsed: before.parsed,
      backtestReq: before.backtestReq ?? null,
      explicitFields: [...before.explicitFields],
      restoredFields: decision.fields ?? [],
      scope: "turn",
    };
  }

  // 필드 단위 — 현재 전략을 유지한 채 지정 항목만 그때 값으로 되돌린다.
  const fields = (decision.fields ?? []).filter((f) => f in before.parsed);
  if (!current || fields.length === 0) {
    return { status: "clarify", question: FALLBACK_QUESTION };
  }
  const parsed = { ...current } as unknown as Record<string, unknown>;
  for (const field of fields) {
    parsed[field] = (before.parsed as unknown as Record<string, unknown>)[field];
  }
  // 되돌린 필드의 provenance만 그때 상태로 맞춘다. 나머지 필드는 이후 턴의 답변이
  // 그대로 유효하므로 건드리지 않는다(턴 단위 복원과 다른 점).
  const restoredSet = new Set(fields);
  const explicitFields = currentExplicitFields.filter(
    (f) => !restoredSet.has(f) || before.explicitFields.includes(f),
  );
  for (const f of before.explicitFields) {
    if (restoredSet.has(f) && !explicitFields.includes(f)) explicitFields.push(f);
  }
  return {
    status: "restored",
    parsed: parsed as unknown as ParsedSummary,
    backtestReq: null,
    explicitFields,
    restoredFields: fields,
    scope: "fields",
  };
}

/**
 * 정정(설계 스펙 § 20)의 되돌림 지점 — 직전 변경 **직전** 상태.
 *
 * 되돌릴 지점을 LLM에 묻지 않는다. 정정은 언제나 방금 한 해석을 겨냥하므로 대상이
 * 결정론으로 정해진다(ROLLBACK과 다른 점 — 거기서는 사용자가 과거 어느 지점이든
 * 가리킬 수 있어 판정이 필요하다). 되돌릴 변경이 없으면 null.
 */
export function stateBeforeLastChange(log: ChangeLogEntry[]): ChangeLogEntry | null {
  const ordered = [...log].sort((a, b) => a.index - b.index);
  const last = [...ordered].reverse().find((e) => e.changedFields.length > 0);
  return last ? stateBefore(ordered, last.index) : null;
}

/** 복원 결과를 사용자에게 알리는 문장. 되돌린 사실만 서술한다(평가·권유 없음). */
export function describeRollback(result: Extract<RollbackResult, { status: "restored" }>): string {
  if (result.scope === "turn") {
    return "직전 변경을 되돌렸습니다. 이어서 바꾸고 싶은 조건을 말씀해 주세요.";
  }
  return "말씀하신 항목만 이전 값으로 되돌렸습니다. 이어서 바꾸고 싶은 조건을 말씀해 주세요.";
}
