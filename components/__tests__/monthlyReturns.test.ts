import { describe, it, expect } from "vitest";
import { buildMonthlyReturnTableData } from "@/components/strategy/backtest/monthlyReturns";

describe("buildMonthlyReturnTableData", () => {
  it("연도는 최신 순으로 정렬되고 월별 셀은 12칸으로 채워져야 함", () => {
    const rows = buildMonthlyReturnTableData({
      "2023": { "1": 1.5, "12": -2.0 },
      "2024": { "1": 10, "2": -5 },
    });

    expect(rows.map((row) => row.year)).toEqual(["2024", "2023"]);
    expect(rows[0].months).toHaveLength(12);
    expect(rows[0].months[0]).toEqual({ month: 1, value: 10 });
    expect(rows[0].months[1]).toEqual({ month: 2, value: -5 });
    expect(rows[0].months[2]).toEqual({ month: 3, value: null });
  });

  it("연간 누적 수익률은 월별 수익률을 복리로 계산해야 함", () => {
    const rows = buildMonthlyReturnTableData({
      "2024": { "1": 10, "2": -5 },
    });

    expect(rows[0].annualReturn).toBeCloseTo(4.5, 6);
  });

  it("월별 데이터가 없으면 빈 배열을 반환해야 함", () => {
    expect(buildMonthlyReturnTableData({})).toEqual([]);
  });
});
