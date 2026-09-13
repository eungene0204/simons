// @ts-nocheck
/**
 * 롤링 수익률 표 — 백테스트 결과 페이지 '롤링 수익률' 탭.
 *
 * 라인 차트 하나 대신 투자 기간(1개월·3개월·6개월·1년·2년·3년)별로 롤링 구간의 수익률 분포와
 * 구간 안 MDD를 표로 보인다(2026-08-18 사용자 지시).
 * - 창을 담을 수 있는 투자 기간만 행으로 나온다.
 * - 최저·최고 수익률과 최악 MDD에는 해당 구간(시작~종료)이 함께 붙는다.
 * - 행이 없으면 기간 부족 안내만 보인다.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RollingReturnTable from "@/components/strategy/backtest/RollingReturnTable";
import {
  ROLLING_WINDOW_OPTIONS,
  rollingWindowLabel,
} from "@/components/strategy/backtest/rollingReturnLabels";
import { buildRollingWindowStatsTable } from "@/components/strategy/backtest/rollingReturns";

// 2023-01-02 ~ 2024-06-02 매월 초 자산곡선(18개월) — 1·3·6·12개월 창은 담기고 2년 이상은 안 담긴다.
const DATES: string[] = [];
const EQUITY: number[] = [];
{
  let eq = 100;
  for (let i = 0; i < 18; i++) {
    const y = 2023 + Math.floor(i / 12);
    const m = (i % 12) + 1;
    DATES.push(`${y}-${String(m).padStart(2, "0")}-02`);
    eq *= i % 5 === 3 ? 0.9 : 1.03;
    EQUITY.push(eq);
  }
}

describe("rollingWindowLabel", () => {
  it("12개월 배수는 연 라벨, 나머지는 개월 라벨", () => {
    expect(rollingWindowLabel(1)).toBe("1개월");
    expect(rollingWindowLabel(6)).toBe("6개월");
    expect(rollingWindowLabel(12)).toBe("1년");
    expect(rollingWindowLabel(24)).toBe("2년");
    expect(rollingWindowLabel(36)).toBe("3년");
  });

  it("지원 투자 기간은 3년까지(5년 없음)", () => {
    expect(ROLLING_WINDOW_OPTIONS).toEqual([1, 3, 6, 12, 24, 36]);
  });
});

describe("RollingReturnTable", () => {
  it("창을 담을 수 있는 투자 기간만 행으로 그린다", () => {
    const rows = buildRollingWindowStatsTable(DATES, EQUITY, ROLLING_WINDOW_OPTIONS);
    render(<RollingReturnTable rows={rows} />);
    expect(screen.getByTestId("rolling-return-table")).toBeTruthy();
    expect(screen.getByTestId("rolling-row-1")).toBeTruthy();
    expect(screen.getByTestId("rolling-row-12")).toBeTruthy();
    expect(screen.queryByTestId("rolling-row-24")).toBeNull();
    expect(screen.queryByTestId("rolling-row-36")).toBeNull();
  });

  it("최저·최고 수익률과 최악 MDD에 해당 구간 날짜를 함께 표시한다", () => {
    const rows = buildRollingWindowStatsTable(DATES, EQUITY, [1]);
    render(<RollingReturnTable rows={rows} />);
    const row = screen.getByTestId("rolling-row-1");
    const r = rows[0];
    expect(row.textContent).toContain(`${r.minReturnWindow.start} ~ ${r.minReturnWindow.end}`);
    expect(row.textContent).toContain(`${r.maxReturnWindow.start} ~ ${r.maxReturnWindow.end}`);
    expect(row.textContent).toContain(`${r.worstMddWindow.start} ~ ${r.worstMddWindow.end}`);
    expect(row.textContent).toContain(`${r.worstMdd.toFixed(2)}%`);
    expect(row.textContent).toContain(String(r.count));
  });

  it("chart 슬롯을 표 위에 그린다(선택 기간의 전체 구간 라인 차트 자리)", () => {
    const rows = buildRollingWindowStatsTable(DATES, EQUITY, [1]);
    render(<RollingReturnTable rows={rows} chart={<div data-testid="rolling-line-chart" />} />);
    const section = screen.getByTestId("rolling-return-section");
    const chart = screen.getByTestId("rolling-line-chart");
    const table = screen.getByTestId("rolling-return-table");
    expect(section.contains(chart)).toBe(true);
    // 차트가 표보다 먼저(위에) 온다
    expect(chart.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("1년을 넘는 행에는 '연환산' 표기가 붙고 1년 이하 행에는 없다", () => {
    // 2021-01-02 ~ 2024-01-02 매월 초(37개월) — 2년·3년 창까지 담긴다
    const dates: string[] = [];
    const equity: number[] = [];
    for (let i = 0; i < 37; i++) {
      const y = 2021 + Math.floor(i / 12);
      const m = (i % 12) + 1;
      dates.push(`${y}-${String(m).padStart(2, "0")}-02`);
      equity.push(100 * Math.pow(1.005, i));
    }
    const rows = buildRollingWindowStatsTable(dates, equity, ROLLING_WINDOW_OPTIONS);
    render(<RollingReturnTable rows={rows} />);
    expect(screen.getByTestId("rolling-row-12").textContent).not.toContain("연환산");
    expect(screen.getByTestId("rolling-row-24").textContent).toContain("연환산");
    expect(screen.getByTestId("rolling-row-36").textContent).toContain("연환산");
    expect(screen.getByText(/1년을 넘는 투자 기간의 수익률은 연환산/)).toBeTruthy();
  });

  it("벤치마크가 있으면 초과 비율·벤치마크 평균을, 없으면 '—'와 안내를 보인다", () => {
    const benchmark = EQUITY.map((_, i) => 100 * Math.pow(1.01, i));
    const withBench = buildRollingWindowStatsTable(DATES, EQUITY, [1], benchmark);
    const { unmount } = render(<RollingReturnTable rows={withBench} benchmarkLabel="KODEX 200" />);
    const cell = screen.getByTestId("rolling-benchmark-1");
    expect(cell.textContent).toContain(`${withBench[0].beatBenchmarkRatio!.toFixed(2)}%`);
    expect(cell.textContent).toContain("벤치마크 평균");
    expect(screen.getByText(/벤치마크\(KODEX 200\) 수익률보다 높았던/)).toBeTruthy();
    unmount();

    const noBench = buildRollingWindowStatsTable(DATES, EQUITY, [1]);
    render(<RollingReturnTable rows={noBench} />);
    expect(screen.getByTestId("rolling-benchmark-1").textContent).toBe("—");
    expect(screen.getByText(/벤치마크 자산곡선이 없어/)).toBeTruthy();
  });

  it("하위 5%·상위 5% 열을 표시한다", () => {
    const rows = buildRollingWindowStatsTable(DATES, EQUITY, [1]);
    render(<RollingReturnTable rows={rows} />);
    expect(screen.getByText("하위 5%")).toBeTruthy();
    expect(screen.getByText("상위 5%")).toBeTruthy();
    const row = screen.getByTestId("rolling-row-1");
    expect(row.textContent).toContain(`${rows[0].p5Return.toFixed(2)}%`);
  });

  it("행이 없으면 기간 부족 안내만 보인다", () => {
    render(<RollingReturnTable rows={[]} />);
    expect(screen.queryByTestId("rolling-return-table")).toBeNull();
    expect(screen.getByText(/롤링 수익률을 계산할 수 없습니다/)).toBeTruthy();
  });
});
