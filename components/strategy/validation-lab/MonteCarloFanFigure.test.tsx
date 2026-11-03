import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MonteCarloFanFigure from "./MonteCarloFanFigure";
import type { MonteCarloFan } from "@/components/strategy/backtest/monteCarloFan";

const fan: MonteCarloFan = {
  stepUnit: "day",
  steps: [0, 100, 200],
  p05: [1, 0.8, 0.6],
  p25: [1, 0.9, 0.8],
  p50: [1, 1, 1.1],
  p75: [1, 1.1, 1.3],
  p95: [1, 1.2, 1.5],
  observed: [1, 1.05, 1.2],
  samples: [],
};

function hoverAtWidth(renderedWidth: number) {
  render(<MonteCarloFanFigure number="그림 1" fan={fan} iterations={1000} />);
  const svg = screen.getByRole("img", { name: "몬테카를로 시나리오 자산 경로 백분위 분포" });
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: renderedWidth, height: 100, right: renderedWidth, bottom: 100, x: 0, y: 0, toJSON() {} });
  fireEvent.mouseMove(svg, { clientX: renderedWidth * 0.3 });
  return screen.getByTestId("monte-carlo-fan-tooltip");
}

describe("MonteCarloFanFigure 호버 정보 상자", () => {
  it("그림이 화면에서 2배로 커져도 정보 상자는 같은 크기로 보이도록 배율의 역수로 그린다", () => {
    expect(hoverAtWidth(1520).getAttribute("transform")).toContain("scale(0.5)");
  });

  it("백분위 숫자 대신 상위·하위 5% 경계로 적고, 범례도 가운데 몇 % 범위로 적는다", () => {
    const tip = hoverAtWidth(760);
    expect(tip).toHaveTextContent("상위 5% 경계");
    expect(tip).toHaveTextContent("하위 5% 경계");
    expect(tip).not.toHaveTextContent(/^95%/);
    expect(screen.getByText("가운데 90% 범위")).toBeInTheDocument();
    expect(screen.getByText("가운데 50% 범위")).toBeInTheDocument();
  });
});
