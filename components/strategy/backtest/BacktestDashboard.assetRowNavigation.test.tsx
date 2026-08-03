// @ts-nocheck
/**
 * BacktestDashboard 종목 분석 탭 — 종목 행 클릭 시 주문 페이지 이동 회귀 테스트.
 *
 * 종목별 매매 분석 표의 행을 클릭하면 /stock-order?symbol={code}&name={인코딩된 종목명}
 * 페이지로 이동한다(QuickSearchModal·가상계좌 상세와 동일한 링크 관례).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => <div /> }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

import BacktestDashboard from "./BacktestDashboard";

const baseResult = {
  executionId: "exec-1",
  strategyId: "strat-1",
  cacheKey: "ck-1",
  symbols: ["005930"],
  totalReturn: 0,
  cagr: 0,
  buyAndHoldReturn: 0,
  maxDrawdown: 0,
  winRate: 0,
  profitFactor: 0,
  sharpe: 0,
  sortino: 0,
  trades: 4,
  finalEquity: 10000000,
  initialCapital: 10000000,
  equity: [],
  dates: ["2022-01-01", "2026-07-08"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
  perAssetStats: {
    "005930": { profit: 193850, totalReturn: 5.16, trades: 4 },
  },
} as any;

describe("BacktestDashboard 종목 분석 행 클릭 이동", () => {
  beforeEach(() => {
    cleanup();
    pushMock.mockClear();
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (typeof url === "string" && url.includes("/api/stocks/names")) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ "005930": { name: "삼성전자", sector: "전기전자" } }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      })
    );
  });

  it("종목 행을 클릭하면 /stock-order 주문 페이지로 심볼·종목명과 함께 이동한다", async () => {
    render(
      <BacktestDashboard
        result={baseResult}
        onRestart={() => {}}
        disableHistorySave
      />
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "종목 분석" }));

    const nameCell = await screen.findByText("삼성전자");
    await user.click(nameCell.closest("tr")!);

    expect(pushMock).toHaveBeenCalledWith(
      "/stock-order?symbol=005930&name=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90"
    );
  });
});
