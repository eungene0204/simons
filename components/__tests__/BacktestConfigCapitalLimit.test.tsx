// @ts-nocheck
/**
 * 초기 자본금 상한(100억) 게이트 — 설정 패널.
 *
 * [회귀] 2026-08-02: 100조를 초기 자금으로 넣은 백테스트가 그대로 실행돼, 전 종목이
 * "유동성 기준 미달(거래대금 부족)"로 빠진 빈 결과가 나왔다. 1회 매수 금액이 전일
 * 거래대금의 10%를 넘으면 엔진이 그 종목의 진입을 통째로 지우기 때문이다
 * (backend/engine/loader.py check_liquidity). 대화 레인만 막으면 이 패널의 직접 입력이
 * 그대로 구멍이 되므로 여기서도 같은 상한을 건다.
 *
 * 같은 이유로 백테스트 창(1996~오늘)도 여기서 막는다 — 미래 종료일을 그대로 보내면
 * 엔진은 오늘까지만 돌리는데 화면은 요청한 날짜를 보여줘 둘이 어긋난다.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import BacktestConfig from "@/components/strategy/backtest/BacktestConfig";
import {
  BACKTEST_DATA_FLOOR_DATE,
  MAX_INITIAL_CAPITAL,
  backtestDataCeilingDate,
} from "@/lib/strategy-summary";

const summary = {
  strategyName: "테스트 전략",
  universeName: "KOSPI200",
  universeSettings: {
    marketCapRange: [0, 0], minTradingVolume: 0, selectedSectors: [],
    excludeLossMaking: false, excludeCapitalImpaired: false, excludeAdministrative: false,
    excludePreferred: false, excludeETF_ETN: false, excludeSPAC: false, excludeREITs: false,
    excludeInvestmentWarning: false, excludeDelistingPending: false, excludeForeignStock: false,
    excludePennyStocks: false, excludeNewListings: false, excludeHighVolatility: false,
  },
  universeFiltersCount: 0,
  blockNames: [],
  riskSettings: {
    maxPositions: 12, allocationType: "equal", executionTiming: "next_open",
    rebalancingPeriod: "quarterly",
  },
  riskManagement: {},
};

function renderPanel(initialCapital: number, onRun = vi.fn()) {
  render(
    <BacktestConfig
      onRun={onRun}
      isRunning={false}
      initialConfig={{ period: "3Y", initialCapital, commissionPct: 0.015, slippagePct: 0.05 }}
      summary={summary}
    />,
  );
  return onRun;
}

describe("초기 자본금 상한 게이트", () => {
  it("상한을 넘으면 안내를 띄우고 실행을 막는다", () => {
    const onRun = renderPanel(100_000_000_000_000);

    expect(screen.getByTestId("initial-capital-over-limit").textContent).toContain("100억원");
    expect(screen.getByTestId("initial-capital-over-limit").textContent).toContain("다시 선택");

    const runButton = screen.getByRole("button", { name: /백테스트 시작하기/ });
    expect(runButton).toBeDisabled();
    fireEvent.click(runButton);
    expect(onRun).not.toHaveBeenCalled();
  });

  it("상한 자체(100억)는 실행할 수 있다 — 경계에서 막으면 우리가 알려준 값을 못 고른다", () => {
    const onRun = renderPanel(MAX_INITIAL_CAPITAL);

    expect(screen.queryByTestId("initial-capital-over-limit")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /백테스트 시작하기/ }));
    expect(onRun).toHaveBeenCalledWith(
      expect.objectContaining({ initialCapital: MAX_INITIAL_CAPITAL }),
    );
  });
});

describe("백테스트 기간 데이터 구간 게이트", () => {
  function renderWindow(startDate: string, endDate: string, onRun = vi.fn()) {
    render(
      <BacktestConfig
        onRun={onRun}
        isRunning={false}
        initialConfig={{
          period: "custom", startDate, endDate,
          initialCapital: 10_000_000, commissionPct: 0.015, slippagePct: 0.05,
        }}
        summary={summary}
      />,
    );
    return onRun;
  }

  const today = backtestDataCeilingDate();

  it("미래 종료일은 실행을 막고 안내한다", () => {
    const onRun = renderWindow("2024-01-01", "2035-12-31");
    expect(screen.getByTestId("backtest-window-out-of-range").textContent).toContain(today);
    const runButton = screen.getByRole("button", { name: /백테스트 시작하기/ });
    expect(runButton).toBeDisabled();
    fireEvent.click(runButton);
    expect(onRun).not.toHaveBeenCalled();
  });

  it("데이터 시작 이전으로 끝나는 창도 막는다", () => {
    renderWindow("1980-01-01", "1990-12-31");
    expect(screen.queryByTestId("backtest-window-out-of-range")).not.toBeNull();
  });

  it("구간 안의 창은 그대로 실행된다", () => {
    const onRun = renderWindow("2020-01-01", "2024-12-31");
    expect(screen.queryByTestId("backtest-window-out-of-range")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /백테스트 시작하기/ }));
    expect(onRun).toHaveBeenCalledWith(
      expect.objectContaining({ startDate: "2020-01-01", endDate: "2024-12-31" }),
    );
  });

  it("날짜 입력에 데이터 구간 경계를 건다", () => {
    renderWindow("2020-01-01", "2024-12-31");
    const inputs = screen.getAllByDisplayValue(/^20\d\d-/);
    inputs.forEach((input) => {
      expect(input).toHaveAttribute("min", BACKTEST_DATA_FLOOR_DATE);
      expect(input).toHaveAttribute("max", today);
    });
  });
});
