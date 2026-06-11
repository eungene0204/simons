import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import BacktestStatsSummary from "@/components/strategy/backtest/BacktestStatsSummary";
import type { BacktestResult } from "@/types/strategy";

// 백엔드는 avgLoss를 양수(절댓값)로 내려보낸다. 화면에서는 손실임이 드러나야 한다.
const baseResult = {
  totalReturn: 30,
  cagr: 10,
  buyAndHoldReturn: 5,
  finalEquity: 13_000_000,
  initialCapital: 10_000_000,
  volatility: 12,
  sharpe: 1.2,
  sortino: 1.5,
  calmar: 0.5,
  maxDrawdown: -15,
  kelly: 0.2,
  trades: 71,
  winRate: 33.8,
  profitFactor: 1.5,
  avgProfit: 24.8,
  avgLoss: 5.31, // 양수로 내려옴
  maxConsecutiveWins: 3,
  maxConsecutiveLosses: 4,
} as unknown as BacktestResult;

function valueFor(label: string): HTMLElement {
  const labelEl = screen.getByText(label);
  // 형제 span(value)을 반환
  const value = labelEl.parentElement?.querySelector("span:last-child");
  if (!value) throw new Error(`value not found for ${label}`);
  return value as HTMLElement;
}

describe("BacktestStatsSummary 평균 손익 표시", () => {
  it("평균 손실을 음수(-)로, 하락 색상으로 표시한다", () => {
    render(<BacktestStatsSummary result={baseResult} />);
    const loss = valueFor("평균 손실");
    expect(loss.textContent).toBe("-5.31%");
    expect(loss.className).toContain("text-main-blue");
  });

  it("평균 수익은 양수(+)로, 상승 색상으로 표시한다", () => {
    render(<BacktestStatsSummary result={baseResult} />);
    const profit = valueFor("평균 수익");
    expect(profit.textContent).toBe("+24.80%");
    expect(profit.className).toContain("text-main-red");
  });
});
