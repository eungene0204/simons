import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { BacktestResult } from "@/types/strategy";
import BacktestStatsSummary from "./BacktestStatsSummary";

const base = {
  totalReturn: 22.89,
  cagr: 3.5,
  buyAndHoldReturn: 52.07,
  benchmarkLabel: "KODEX 코스피 (226490)",
  benchmarkPartial: false,
  finalEquity: 12_289_115,
  initialCapital: 10_000_000,
  volatility: 18.71,
  sharpe: 0.28,
  sortino: 0.41,
  calmar: 0.1,
  maxDrawdown: -33.39,
  kelly: 5.99,
  trades: 141,
  winRate: 38.3,
  profitFactor: 1.12,
  avgProfit: 16.68,
  avgLoss: 8.73,
  maxConsecutiveWins: 4,
  maxConsecutiveLosses: 8,
} as unknown as BacktestResult;

const valueFor = (label: string) =>
  screen.getByText(label).parentElement?.querySelector("span:last-child")?.textContent;

describe("BacktestStatsSummary 지표 표기", () => {
  it("초과 수익(α)은 연율값이 아니라 총수익률에서 벤치마크를 뺀다", () => {
    // 회귀: `cagr - buyAndHoldReturn`이라 6년 백테스트에서 3.5 − 52.07 = −48.57%p가
    // 나왔다. 올바른 값은 22.89 − 52.07 = −29.18%p.
    render(<BacktestStatsSummary result={base} />);
    expect(valueFor("초과 수익 (α)")).toBe("-29.18%");
  });

  it("벤치마크가 구간 일부만 덮으면 초과 수익을 내지 않는다", () => {
    render(<BacktestStatsSummary result={{ ...base, benchmarkPartial: true }} />);
    expect(valueFor("초과 수익 (α)")).toBe("—");
  });

  it("벤치마크 행은 '바이앤홀드'가 아니라 실제 비교 지수명을 쓴다", () => {
    // 값은 지수 ETF 수익률이지 전략 종목의 매수 후 보유가 아니다
    render(<BacktestStatsSummary result={base} />);
    expect(screen.getByText("KODEX 코스피")).toBeInTheDocument();
    expect(screen.queryByText("바이앤홀드")).not.toBeInTheDocument();
  });

  it("손실 거래가 0건이면 손익비를 0이 아니라 ∞로 표시한다", () => {
    render(<BacktestStatsSummary result={{ ...base, profitFactor: null }} />);
    expect(valueFor("손익비")).toBe("∞");
  });

  it("켈리를 못 구하면 +0.00%가 아니라 —로 표시한다", () => {
    render(<BacktestStatsSummary result={{ ...base, kelly: null }} />);
    expect(valueFor("켈리 기준")).toBe("—");
  });
});
