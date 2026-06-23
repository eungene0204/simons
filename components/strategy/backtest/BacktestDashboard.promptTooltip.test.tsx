// @ts-nocheck
/**
 * BacktestDashboard 프롬프트 툴팁 배지 렌더링 회귀 테스트.
 *
 * 버그: 진입 신호 섹션이 entryBlocks가 비면 blockNames(진입+청산 혼합) 폴백으로
 * 떨어져, 매수 기준 없이 익절만 있는 전략에서 청산 배지("익절 30% …")가 진입 신호로
 * 잘못 노출됐다. 사용자의 실제 진입 배지(entryBlocks)만 그대로 보여주도록 수정 → 회귀 고정.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";

// 무거운 자식/애니메이션은 렌더 부담만 주므로 패스스루/널 모킹한다.
vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

import BacktestDashboard from "./BacktestDashboard";

const baseResult = {
  executionId: "exec-1",
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

function renderDashboard(strategySummary: any) {
  return render(
    <BacktestDashboard
      result={baseResult}
      onRestart={() => {}}
      disableHistorySave
      promptText="어떤 종목에 투자 할까?"
      strategySummary={strategySummary}
    />
  );
}

describe("BacktestDashboard 프롬프트 툴팁 진입 신호 배지", () => {
  beforeEach(() => {
    cleanup();
    // 마운트 시 AI 리포트/종목명 등 fetch가 발생 — 빈 응답으로 무력화.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }))
    );
  });

  it("매수 기준 없이 익절만 있으면 진입 신호 섹션을 숨기고 청산 배지를 진입에 누출하지 않는다", () => {
    // 사진 시나리오: entryBlocks 비어 있고 blockNames엔 청산(익절) 라벨만 들어 있음.
    renderDashboard({
      strategyName: "익절 전략",
      universeName: "KOSPI",
      blockNames: ["익절 30% 이상 수익시 매도"],
      entryBlocks: [],
      exitBlocks: ["익절 30% 이상 수익시 매도"],
      positionText: "최대 10종목",
      riskText: "익절 30%",
    });

    fireEvent.click(screen.getByRole("button", { name: "프롬프트" }));

    // 진입 신호 섹션 자체가 없어야 한다(폴백으로 살아나면 안 됨).
    expect(screen.queryByText("진입 신호")).not.toBeInTheDocument();
    // 익절 배지는 청산 신호에 단 한 번만 나타난다.
    expect(screen.getByText("청산 신호")).toBeInTheDocument();
    expect(screen.getAllByText("익절 30% 이상 수익시 매도")).toHaveLength(1);
  });

  it("진입 신호가 있으면 사용자의 entryBlocks를 그대로 표시한다", () => {
    renderDashboard({
      strategyName: "골든크로스 전략",
      universeName: "KOSPI",
      blockNames: ["MA 크로스", "RSI"],
      entryBlocks: ["MA 크로스"],
      exitBlocks: ["RSI"],
      positionText: "최대 10종목",
    });

    fireEvent.click(screen.getByRole("button", { name: "프롬프트" }));

    const entryRow = screen.getByText("진입 신호").parentElement as HTMLElement;
    expect(within(entryRow).getByText("MA 크로스")).toBeInTheDocument();
    expect(within(entryRow).queryByText("RSI")).not.toBeInTheDocument();
  });
});
