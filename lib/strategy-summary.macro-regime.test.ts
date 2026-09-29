import { describe, expect, it } from "vitest";
import { buildStrategySummaryFromRequest, formatMacroFilterLabels, type MacroFilterSummary } from "./strategy-summary";

const filters: MacroFilterSummary[] = [
  { series: "usdkrw", role: "entry", mode: "ma", operator: "crosses_above", period: 60 },
  { series: "usdkrw", role: "entry", mode: "change", operator: ">", period: 20, value: 0 },
  { series: "usdkrw", role: "exit", mode: "ma", operator: "<", period: 60 },
  { series: "usdkrw", role: "exit", mode: "change", operator: "crosses_below", period: 20, value: 0 },
];

describe("macro regime summary", () => {
  it("shows crossing, AND entry and OR liquidation without asking for exposure", () => {
    const labels = formatMacroFilterLabels(filters);
    expect(labels[0]).toContain("60일 이동평균 상향 돌파");
    expect(labels[0]).toContain("20일 변화율 0% 초과");
    expect(labels[0]).toContain("모두 충족");
    expect(labels[1]).toContain("20일 변화율 0% 하향 돌파");
    expect(labels[1]).toContain("하나라도 충족 시 신규 매수 중단·전량 청산");
    expect(labels.join(" ")).not.toContain("값 미정");
    expect(labels[2]).toContain("청산 후 진입 조건 재충족");
    const summary = buildStrategySummaryFromRequest({ universe_id: "kospi", risk: { macro_filters: filters } });
    expect(summary?.riskText).toContain(labels[0]);
    expect(summary?.riskText).toContain(labels[1]);
  });

  it("preserves legacy reduction and distinguishes a missing value from zero", () => {
    expect(formatMacroFilterLabels([{ series: "vix", mode: "level", operator: ">", value: 30, exposure_pct: 0 }]))
      .toEqual(["VIX(변동성 지수) 30 초과이면 투자 비중 0%"]);
    expect(formatMacroFilterLabels([{ ...filters[1], value: null }])[0]).toContain("값 미정");
  });
});
