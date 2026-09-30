import { describe, expect, it } from "vitest";
import { parseStrategySnapshot, strategySnapshotJson } from "./qaLogStrategy";

describe("qaLogStrategy", () => {
  it("카드 항목과 해석 원본을 JSON으로 만들고 되읽는다", () => {
    const json = strategySnapshotJson({ summaryItems: [{ label: "매수", value: "RSI" }], parsed: { a: 1 } });
    expect(parseStrategySnapshot(json)).toEqual({
      summaryItems: [{ label: "매수", value: "RSI" }],
      parsed: { a: 1 },
    });
  });

  it("너무 크면 원본을 빼고 카드 항목만 남긴다 — JSON을 중간에서 자르지 않는다", () => {
    const json = strategySnapshotJson({
      summaryItems: [{ label: "매수", value: "RSI" }],
      parsed: { big: "x".repeat(300_000) },
    });
    expect(parseStrategySnapshot(json)).toEqual({
      summaryItems: [{ label: "매수", value: "RSI" }],
      parsed: null,
      parsedOmitted: true,
    });
  });

  it("객체가 아니면 기록하지 않고, 깨진 JSON은 null로 읽는다", () => {
    expect(strategySnapshotJson(null)).toBeNull();
    expect(strategySnapshotJson([1])).toBeNull();
    expect(parseStrategySnapshot("{broken")).toBeNull();
  });
});
