import { describe, it, expect } from "vitest";

import {
  buildStrategySummaryFromRequest,
  getDisplayUniverseLabels,
  type ParsedSummary,
} from "./strategy-summary";

// 업종 제외 필터(엔진 v16.24) — 배지에 드러내지 않으면 제외가 조용히 사라진 것처럼 보인다.

const base: ParsedSummary = {
  description: "테스트",
  universe: ["kospi"],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "monthly",
  stop_loss_pct: null,
  take_profit_pct: null,
  backtest_period: "full",
  initial_capital: 10000000,
};

describe("업종 제외 배지", () => {
  it("파싱 요약의 exclude_sectors를 업종별 '제외' 배지로 만든다", () => {
    const labels = getDisplayUniverseLabels({ ...base, sector: "반도체", exclude_sectors: ["은행", "지주회사"] });
    expect(labels).toContain("반도체 업종");
    expect(labels).toContain("은행 업종 제외");
    expect(labels).toContain("지주회사 업종 제외");
  });

  it("실행된 요청의 exclude_sectors도 유니버스 이름에 실린다", () => {
    const summary = buildStrategySummaryFromRequest({
      universe_id: "kospi",
      exclude_sectors: ["금융지주"],
      risk: { max_positions: 10 },
    });
    expect(summary?.universeName).toContain("금융지주 업종 제외");
  });
});
