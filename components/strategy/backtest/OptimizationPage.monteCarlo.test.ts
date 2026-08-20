// @ts-nocheck
import { describe, expect, it } from "vitest";

import {
  backtestYears,
  buildMonteCarloHistogram,
  extractTradeReturns,
  formatMonteCarloMethodLabel,
  KRX_TRADING_DAYS_PER_YEAR,
  recommendMonteCarloMethod,
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

  it("원래 순서 지표를 재구성하고, 분포 내 위치는 MDD에만 제공한다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), settings);
    expect(result.status).toBe("ok");
    expect(result.observed).toBeDefined();
    expect(Number.isFinite(result.observed.cagr)).toBe(true);
    expect(result.observed.mdd).toBeGreaterThanOrEqual(0);
    expect(result.observed.mddPct).toBeGreaterThanOrEqual(0);
    expect(result.observed.mddPct).toBeLessThanOrEqual(1);
    // CAGR은 순서 불변(성장배수의 곱)이라 위치를 내지 않는다 — 회귀 방지
    expect(result.observed).not.toHaveProperty("cagrPct");
  });

  it("관측 CAGR은 부트스트랩 분포 한가운데에 온다(순서 불변) — 위치 카드가 무의미한 근거", async () => {
    // 부트스트랩 평균은 관측 평균과 같으므로 어떤 방식이든 관측 CAGR ≤ 인 시나리오 비율은 ~50%.
    // 08-19 감사에서 8시드×3방식 전부 0.47~0.59로 실측됐다. 이 성질이 깨지면 계산 자체가 바뀐 것.
    const backtest = buildResult(600);
    for (const s of [
      { ...settings, blockSize: 1, iterations: 400 },
      { ...settings, blockSize: 21, iterations: 400 },
      { ...settings, blockSize: 10, blockMethod: "stationary", iterations: 400 },
    ]) {
      const result = await runMonteCarloSimulation(backtest, s);
      expect(result.status).toBe("ok");
      const values = [];
      // 히스토그램에서 관측 이하 비율을 근사한다(빈 경계 오차 허용)
      let below = 0;
      let total = 0;
      for (const bin of result.cagrHistogram) {
        total += bin.count;
        if (bin.x1 <= result.observed.cagr) below += bin.count;
      }
      const pct = below / total;
      expect(pct).toBeGreaterThan(0.25);
      expect(pct).toBeLessThan(0.75);
      values.push(pct);
    }
  });

  it("연환산은 엔진과 같은 달력 연수(dates 경과일÷365.25)·KRX 246일을 쓴다", async () => {
    // 1년치(246봉)를 2024-01-02~2024-12-30 달력으로 깔면 연수 ≈ 0.995년.
    // 봉수÷252(=0.976년)로 세면 CAGR이 ~2% 상대 과대 — 백테스트 결과 탭 CAGR과 어긋나던 원인.
    const dates = [];
    const start = Date.parse("2024-01-02");
    for (let i = 0; i < 246; i += 1) {
      dates.push(new Date(start + Math.round((i * 363) / 245) * 86_400_000).toISOString().slice(0, 10));
    }
    expect(backtestYears(dates, 246)).toBeCloseTo(363 / 365.25, 6);
    expect(backtestYears(undefined, 246)).toBeCloseTo(1, 6);
    expect(backtestYears(["bad", "worse"], 123)).toBeCloseTo(123 / KRX_TRADING_DAYS_PER_YEAR, 6);
    expect(KRX_TRADING_DAYS_PER_YEAR).toBe(246);

    // 관측 CAGR = (마지막/처음)^(1/years) − 1 이 dates 기준 연수로 계산돼야 한다.
    const backtest = { ...buildResult(246), dates };
    const result = await runMonteCarloSimulation(backtest, { ...settings, blockSize: 21, iterations: 100 });
    expect(result.status).toBe("ok");
    const equity = backtest.equity;
    const expected = (equity[equity.length - 1] / equity[0]) ** (1 / (363 / 365.25)) - 1;
    expect(result.observed.cagr).toBeCloseTo(expected, 8);
  });

  it("blockSize 1(일별 독립 재표본)도 동작한다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), {
      ...settings,
      blockSize: 1,
    });
    expect(result.status).toBe("ok");
    expect(result.blockSize).toBe(1);
  });

  it("가변 블록(stationary) 방식이 동작하고 같은 seed로 재현된다", async () => {
    const stationarySettings = { ...settings, blockMethod: "stationary" as const, blockSize: 10 };
    const first = await runMonteCarloSimulation(buildResult(300), stationarySettings);
    const second = await runMonteCarloSimulation(buildResult(300), stationarySettings);
    expect(first.status).toBe("ok");
    expect(first.blockMethod).toBe("stationary");
    expect(first.cagr).toEqual(second.cagr);
    expect(first.mdd).toEqual(second.mdd);
  });

  it("낙폭 지속(underwater)과 표본 충분성 지표를 제공한다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), settings);
    expect(result.status).toBe("ok");
    expect(result.underwater).toBeDefined();
    expect(result.underwater.median).toBeGreaterThanOrEqual(0);
    expect(result.underwaterUnrecoveredRatio).toBeGreaterThanOrEqual(0);
    expect(result.underwaterUnrecoveredRatio).toBeLessThanOrEqual(1);
    expect(result.sufficiency).toBeDefined();
    expect(result.sufficiency.effectiveSamples).toBeGreaterThan(0);
    expect(typeof result.sufficiency.low).toBe("boolean");
  });

  it("기간 끝까지 고점을 회복하지 못한 시나리오 비율을 집계한다(검열 고지 근거)", async () => {
    // 매 스텝 하락하는 equity → 모든 재표본 경로도 전 구간 하락 → 미회복 100%,
    // 최장 언더워터는 경로 길이(수익률 포인트 수) 전체가 된다.
    let value = 10_000_000;
    const equity = Array.from({ length: 260 }, () => (value *= 0.999));
    const result = await runMonteCarloSimulation({ equity, initialCapital: 10_000_000 }, settings);
    expect(result.status).toBe("ok");
    expect(result.underwaterUnrecoveredRatio).toBe(1);
    expect(result.underwater.median).toBe(equity.length - 1);
  });

  it("실행 파라미터(seed 포함)를 결과에 담아 화면 표시에 쓸 수 있다", async () => {
    const result = await runMonteCarloSimulation(buildResult(300), { ...settings, seed: 7 });
    expect(result.status).toBe("ok");
    expect(result.seed).toBe(7);
    expect(result.nIterations).toBe(settings.iterations);
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

describe("formatMonteCarloMethodLabel", () => {
  it("결과 필드에서 방식 라벨을 만든다", () => {
    expect(formatMonteCarloMethodLabel({ mode: "returns", blockSize: 1 })).toBe("일별 재표본");
    expect(formatMonteCarloMethodLabel({ mode: "returns", blockSize: 21 })).toBe("21일 블록");
    expect(
      formatMonteCarloMethodLabel({ mode: "returns", blockMethod: "stationary", blockSize: 10 })
    ).toBe("평균 10일 가변 블록");
    expect(formatMonteCarloMethodLabel({ mode: "trades", blockSize: 21 })).toBe("거래 재표본");
  });
});

describe("recommendMonteCarloMethod", () => {
  it("평균 보유기간이 없으면 추천하지 않는다", () => {
    expect(recommendMonteCarloMethod({})).toBeNull();
    expect(recommendMonteCarloMethod({ avgHoldingDays: 0 })).toBeNull();
  });

  it("평균 보유기간에 따라 블록 길이를 추천한다", () => {
    expect(recommendMonteCarloMethod({ avgHoldingDays: 1 })?.blockSize).toBe(1);
    expect(recommendMonteCarloMethod({ avgHoldingDays: 4 })?.blockSize).toBe(5);
    expect(recommendMonteCarloMethod({ avgHoldingDays: 12 })?.blockSize).toBe(10);
    expect(recommendMonteCarloMethod({ avgHoldingDays: 30 })?.blockSize).toBe(21);
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
  it("수량·일별 자산이 없으면 가격수익률로 강등하고 sized=false를 반환한다", () => {
    const result = {
      tradesList: [
        { date: "2024-01-02", symbol: "A", type: "buy", price: 100 },
        { date: "2024-01-10", symbol: "B", type: "buy", price: 200 },
        { date: "2024-02-01", symbol: "A", type: "sell", price: 110 },
        { date: "2024-02-05", symbol: "B", type: "sell", price: 180 },
        { date: "2024-03-01", symbol: "A", type: "buy", price: 120 }, // 미청산 → 제외
      ],
    };
    const { returns, sized } = extractTradeReturns(result);
    expect(sized).toBe(false);
    expect(returns).toHaveLength(2);
    expect(returns[0]).toBeCloseTo(0.1);
    expect(returns[1]).toBeCloseTo(-0.1);
  });

  it("수량과 진입시점 자산이 있으면 자본 대비 기여도(사이징 반영)를 계산한다", () => {
    const result = {
      initialCapital: 1000,
      equity: [1000, 1000],
      dates: ["2024-01-02", "2024-02-01"],
      tradesList: [
        { date: "2024-01-02", symbol: "A", type: "buy", price: 100, quantity: 2 },
        { date: "2024-02-01", symbol: "A", type: "sell", price: 110, quantity: 2 },
      ],
    };
    const { returns, sized } = extractTradeReturns(result);
    expect(sized).toBe(true);
    expect(returns).toHaveLength(1);
    // 가격수익률은 0.1이지만, 자본 1000 중 200만 투입 → 기여도 = 20/1000 = 0.02
    expect(returns[0]).toBeCloseTo(0.02);
  });

  it("매도 체결에 순손익(pnl)이 있으면 체결가 차액 대신 그것을 써서 수수료·거래세를 반영한다", () => {
    const result = {
      initialCapital: 1000,
      equity: [1000, 1000],
      dates: ["2024-01-02", "2024-02-01"],
      tradesList: [
        { date: "2024-01-02", symbol: "A", type: "buy", price: 100, quantity: 2 },
        // 차액 20원, 비용 0.45% 차감한 순손익 19.055원을 엔진이 실어 준다
        { date: "2024-02-01", symbol: "A", type: "sell", price: 110, quantity: 2, pnl: 19.055 },
      ],
    };
    const { returns, sized, netOfFees } = extractTradeReturns(result);
    expect(sized).toBe(true);
    expect(netOfFees).toBe(true);
    expect(returns[0]).toBeCloseTo(0.019055, 8);
  });

  it("부분 체결이면 주당 순손익으로 배분하고, pnl 없는 매도가 섞이면 netOfFees=false", () => {
    const result = {
      initialCapital: 1000,
      equity: [1000, 1000, 1000],
      dates: ["2024-01-02", "2024-02-01", "2024-03-01"],
      tradesList: [
        { date: "2024-01-02", symbol: "A", type: "buy", price: 100, quantity: 4 },
        { date: "2024-02-01", symbol: "A", type: "sell", price: 110, quantity: 2, pnl: 18 }, // 주당 9
        { date: "2024-03-01", symbol: "A", type: "sell", price: 120, quantity: 2 }, // pnl 없음 → 차액 40
      ],
    };
    const { returns, netOfFees } = extractTradeReturns(result);
    expect(netOfFees).toBe(false);
    expect(returns[0]).toBeCloseTo(0.018, 8);
    expect(returns[1]).toBeCloseTo(0.04, 8);
  });

  it("tradesList가 없으면 signals(entry/exit)로 폴백한다", () => {
    const result = {
      tradesList: [],
      signals: [
        { date: "2024-01-02", symbol: "A", type: "entry", condition: "x", price: 100 },
        { date: "2024-02-01", symbol: "A", type: "exit", condition: "y", price: 105 },
      ],
    };
    const { returns, sized } = extractTradeReturns(result);
    expect(sized).toBe(false);
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
    expect(result.tradeSizing).toBe("equity-weighted");
    // buildTrades에는 pnl이 없다 → 비용 전 손익으로 계산됐음을 결과에 표시한다
    expect(result.tradeCosts).toBe("gross");
    expect(result.observed).toBeDefined();
    expect(result.observed).not.toHaveProperty("cagrPct");
    expect(result.cagrHistogram.reduce((sum, bin) => sum + bin.count, 0)).toBe(result.nIterations);
    expect(result.mdd.min).toBeGreaterThanOrEqual(0);
    expect(result.cagr.min).toBeLessThanOrEqual(result.cagr.max);
    expect(result.underwaterUnrecoveredRatio).toBeGreaterThanOrEqual(0);
    expect(result.underwaterUnrecoveredRatio).toBeLessThanOrEqual(1);
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
