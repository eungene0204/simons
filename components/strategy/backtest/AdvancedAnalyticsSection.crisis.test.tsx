import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CrisisPeriodResult } from "@/types/strategy";
import { CrisisPeriodsCard } from "./AdvancedAnalyticsSection";

const row = (over: Partial<CrisisPeriodResult>): CrisisPeriodResult => ({
  id: "covid_2020", start: "2020-01-22", end: "2020-03-19", coveredStart: "2020-01-22", coveredEnd: "2020-03-19",
  partial: false, tradingDays: 40, strategyReturn: -12.5, strategyMaxDrawdown: -20.1,
  benchmarkReturn: -35.7, benchmarkMaxDrawdown: -35.7, recoveryDays: 37, recovered: true, ...over,
});

describe("CrisisPeriodsCard", () => {
  it("구간 이름·값·회복 상태를 표로 보여 준다", () => {
    render(
      <CrisisPeriodsCard
        english={false}
        benchmarkLabel="KOSPI"
        rows={[
          row({}),
          row({ id: "gfc_2008", coveredStart: "2008-01-02", partial: true, recovered: false, recoveryDays: null }),
          row({ id: "tariff_2025", recovered: null, recoveryDays: null }),
        ]}
      />,
    );
    const card = screen.getByTestId("analytics-crisis-periods");
    expect(within(card).getByText("2020 코로나19 폭락")).toBeTruthy();
    expect(within(card).getByText("KOSPI 수익률")).toBeTruthy();
    expect(within(card).getAllByText("-12.50%").length).toBe(3);
    expect(within(card).getByText("37거래일")).toBeTruthy();
    expect(within(card).getByText("미회복")).toBeTruthy();
    expect(within(card).getByText("일부 기간")).toBeTruthy();
  });

  it("겹치는 구간이 없으면 안내 문구를 보여 준다", () => {
    render(<CrisisPeriodsCard english={false} rows={[]} />);
    expect(screen.getByText("백테스트 기간이 정해 둔 위기 구간과 겹치지 않습니다.")).toBeTruthy();
  });

  it("영어 화면은 영어 구간 이름을 쓴다", () => {
    render(<CrisisPeriodsCard english rows={[row({ recoveryDays: 0 })]} />);
    expect(screen.getByText("2020 COVID-19 crash")).toBeTruthy();
    expect(screen.getByText("Within period")).toBeTruthy();
  });
});
