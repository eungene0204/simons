// @ts-nocheck
/**
 * 백테스트를 저장하면 기록 목록 캐시가 버려져야 한다(FR-BT-031c).
 *
 * 캐시가 남아 있으면 기록 탭이 "방금 실행한 백테스트가 빠진 옛 목록"을 즉시 그린다 —
 * 캐시로 로딩을 건너뛰는 이득은 이 무효화가 있어야만 안전하다.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/react";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import BacktestDashboard from "./BacktestDashboard";
import {
  getCachedBacktestHistory,
  invalidateBacktestHistoryCache,
  setCachedBacktestHistory,
} from "@/lib/backtest-history-cache";

const baseResult = {
  executionId: "exec-cache-1",
  strategyId: "strat-1",
  symbols: [],
  totalReturn: 0,
  cagr: 0,
  buyAndHoldReturn: 0,
  maxDrawdown: 0,
  winRate: 0,
  profitFactor: 0,
  sharpe: 0,
  sortino: 0,
  trades: 0,
  finalEquity: 10000000,
  initialCapital: 10000000,
  equity: [],
  dates: [],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

const strategySummary = {
  strategyName: "pbr, roe 전략",
  universeName: "KOSPI",
  entryLogic: "AND",
  exitLogic: "AND",
  entryBlocks: ["PBR <= 1"],
  exitBlocks: ["익절 20% 이상 수익시 매도"],
  blockNames: ["PBR <= 1", "익절 20% 이상 수익시 매도"],
  positionText: "최대 5종목",
  riskText: "손절 10%, 익절 20%",
};

describe("BacktestDashboard 자동 저장 — 기록 목록 캐시 무효화", () => {
  beforeEach(() => {
    cleanup();
    invalidateBacktestHistoryCache();
  });

  afterEach(() => {
    invalidateBacktestHistoryCache();
    vi.unstubAllGlobals();
  });

  it("결과 자동 저장 시 옛 기록 목록 캐시를 버린다", async () => {
    const historyPosts: any[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: any) => {
        if (typeof url === "string" && url.includes("/api/backtest/history")) {
          historyPosts.push(init?.body);
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      })
    );

    setCachedBacktestHistory([{ id: "old-1" } as any]);

    render(
      <BacktestDashboard
        result={baseResult}
        onRestart={() => {}}
        promptText="pbr, roe 전략"
        backtestDsl={{ universe: { id: "KOSPI" }, entry: {}, exit: {} }}
        strategySummary={strategySummary}
      />
    );

    await waitFor(() => expect(historyPosts.length).toBeGreaterThan(0));
    expect(getCachedBacktestHistory()).toBeNull();
  });
});
