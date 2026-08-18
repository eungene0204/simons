/**
 * 차트 범례 — 그래프에 없는 계열이 범례에 뜨면 안 된다(2026-08-18 사용자 신고).
 * 월별 수익률 막대 차트는 히스토그램 한 종류뿐이라 '나의 전략'·'벤치마크'가 없다.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import BacktestChart from "@/components/strategy/BacktestChart";

const MONTHLY = [
  { time: "2024-01-01", value: -8.69 },
  { time: "2024-02-01", value: 1.85 },
];

describe("BacktestChart 범례", () => {
  it("월별 수익률 차트는 '월간 수익/손실'만 가로로 보이고 자산곡선 계열은 없어야 함", () => {
    const { container } = render(
      <BacktestChart type="monthly_returns" height={220} monthlyData={MONTHLY} />
    );

    expect(screen.getByText("월간 수익/손실")).toBeTruthy();
    expect(screen.queryByText("나의 전략")).toBeNull();
    expect(screen.queryByText("벤치마크")).toBeNull();

    const legend = container.querySelector("div.absolute.top-4.left-4");
    expect(legend?.className).toContain("flex-row");
  });

  it("자산곡선 차트에는 '나의 전략'·'벤치마크' 범례가 남아야 함", () => {
    render(<BacktestChart type="equity" height={220} equityData={[]} />);

    expect(screen.getByText("나의 전략")).toBeTruthy();
    expect(screen.getByText("벤치마크")).toBeTruthy();
  });
});
