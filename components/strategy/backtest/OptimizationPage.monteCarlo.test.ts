// @ts-nocheck
import { describe, expect, it } from "vitest";

import {
  buildMonteCarloHistogram,
  extractTradeReturns,
  runMonteCarloSimulation,
} from "./OptimizationPage";

function buildResult(length: number) {
  let value = 10_000_000;
  const equity = Array.from({ length }, (_, index) => {
    value *= index % 7 === 0 ? 0.99 : 1.004;
    return value;
  });
  return { equity, initialCapital: 10_000_000 };
}

function buildTrades(count: number) {
  const tradesList = [];
  for (let i = 0; i < count; i += 1) {
    const buyPrice = 10_000 + i * 10;
    const sellPrice = buyPrice * (i % 3 === 0 ? 0.96 : 1.05);
    const day = String((i % 27) + 1).padStart(2, "0");
    tradesList.push({ date: `2024-01-${day}`, symbol: `SYM${i % 5}`, type: "buy", price: buyPrice, quantity: 10, reason: "진입" });
    tradesList.push({ date: `2024-02-${day}`, symbol: `SYM${i % 5}`, type: "sell", price: sellPrice, quantity: 10, reason: "청산" });
  }
  return tradesList;
}

const settings = { iterations: 200, blockSize: 21, seed: 42, mode: "returns" };

describe("runMonteCarloSimulation", () => {
  it("equity 데이터가 부족하면 에러를 반환한다", async () => {
    const result = await runMonteCarloSimulation(buildResult(30), settings);
    expect(result.status).toBe("error");
    expect(result.message).toContain("최소");
  });

  it("분포 요약에 min/max·사분위·표준편차를 모두 제공한다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), settings);
    expect(result.status).toBe("ok");

    for (const summary of [result.cagr, result.sharpe, result.mdd]) {
      expect(summary.min).toBeLessThanOrEqual(summary.p05);
      expect(summary.p05).toBeLessThanOrEqual(summary.p25);
      expect(summary.p25).toBeLessThanOrEqual(summary.median);
      expect(summary.median).toBeLessThanOrEqual(summary.p75);
      expect(summary.p75).toBeLessThanOrEqual(summary.p95);
      expect(summary.p95).toBeLessThanOrEqual(summary.max);
      expect(summary.std).toBeGreaterThanOrEqual(0);
    }
    // MDD는 항상 0 이상
    expect(result.mdd.min).toBeGreaterThanOrEqual(0);
    expect(result.probPositiveCagr).toBeGreaterThanOrEqual(0);
    expect(result.probPositiveCagr).toBeLessThanOrEqual(1);
    expect(result.probMddOver30pct).toBeGreaterThanOrEqual(0);
    expect(result.probMddOver30pct).toBeLessThanOrEqual(1);
  });

  it("히스토그램 빈도의 합은 반복 횟수와 같다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), settings);
    expect(result.status).toBe("ok");

    const cagrTotal = result.cagrHistogram.reduce((sum, bin) => sum + bin.count, 0);
    const mddTotal = result.mddHistogram.reduce((sum, bin) => sum + bin.count, 0);
    expect(cagrTotal).toBe(result.nIterations);
    expect(mddTotal).toBe(result.nIterations);
  });

  it("blockSize 1(일별 독립 재표본)도 동작한다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), {
      ...settings,
      blockSize: 1,
    });
    expect(result.status).toBe("ok");
    expect(result.blockSize).toBe(1);
  });

  it("같은 seed는 같은 분포를 재현한다", async () => {
    const first = await runMonteCarloSimulation(buildResult(300), settings);
    const second = await runMonteCarloSimulation(buildResult(300), settings);
    expect(first.status).toBe("ok");
    expect(second.status).toBe("ok");
    expect(first.cagr).toEqual(second.cagr);
    expect(first.mdd).toEqual(second.mdd);
  });

  it("취소 콜백이 true를 반환하면 중단한다", async () => {
    const result = await runMonteCarloSimulation(
      buildResult(300),
      { ...settings, iterations: 2000 },
      undefined,
      () => true
    );
    expect(result.status).toBe("cancelled");
  });

  it("진행률 콜백은 0~1 범위로 증가하며 마지막에 1을 보고한다", async () => {
    const reported: number[] = [];
    const result = await runMonteCarloSimulation(
      buildResult(300),
      { ...settings, iterations: 1000 },
      (ratio) => reported.push(ratio)
    );
    expect(result.status).toBe("ok");
    expect(reported.length).toBeGreaterThan(0);
    expect(reported[reported.length - 1]).toBe(1);
    for (let i = 1; i < reported.length; i += 1) {
      expect(reported[i]).toBeGreaterThanOrEqual(reported[i - 1]);
    }
  });
});

describe("buildMonteCarloHistogram", () => {
  it("빈 배열이면 빈 히스토그램을 반환한다", () => {
    expect(buildMonteCarloHistogram([])).toEqual([]);
  });

  it("모든 값이 같으면 단일 구간으로 묶는다", () => {
    expect(buildMonteCarloHistogram([0.1, 0.1, 0.1])).toEqual([
      { x0: 0.1, x1: 0.1, count: 3 },
    ]);
  });

  it("구간 수와 총 빈도를 보존한다", () => {
    const values = Array.from({ length: 500 }, (_, index) => Math.sin(index) * 0.2);
    const bins = buildMonteCarloHistogram(values, 24);
    expect(bins).toHaveLength(24);
    expect(bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(500);
    expect(bins[0].x0).toBeCloseTo(Math.min(...values));
    expect(bins[bins.length - 1].x1).toBeCloseTo(Math.max(...values));
  });
});

describe("extractTradeReturns", () => {
  it("종목별 FIFO 매칭으로 완결 거래 수익률을 추정한다", () => {
    const result = {
      tradesList: [
        { date: "2024-01-02", symbol: "A", type: "buy", price: 100 },
        { date: "2024-01-10", symbol: "B", type: "buy", price: 200 },
        { date: "2024-02-01", symbol: "A", type: "sell", price: 110 },
        { date: "2024-02-05", symbol: "B", type: "sell", price: 180 },
        { date: "2024-03-01", symbol: "A", type: "buy", price: 120 }, // 미청산 → 제외
      ],
    };
    const returns = extractTradeReturns(result);
    expect(returns).toHaveLength(2);
    expect(returns[0]).toBeCloseTo(0.1);
    expect(returns[1]).toBeCloseTo(-0.1);
  });

  it("tradesList가 없으면 signals(entry/exit)로 폴백한다", () => {
    const result = {
      tradesList: [],
      signals: [
        { date: "2024-01-02", symbol: "A", type: "entry", condition: "x", price: 100 },
        { date: "2024-02-01", symbol: "A", type: "exit", condition: "y", price: 105 },
      ],
    };
    const returns = extractTradeReturns(result);
    expect(returns).toHaveLength(1);
    expect(returns[0]).toBeCloseTo(0.05);
  });
});

describe("runMonteCarloSimulation — 거래 재표본 모드", () => {
  const tradeSettings = { iterations: 200, blockSize: 21, seed: 42, mode: "trades" };

  it("완결 거래가 부족하면 에러를 반환한다", async () => {
    const result = await runMonteCarloSimulation(
      { ...buildResult(300), tradesList: buildTrades(5) },
      tradeSettings
    );
    expect(result.status).toBe("error");
    expect(result.message).toContain("거래");
  });

  it("거래 수익률 복원추출로 분포를 생성한다", async () => {
    const backtest = {
      ...buildResult(300),
      dates: Array.from({ length: 300 }, (_, i) => `d${i}`),
      tradesList: buildTrades(40),
    };
    const result = await runMonteCarloSimulation(backtest, tradeSettings);
    expect(result.status).toBe("ok");
    expect(result.mode).toBe("trades");
    expect(result.tradeCount).toBe(40);
    expect(result.cagrHistogram.reduce((sum, bin) => sum + bin.count, 0)).toBe(result.nIterations);
    expect(result.mdd.min).toBeGreaterThanOrEqual(0);
    expect(result.cagr.min).toBeLessThanOrEqual(result.cagr.max);
  });

  it("같은 seed는 같은 거래 재표본 분포를 재현한다", async () => {
    const backtest = {
      ...buildResult(300),
      dates: Array.from({ length: 300 }, (_, i) => `d${i}`),
      tradesList: buildTrades(40),
    };
    const first = await runMonteCarloSimulation(backtest, tradeSettings);
    const second = await runMonteCarloSimulation(backtest, tradeSettings);
    expect(first.cagr).toEqual(second.cagr);
    expect(first.mdd).toEqual(second.mdd);
  });

  it("거래 모드에서도 취소가 동작한다", async () => {
    const backtest = {
      ...buildResult(300),
      dates: Array.from({ length: 300 }, (_, i) => `d${i}`),
      tradesList: buildTrades(40),
    };
    const result = await runMonteCarloSimulation(
      backtest,
      { ...tradeSettings, iterations: 2000 },
      undefined,
      () => true
    );
    expect(result.status).toBe("cancelled");
  });
});
