import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QuantileGroupsSection from "./QuantileGroupsSection";
import type { QuantileGroupsResult } from "@/types/strategy";

function makeGroup(group: number, cagr: number): QuantileGroupsResult["groups"][number] {
  return {
    group,
    label: `${group}그룹 (PER(주가수익비율) 낮은 순 ${(group - 1) * 10}~${group * 10}%)`,
    pctRange: [(group - 1) * 10, group * 10],
    totalReturn: cagr * 2,
    cagr,
    maxDrawdown: -12.34,
    sharpe: 0.87,
    winRate: 55.5,
    trades: 42,
    finalEquity: 12_345_678,
    equity: [10_000_000, 11_000_000, 12_345_678],
    dates: ["2020-01-02", "2022-01-03", "2024-01-02"],
  };
}

const data: QuantileGroupsResult = {
  groups: [makeGroup(1, 15.2), makeGroup(2, 4.1), makeGroup(3, -3.7)],
  metricLabel: "PER(주가수익비율)",
  orderLabel: "PER(주가수익비율) 낮은 순",
  groupCount: 3,
  mainGroup: 1,
};

describe("QuantileGroupsSection", () => {
  it("그룹별 막대와 테이블 행을 렌더링한다", () => {
    render(<QuantileGroupsSection data={data} />);

    expect(screen.getByText("분위 그룹 비교")).toBeTruthy();
    // 막대 — 그룹 수만큼
    expect(screen.getByTestId("quantile-bar-1")).toBeTruthy();
    expect(screen.getByTestId("quantile-bar-3")).toBeTruthy();
    // 테이블 — 그룹 수 + 헤더
    const table = screen.getByTestId("quantile-groups-table");
    expect(table.querySelectorAll("tbody tr").length).toBe(3);
    // 메인 그룹 배지
    expect(screen.getAllByText("메인").length).toBeGreaterThanOrEqual(1);
  });

  it("지표 토글로 총 수익률 기준 라벨이 갱신된다", async () => {
    render(<QuantileGroupsSection data={data} />);

    // 기본은 CAGR 라벨(+15.2%)
    expect(screen.getByText("+15.2%")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "총 수익률" }));
    // totalReturn = cagr*2 → +30.4%
    expect(screen.getByText("+30.4%")).toBeTruthy();
  });

  it("그룹이 없으면 아무것도 렌더링하지 않는다", () => {
    const { container } = render(
      <QuantileGroupsSection data={{ ...data, groups: [] }} />
    );
    expect(container.firstChild).toBeNull();
  });
});
