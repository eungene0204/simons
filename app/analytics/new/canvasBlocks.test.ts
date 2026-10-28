import { describe, expect, it } from "vitest";

import { applyCanvasBlock, canvasBlocksForStage, EMPTY_PARSED } from "./canvasBlocks";

const choices = (stage: Parameters<typeof canvasBlocksForStage>[0]) =>
  canvasBlocksForStage(stage, null).map((b) => b.choice);

describe("canvasBlocksForStage — 캔버스 블록 = 값이 정해진 되묻기 칩", () => {
  it("매수 칸 칩을 진입 신호·종목 필터·순위 선정으로 가른다", () => {
    expect(choices("entry")).toContain("RSI 30 이하에서 매수");
    expect(choices("entry")).not.toContain("PER 10 이하");
    expect(choices("filters")).toEqual(["PER 10 이하", "ROE 15% 이상"]);
    expect(choices("ranking")).toEqual(["최근 3개월 수익률 상위 매수"]);
  });

  it("'안 함' 거부 칩은 블록이 아니다", () => {
    expect(choices("risk")).toEqual(["손절 -5%", "손절 -10%", "손절 -15%", "익절 10%", "익절 20%", "익절 30%"]);
  });

  it("모든 칸에 블록이 하나 이상 있다", () => {
    for (const stage of ["universe", "filters", "ranking", "entry", "exit", "allocation", "rebalance", "risk"] as const) {
      expect(choices(stage).length, stage).toBeGreaterThan(0);
    }
  });
});

describe("applyCanvasBlock — 올리는 즉시 전략에 포함", () => {
  it("전략이 없어도 빈 전략에 값을 넣는다", () => {
    const result = applyCanvasBlock(null, { stage: "universe", slot: "universe", choice: "코스피" });
    expect(result?.parsed.universe).toEqual(["KOSPI"]);
    expect(result?.parsed.entry_signals).toEqual([]);
  });

  it("목록 칸은 기존 조건 뒤에 잇고 같은 조건은 두 번 넣지 않는다", () => {
    const first = applyCanvasBlock(EMPTY_PARSED, { stage: "entry", slot: "entry", choice: "RSI 30 이하에서 매수" })!.parsed;
    const second = applyCanvasBlock(first, { stage: "entry", slot: "entry", choice: "MACD 골든크로스 매수" })!.parsed;
    expect(second.entry_signals.map((s) => s.indicator)).toEqual(["rsi", "macd"]);
    const again = applyCanvasBlock(second, { stage: "entry", slot: "entry", choice: "RSI 30 이하에서 매수" })!.parsed;
    expect(again.entry_signals.map((s) => s.indicator)).toEqual(["rsi", "macd"]);
  });

  it("값 칸은 바꾼다", () => {
    const a = applyCanvasBlock(EMPTY_PARSED, { stage: "risk", slot: "stop_loss", choice: "손절 -5%" })!.parsed;
    const b = applyCanvasBlock(a, { stage: "risk", slot: "stop_loss", choice: "손절 -10%" })!.parsed;
    expect(b.stop_loss_pct).toBe(10);
  });
});
