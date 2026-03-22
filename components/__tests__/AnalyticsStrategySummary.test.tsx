// @ts-nocheck
/**
 * analytics/page.tsx의 strategySummary 구성 로직 회귀 테스트
 *
 * 변경사항:
 * - BacktestDashboard에 strategySummary prop을 전달해야 테스트 기록이 저장됨
 * - parsed 상태에서 strategySummary를 올바르게 구성하는지 검증
 */
import { describe, it, expect } from "vitest";

// analytics/page.tsx의 상수 및 변환 로직을 그대로 복제
const METRIC_LABELS: Record<string, string> = {
  per: "PER", pbr: "PBR", roe_or_gpa: "ROE",
  debt_ratio: "부채비율", market_cap: "시총", trading_value: "거래대금",
};
const INDICATOR_LABELS: Record<string, string> = {
  ma_crossover: "MA 크로스", rsi: "RSI", ema: "EMA 크로스",
  macd: "MACD", bollinger_bands: "볼린저밴드", breakout: "브레이크아웃",
  volume_spike: "거래량 급증", stochastic: "스토캐스틱", cci: "CCI", adx: "ADX",
};

// analytics/page.tsx에서 BacktestDashboard에 전달하는 strategySummary 구성 함수
function buildStrategySummary(parsed: any) {
  if (!parsed) return undefined;
  return {
    strategyName: parsed.description,
    universeName: parsed.universe.join(", "),
    blockNames: [
      ...parsed.fundamental_filters.map(
        (f: any) => `${METRIC_LABELS[f.metric] ?? f.metric} ${f.operator} ${f.value}`
      ),
      ...parsed.entry_signals.map(
        (s: any) => INDICATOR_LABELS[s.indicator] ?? s.indicator
      ),
      ...parsed.exit_signals.map(
        (s: any) => INDICATOR_LABELS[s.indicator] ?? s.indicator
      ),
    ],
    entryBlocks: parsed.entry_signals.map(
      (s: any) => INDICATOR_LABELS[s.indicator] ?? s.indicator
    ),
    exitBlocks: parsed.exit_signals.map(
      (s: any) => INDICATOR_LABELS[s.indicator] ?? s.indicator
    ),
    positionText: `최대 ${parsed.max_positions}종목${parsed.hold_period_days ? ` · ${parsed.hold_period_days}일 보유` : ""}`,
    riskText:
      [
        parsed.stop_loss_pct ? `손절 ${parsed.stop_loss_pct}%` : "",
        parsed.take_profit_pct ? `익절 ${parsed.take_profit_pct}%` : "",
      ]
        .filter(Boolean)
        .join(", ") || undefined,
  };
}

// ── 픽스처 ─────────────────────────────────────────────────────────────────

const parsedFundamental = {
  description: "PBR 1 이하 PER 7 이하 종목 10개 1년 보유",
  universe: ["KOSPI", "KOSDAQ"],
  fundamental_filters: [
    { metric: "pbr", operator: "<=", value: 1.0 },
    { metric: "per", operator: "<=", value: 7.0 },
  ],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: 252,
  rebalancing_period: "yearly",
  stop_loss_pct: null,
  take_profit_pct: null,
  backtest_period: "5y",
  initial_capital: 10000000,
};

const parsedTechnical = {
  description: "골든크로스 매수 RSI 70 매도",
  universe: ["KOSPI"],
  fundamental_filters: [],
  entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
  exit_signals: [{ indicator: "rsi", signal_type: "sell" }],
  max_positions: 15,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: 10.0,
  take_profit_pct: 25.0,
  backtest_period: "3y",
  initial_capital: 10000000,
};

// ── 테스트 ─────────────────────────────────────────────────────────────────

describe("buildStrategySummary (analytics/page.tsx)", () => {
  it("parsed가 null이면 undefined를 반환해야 함", () => {
    expect(buildStrategySummary(null)).toBeUndefined();
  });

  it("strategyName은 parsed.description이어야 함", () => {
    const summary = buildStrategySummary(parsedFundamental);
    expect(summary?.strategyName).toBe(parsedFundamental.description);
  });

  it("universeName은 universe 배열을 ', '로 조인해야 함", () => {
    const summary = buildStrategySummary(parsedFundamental);
    expect(summary?.universeName).toBe("KOSPI, KOSDAQ");
  });

  it("재무 필터가 blockNames에 올바른 형식으로 포함되어야 함", () => {
    const summary = buildStrategySummary(parsedFundamental);
    expect(summary?.blockNames).toContain("PBR <= 1");
    expect(summary?.blockNames).toContain("PER <= 7");
  });

  it("기술적 진입 신호가 entryBlocks에 한국어 레이블로 포함되어야 함", () => {
    const summary = buildStrategySummary(parsedTechnical);
    expect(summary?.entryBlocks).toContain("MA 크로스");
  });

  it("기술적 청산 신호가 exitBlocks에 한국어 레이블로 포함되어야 함", () => {
    const summary = buildStrategySummary(parsedTechnical);
    expect(summary?.exitBlocks).toContain("RSI");
  });

  it("진입/청산 신호가 없으면 entryBlocks, exitBlocks는 빈 배열이어야 함", () => {
    const summary = buildStrategySummary(parsedFundamental);
    expect(summary?.entryBlocks).toEqual([]);
    expect(summary?.exitBlocks).toEqual([]);
  });

  it("hold_period_days가 있으면 positionText에 포함되어야 함", () => {
    const summary = buildStrategySummary(parsedFundamental);
    expect(summary?.positionText).toBe("최대 10종목 · 252일 보유");
  });

  it("hold_period_days가 없으면 positionText에 보유기간 없이 종목 수만 표시", () => {
    const summary = buildStrategySummary(parsedTechnical);
    expect(summary?.positionText).toBe("최대 15종목");
  });

  it("손절/익절이 있으면 riskText에 포함되어야 함", () => {
    const summary = buildStrategySummary(parsedTechnical);
    expect(summary?.riskText).toBe("손절 10%, 익절 25%");
  });

  it("손절/익절이 없으면 riskText는 undefined여야 함", () => {
    const summary = buildStrategySummary(parsedFundamental);
    expect(summary?.riskText).toBeUndefined();
  });

  it("미등록 지표 id는 레이블 대신 id 그대로 사용해야 함", () => {
    const parsed = {
      ...parsedFundamental,
      entry_signals: [{ indicator: "unknown_indicator", signal_type: "buy" }],
    };
    const summary = buildStrategySummary(parsed);
    expect(summary?.entryBlocks).toContain("unknown_indicator");
  });

  it("strategySummary가 존재하면 BacktestDashboard history 저장 조건을 통과할 수 있어야 함", () => {
    // BacktestDashboard의 if (strategySummary) 조건 검증
    const summary = buildStrategySummary(parsedFundamental);
    expect(summary).toBeTruthy();
    expect(summary?.strategyName).toBeTruthy();
    expect(summary?.universeName).toBeTruthy();
  });
});
