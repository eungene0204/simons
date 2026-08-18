// @ts-nocheck
/**
 * 리밸런싱 기간별 결과 비교 탭(FR-BT-064) — 백테스트 결과 페이지 '월별 수익률' 옆 세 번째 탭.
 *
 * 엔진이 백테스트 결과에 동봉한 6주기 재시뮬레이션(result.rebalanceComparison)을 실행 버튼 없이
 * 바로 표로 그린다(2026-08-18 사용자 지시 — 별도 실행·AI 서술 없음).
 * - 현재 설정이 6주기 밖(예: 리밸런싱 없음)이면 메인 결과 지표로 참고 행을 덧붙인다.
 * - 보유 상한이 없는 전략(positionCapAbsent)은 6행이 같을 수 있다는 안내를 붙인다.
 * - 구버전 저장 결과(필드 없음)는 안내만 보인다.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RebalanceComparisonSection from "@/components/strategy/backtest/RebalanceComparisonSection";
import { orderComparisonRows } from "@/components/strategy/backtest/rebalanceComparison";

const PERIODS = [
  { period: "daily", cagr: 8, mdd: -25, sharpe: 0.8, profitFactor: 1.2, trades: 600, turnover: 900, error: null },
  { period: "weekly", cagr: 12, mdd: -22, sharpe: 1.0, profitFactor: 1.4, trades: 300, turnover: 400, error: null },
  { period: "monthly", cagr: 15, mdd: -20, sharpe: 1.3, profitFactor: 1.6, trades: 120, turnover: 200, error: null },
  { period: "quarterly", cagr: 14, mdd: -19, sharpe: 1.25, profitFactor: 1.5, trades: 40, turnover: 80, error: null },
  { period: "semiannual", cagr: 13.5, mdd: -18, sharpe: 1.2, profitFactor: null, trades: 20, turnover: 40, error: null },
  { period: "yearly", cagr: 11, mdd: -17, sharpe: 1.0, profitFactor: 1.3, trades: 10, turnover: 20, error: null },
];

const CURRENT = { cagr: 9.5, maxDrawdown: -21, sharpe: 0.9, profitFactor: 1.1, trades: 77, turnoverRate: 150 };

describe("orderComparisonRows", () => {
  it("6주기를 짧은 → 긴 순으로 늘어놓고 현재 설정이 그 안에 있으면 표시만 한다", () => {
    const shuffled = [PERIODS[3], PERIODS[0], PERIODS[5], PERIODS[1], PERIODS[4], PERIODS[2]];
    const rows = orderComparisonRows({ periods: shuffled, currentPeriod: "monthly" }, CURRENT);
    expect(rows.map((r) => r.period)).toEqual(["daily", "weekly", "monthly", "quarterly", "semiannual", "yearly"]);
    expect(rows.find((r) => r.period === "monthly")?.isCurrent).toBe(true);
    expect(rows.some((r) => r.isReference)).toBe(false);
  });

  it("현재 설정이 6주기 밖(리밸런싱 없음)이면 메인 결과 지표로 참고 행을 덧붙인다", () => {
    const rows = orderComparisonRows({ periods: PERIODS, currentPeriod: "none" }, CURRENT);
    expect(rows).toHaveLength(7);
    const ref = rows[6];
    expect(ref.period).toBe("none");
    expect(ref.isReference).toBe(true);
    expect(ref.cagr).toBe(9.5);
    expect(ref.mdd).toBe(-21);
    expect(ref.trades).toBe(77);
  });
});

describe("RebalanceComparisonSection", () => {
  it("결과에 비교가 없으면(구버전 저장 결과) 안내만 보인다", () => {
    render(<RebalanceComparisonSection data={undefined} current={CURRENT} />);
    expect(screen.getByText(/리밸런싱 기간별 비교가 저장되어 있지 않습니다/)).toBeTruthy();
    expect(screen.queryByTestId("rebalance-comparison-table")).toBeNull();
  });

  it("6주기 표 + 현재 설정 참고 행을 실행 버튼 없이 바로 그린다", () => {
    render(
      <RebalanceComparisonSection
        data={{ periods: PERIODS, currentPeriod: "none", positionCapAbsent: false }}
        current={CURRENT}
      />
    );
    expect(screen.queryByRole("button")).toBeNull();
    for (const period of ["daily", "weekly", "monthly", "quarterly", "semiannual", "yearly", "none"]) {
      expect(screen.getByTestId(`rebalance-row-${period}`)).toBeTruthy();
    }
    expect(screen.getByTestId("rebalance-row-monthly").textContent).toContain("+15.00%");
    const noneRow = screen.getByTestId("rebalance-row-none");
    expect(noneRow.textContent).toContain("현재 설정");
    expect(noneRow.textContent).toContain("+9.50%");
    // 손익비 null(손실 0건)은 ∞ 표기
    expect(screen.getByTestId("rebalance-row-semiannual").textContent).toContain("∞");
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("현재 설정이 6주기 안(monthly)이면 그 행에 배지만 붙고 참고 행은 없다", () => {
    render(<RebalanceComparisonSection data={{ periods: PERIODS, currentPeriod: "monthly" }} current={CURRENT} />);
    expect(screen.getAllByTestId(/rebalance-row-/)).toHaveLength(6);
    expect(screen.getByTestId("rebalance-row-monthly").textContent).toContain("현재 설정");
  });

  it("보유 상한이 없는 전략(positionCapAbsent)은 표를 그대로 두고 안내를 덧붙인다", () => {
    render(<RebalanceComparisonSection data={{ periods: PERIODS, currentPeriod: "none", positionCapAbsent: true }} current={CURRENT} />);
    expect(screen.getByRole("note").textContent).toContain("영향을 주지 않습니다");
    expect(screen.getByTestId("rebalance-comparison-table")).toBeTruthy();
  });

  it("주기 하나가 실패하면 그 행만 실패 문구로 남고 나머지는 그린다", () => {
    const withError = PERIODS.map((p) => (p.period === "weekly" ? { period: "weekly", error: "boom" } : p));
    render(<RebalanceComparisonSection data={{ periods: withError, currentPeriod: "monthly" }} current={CURRENT} />);
    expect(screen.getByTestId("rebalance-row-weekly").textContent).toContain("실행 실패: boom");
    expect(screen.getByTestId("rebalance-row-daily").textContent).toContain("+8.00%");
  });
});
