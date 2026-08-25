// @ts-nocheck
/**
 * US 전략 결과의 달러 표기 (US 레인 Phase 3).
 *
 * 미국 유니버스(universeId=dow30 등)나 미국 티커 지정 종목 백테스트는 엔진이 달러
 * 데이터로 시뮬레이션한다 — 결과 화면이 원화로 표기하면 값 자체가 거짓이 된다.
 * 총 수익 등 금액은 $ 표기, 벤치마크 폴백 라벨은 지수별 대응 ETF(SPY/QQQ/DIA).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/" }));

import BacktestDashboard from "./BacktestDashboard";
import { formatUsd, isUsBacktestResult, isUsUniverseId } from "@/lib/us-symbols";

const usResult = {
  executionId: "exec-us-1",
  strategyId: "strat-us-1",
  symbols: [],
  universeId: "dow30",
  totalReturn: 5.11,
  cagr: 2.6,
  buyAndHoldReturn: 8.2,
  maxDrawdown: -6.1,
  winRate: 52.4,
  profitFactor: 1.31,
  sharpe: 0.8,
  sortino: 1.0,
  trades: 122,
  finalEquity: 105110,
  initialCapital: 100000,
  totalProfit: 5110,
  equity: [100000, 102000, 105110],
  dates: ["2024-01-02", "2024-03-29", "2024-06-28"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

describe("BacktestDashboard 미국 전략 달러 표기", () => {
  beforeEach(() => {
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }))
    );
  });

  it("미국 유니버스 결과의 금액은 달러로, 원화 표기는 없어야 한다", () => {
    render(
      <BacktestDashboard
        result={usResult}
        onRestart={() => {}}
        disableHistorySave
        promptText="다우 30 수익률 상위 5 월간"
      />
    );

    expect(screen.getByText("$5,110")).toBeInTheDocument();
    expect(screen.queryByText(/5,110원/)).not.toBeInTheDocument();
  });
});

describe("us-symbols 유틸", () => {
  it("isUsUniverseId — 엔진 US 유니버스 id와 동일 목록", () => {
    for (const id of ["us", "sp500", "nasdaq100", "nasdaq", "dow30", "us_etf"]) {
      expect(isUsUniverseId(id)).toBe(true);
    }
    expect(isUsUniverseId("kospi")).toBe(false);
    expect(isUsUniverseId(undefined)).toBe(false);
  });

  it("isUsBacktestResult — 유니버스 id 우선, 지정 종목은 거래 심볼 과반", () => {
    expect(isUsBacktestResult({ universeId: "sp500" })).toBe(true);
    expect(isUsBacktestResult({ universeId: null, tradesList: [{ symbol: "AAPL" }, { symbol: "MSFT" }] })).toBe(true);
    expect(isUsBacktestResult({ universeId: null, tradesList: [{ symbol: "005930" }] })).toBe(false);
    expect(isUsBacktestResult({ universeId: "kospi200", tradesList: [] })).toBe(false);
  });

  it("formatUsd — 금액 정수·가격 소수 2자리·음수 -$ 접두", () => {
    expect(formatUsd(5110)).toBe("$5,110");
    expect(formatUsd(-1234.56)).toBe("-$1,235");
    expect(formatUsd(214, { price: true })).toBe("$214.00");
    expect(formatUsd(1234.567, { price: true })).toBe("$1,234.57");
  });
});
