import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const { addSeries, setData, fitContent, createChart } = vi.hoisted(() => {
  const setData = vi.fn();
  const fitContent = vi.fn();
  const addSeries = vi.fn(() => ({ setData }));
  const createChart = vi.fn(() => ({
    addSeries,
    timeScale: () => ({ fitContent }),
    applyOptions: vi.fn(),
    remove: vi.fn(),
  }));
  return { addSeries, setData, fitContent, createChart };
});

vi.mock("lightweight-charts", () => ({
  createChart,
  BaselineSeries: "BaselineSeries",
  ColorType: { Solid: "solid" },
  LineType: { Curved: "Curved" },
}));

import PortfolioPerformanceChart from "./PortfolioPerformanceChart";

describe("PortfolioPerformanceChart", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it("keeps every gain and loss point on one continuous zero-based line", () => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(600);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(260);

    render(
      <PortfolioPerformanceChart
        data={[
          { time: "2026-07-03", portfolio: 110 },
          { time: "2026-07-01", portfolio: 100 },
          { time: "2026-07-02", portfolio: 95 },
        ]}
      />
    );

    expect(createChart).toHaveBeenCalledTimes(1);
    expect(addSeries).toHaveBeenCalledTimes(1);
    expect(addSeries).toHaveBeenCalledWith("BaselineSeries", expect.objectContaining({
      baseValue: { type: "price", price: 100 },
      topLineColor: "#ef4444",
      bottomLineColor: "#3b82f6",
      lineType: "Curved",
    }));
    expect(setData).toHaveBeenCalledWith([
      { time: Date.parse("2026-07-01T00:00:00Z") / 1000, value: 100 },
      { time: Date.parse("2026-07-02T00:00:00Z") / 1000, value: 95 },
      { time: Date.parse("2026-07-03T00:00:00Z") / 1000, value: 110 },
    ]);
    expect(fitContent).toHaveBeenCalled();
    expect(screen.getByText("수익률 ≥ 0%")).toBeInTheDocument();
    expect(screen.getByText("수익률 < 0%")).toBeInTheDocument();
  });
});
