import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import {
  appendChangeLog,
  applyRollback,
  toResolvePayload,
  type ChangeLogEntry,
} from "./rollback";

const parsed = (over: Partial<ParsedSummary>): ParsedSummary =>
  ({
    description: "전략",
    universe: ["KOSPI"],
    target_symbols: [],
    fundamental_filters: [],
    entry_signals: [],
    exit_signals: [],
    max_positions: 10,
    rebalancing_period: "none",
    ...over,
  }) as unknown as ParsedSummary;

// 1: 최초 파스 → 2: ETF로 교체 → 3: PER 조건 제거
const LOG: ChangeLogEntry[] = [
  {
    index: 1,
    userText: "코스피 저평가 전략",
    parsed: parsed({ universe: ["KOSPI"], fundamental_filters: [{ metric: "per" }] as any }),
    backtestReq: { id: "req1" },
    explicitFields: ["universe"],
    changedFields: [],
  },
  {
    index: 2,
    userText: "ETF로 바꿔줘",
    parsed: parsed({ universe: ["ETF"], fundamental_filters: [{ metric: "per" }] as any }),
    backtestReq: { id: "req2" },
    explicitFields: ["universe", "max_positions"],
    changedFields: ["universe", "max_positions"],
  },
  {
    index: 3,
    userText: "PER 조건 빼줘",
    parsed: parsed({ universe: ["ETF"], fundamental_filters: [] }),
    backtestReq: { id: "req3" },
    explicitFields: ["universe", "max_positions"],
    changedFields: ["fundamental_filters"],
  },
];

describe("appendChangeLog", () => {
  it("같은 index가 다시 오면 덮어쓴다(재시도·후행 교정본)", () => {
    const next = appendChangeLog(LOG, { ...LOG[2], userText: "교정본" });
    expect(next).toHaveLength(3);
    expect(next[2].userText).toBe("교정본");
  });

  it("index 순으로 정렬된 상태를 유지한다", () => {
    const next = appendChangeLog([LOG[2], LOG[0]], LOG[1]);
    expect(next.map((e) => e.index)).toEqual([1, 2, 3]);
  });
});

describe("toResolvePayload", () => {
  it("판정 LLM에 전략 값을 싣지 않는다", () => {
    const payload = toResolvePayload(LOG);
    expect(payload[1]).toEqual({
      index: 2,
      user_text: "ETF로 바꿔줘",
      changed_fields: ["universe", "max_positions"],
    });
    expect(JSON.stringify(payload)).not.toContain("KOSPI");
  });
});

describe("applyRollback — 턴 단위", () => {
  it("그 변경 '직전' 상태로 되돌린다(그 턴의 결과가 아니라)", () => {
    const result = applyRollback(LOG[2].parsed, LOG[2].explicitFields, LOG, {
      action: "turn",
      turn_index: 3,
      fields: ["fundamental_filters"],
    });
    expect(result.status).toBe("restored");
    if (result.status !== "restored") return;
    // 3번 변경 직전 = 2번이 끝난 시점
    expect(result.parsed).toBe(LOG[1].parsed);
    expect(result.backtestReq).toEqual({ id: "req2" });
  });

  it("provenance도 함께 되돌린다 — 남기면 되돌아온 질문을 이미 답한 것으로 본다", () => {
    const result = applyRollback(LOG[2].parsed, ["universe", "max_positions"], LOG, {
      action: "turn",
      turn_index: 2,
    });
    if (result.status !== "restored") throw new Error("복원 실패");
    expect(result.explicitFields).toEqual(["universe"]);
  });

  it("최초 턴은 되돌릴 이전 상태가 없어 되묻기로 강등된다", () => {
    const result = applyRollback(LOG[0].parsed, [], LOG, {
      action: "turn",
      turn_index: 1,
    });
    expect(result.status).toBe("clarify");
  });
});

describe("applyRollback — 필드 단위", () => {
  it("현재 전략을 유지한 채 지정 항목만 그때 값으로 되돌린다", () => {
    const result = applyRollback(LOG[2].parsed, LOG[2].explicitFields, LOG, {
      action: "fields",
      turn_index: 3,
      fields: ["fundamental_filters"],
    });
    if (result.status !== "restored") throw new Error("복원 실패");
    // PER 조건은 되살아나고, 그 뒤 유지된 ETF 유니버스는 그대로다.
    expect(result.parsed.fundamental_filters).toEqual([{ metric: "per" }]);
    expect(result.parsed.universe).toEqual(["ETF"]);
    // 새 조합이라 백테스트 요청은 재컴파일해야 한다.
    expect(result.backtestReq).toBeNull();
    expect(result.restoredFields).toEqual(["fundamental_filters"]);
  });

  it("되돌리지 않은 필드의 provenance는 건드리지 않는다", () => {
    const result = applyRollback(LOG[2].parsed, ["universe", "max_positions"], LOG, {
      action: "fields",
      turn_index: 3,
      fields: ["fundamental_filters"],
    });
    if (result.status !== "restored") throw new Error("복원 실패");
    expect(result.explicitFields).toEqual(["universe", "max_positions"]);
  });

  it("현재 전략이 없으면 되묻는다", () => {
    const result = applyRollback(null, [], LOG, {
      action: "fields",
      turn_index: 3,
      fields: ["fundamental_filters"],
    });
    expect(result.status).toBe("clarify");
  });
});

describe("applyRollback — 안전 강등", () => {
  it.each(["clarify", "unsupported"] as const)("%s 판정은 전략을 바꾸지 않는다", (action) => {
    const result = applyRollback(LOG[2].parsed, [], LOG, {
      action,
      question: "어떤 변경을 되돌릴까요?",
    });
    expect(result).toEqual({ status: "clarify", question: "어떤 변경을 되돌릴까요?" });
  });

  it("이력에 없는 turn_index는 추측으로 보정하지 않는다", () => {
    const result = applyRollback(LOG[2].parsed, [], LOG, {
      action: "turn",
      turn_index: 99,
    });
    expect(result.status).toBe("clarify");
  });

  it("turn_index가 없으면 되묻는다", () => {
    const result = applyRollback(LOG[2].parsed, [], LOG, { action: "turn" });
    expect(result.status).toBe("clarify");
  });
});
