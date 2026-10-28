import { describe, expect, it } from "vitest";

import { applyCanvasBlock, EMPTY_PARSED } from "./canvasBlocks";
import compiled from "@/lib/strategy-graph/__fixtures__/compiled.json";
import type { ParsedSummary } from "@/lib/strategy-summary";
import { applyItemEdit, editableItemsForNode, editableItemsForStage } from "./canvasEdits";

const parsed = (() => {
  let p = applyCanvasBlock(EMPTY_PARSED, { stage: "universe", slot: "universe", choice: "코스피" })!.parsed;
  p = applyCanvasBlock(p, { stage: "entry", slot: "entry", choice: "RSI 30 이하에서 매수" })!.parsed;
  p = applyCanvasBlock(p, { stage: "entry", slot: "entry", choice: "골든크로스(5일/20일) 발생 시 매수" })!.parsed;
  p = applyCanvasBlock(p, { stage: "risk", slot: "stop_loss", choice: "손절 -10%" })!.parsed;
  return { ...p, rebalancing_period: "monthly" };
})();

describe("editableItemsForStage — 칸의 항목별 편집 칸", () => {
  it("매수 신호는 값이 있는 칸만 숫자 편집 칸이 된다", () => {
    const items = editableItemsForStage("entry", parsed);
    expect(items.map((i) => i.id)).toEqual(["entry.0", "entry.1"]);
    expect(items[0].fields.map((f) => f.key)).toEqual(["value"]);
    expect(items[1].fields.map((f) => f.key)).toEqual(["short_period", "long_period"]);
  });

  it("정해진 선택지 칸은 칩 목록을 고르게 하고 현재 값을 짚는다", () => {
    const [universe] = editableItemsForStage("universe", parsed);
    const field = universe.fields[0];
    expect(field.kind).toBe("choice");
    if (field.kind !== "choice") return;
    expect(field.value).toBe("코스피");
    expect(field.options.map((o) => o.value)).toContain("코스닥");
  });

  it("전략이 없으면 편집할 항목도 없다", () => {
    expect(editableItemsForStage("risk", null)).toEqual([]);
  });
});

describe("applyItemEdit — 사용자가 넣은 값을 그 필드에 반영", () => {
  it("숫자 칸을 바꾸고 대화 기록에 남길 문구를 준다", () => {
    const edit = applyItemEdit(parsed, "stop_loss", { stop_loss_pct: 7 })!;
    expect(edit.choice.parsed.stop_loss_pct).toBe(7);
    expect(edit.slot).toBe("stop_loss");
    expect(edit.text).toContain("-7%");
  });

  it("매수 신호의 값만 바꾸고 다른 신호는 그대로 둔다", () => {
    const edit = applyItemEdit(parsed, "entry.0", { value: 25 })!;
    expect(edit.choice.parsed.entry_signals[0].value).toBe(25);
    expect(edit.choice.parsed.entry_signals[1]).toEqual(parsed.entry_signals[1]);
  });

  it("선택지 칸은 칩=값 결속 표로 바꾼다", () => {
    expect(applyItemEdit(parsed, "universe", { choice: "코스닥" })!.choice.parsed.universe).toEqual(["KOSDAQ"]);
  });

  it("범위를 벗어나거나 정수가 아닌 기간, 없는 선택지는 거절한다", () => {
    expect(applyItemEdit(parsed, "stop_loss", { stop_loss_pct: 150 })).toBeNull();
    expect(applyItemEdit(parsed, "entry.1", { short_period: 2.5 })).toBeNull();
    expect(applyItemEdit(parsed, "universe", { choice: "없는 시장" })).toBeNull();
  });
});

describe("editableItemsForNode — 더블클릭한 조건만 편집", () => {
  // 엔진 요청: [0] PER 필터, [1] RSI, [2] MACD, [3] EMA60 위(엔진이 덧붙인 조건, 전략 항목 없음)
  const c = (compiled as unknown as Record<string, { parsed: ParsedSummary; request: never }>).entryOrWithFilters;
  const ids = (ref: string | null, stage: Parameters<typeof editableItemsForNode>[0] = "entry") =>
    editableItemsForNode(stage, ref, c.parsed, c.request).map((i) => i.id);

  it("조건 노드는 그 조건에서 온 항목 하나만 낸다", () => {
    expect(ids("snapshot.request.entry.conditions[1]")).toEqual(["entry.0"]);
    expect(ids("snapshot.request.entry.conditions[0]", "filters")).toEqual(["fundamental.0"]);
    expect(ids("snapshot.request.exit.conditions[0]", "exit")).toEqual(["exit.0"]);
  });

  it("전략 항목이 없는 엔진 조건은 편집 칸이 없다", () => {
    expect(ids("snapshot.request.entry.conditions[3]", "filters")).toEqual([]);
  });

  it("설정 노드는 이름이 같은 항목으로, 칸 노드(경로 없음)는 칸 전체로", () => {
    const withRisk = { ...c.parsed, stop_loss_pct: 10, take_profit_pct: 20 };
    expect(editableItemsForNode("risk", "snapshot.request.risk.stop_loss_pct", withRisk, c.request).map((i) => i.id)).toEqual(["stop_loss"]);
    expect(editableItemsForNode("risk", null, withRisk, c.request).map((i) => i.id)).toEqual(["stop_loss", "take_profit"]);
  });
});
