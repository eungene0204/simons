import { describe, expect, it } from "vitest";
import {
  MAX_WALK_FORWARD_RUN_SECONDS,
  estimateWalkForwardSeconds,
  judgeWalkForwardRun,
  type WalkForwardRunState,
} from "../walkForwardRunLimits";

// 1,000거래일 · 구간 340(학습 75%) · 베이지안 30회 → 구간 3개.
const base: WalkForwardRunState = {
  totalBars: 1000,
  minWindowBars: 20,
  windowBars: 340,
  windowBarsMax: 1000,
  trainRatioPct: 75,
  windows: 3,
  method: "bayesian",
  nTrials: 30,
  gridCombinations: 0,
  prepareBacktests: 0,
  perBacktestSec: 10,
};

describe("estimateWalkForwardSeconds", () => {
  it("구간마다 첫 시도·OOS는 전체 비용, 나머지 시도는 캐시 재사용 비용으로 센다", () => {
    // 전체 비용 3×2=6회 + 캐시 87회×0.1 = 14.7회 × 10s
    expect(estimateWalkForwardSeconds({ windows: 3, backtestsPerWindow: 30, prepareBacktests: 0, perBacktestSec: 10 })).toBeCloseTo(147);
  });
});

describe("judgeWalkForwardRun", () => {
  it("예상 시간이 상한 안이면 실행을 허용한다", () => {
    expect(judgeWalkForwardRun(base)).toEqual({ status: "ok", seconds: expect.any(Number) });
  });

  it("예상 시간이 10분을 넘으면 막고, 시간 안에 끝나는 설정을 함께 돌려준다", () => {
    const verdict = judgeWalkForwardRun({ ...base, perBacktestSec: 50 });

    expect(verdict.status).toBe("too_long");
    if (verdict.status !== "too_long") return;
    expect(verdict.seconds).toBeGreaterThan(MAX_WALK_FORWARD_RUN_SECONDS);
    expect(verdict.suggestions.length).toBeGreaterThan(0);
    for (const suggestion of verdict.suggestions) {
      expect(suggestion.kind).not.toBe("shrink_strategy");
      if ("seconds" in suggestion) expect(suggestion.seconds).toBeLessThanOrEqual(MAX_WALK_FORWARD_RUN_SECONDS);
    }
    // 구간 길이를 늘리면 구간 수가 줄어 시간 안에 들어온다
    const longer = verdict.suggestions.find((s) => s.kind === "window_bars");
    expect(longer && longer.kind === "window_bars" && longer.windows).toBeLessThan(base.windows);
  });

  it("어떤 설정으로도 시간 안에 끝낼 수 없으면 종목 범위·기간을 줄이라고 안내한다", () => {
    const verdict = judgeWalkForwardRun({ ...base, perBacktestSec: 600 });

    expect(verdict).toEqual({ status: "too_long", seconds: expect.any(Number), suggestions: [{ kind: "shrink_strategy" }] });
  });

  it("그리드 조합이 너무 많아 오래 걸리면 베이지안으로 바꾸는 설정을 안내한다", () => {
    const verdict = judgeWalkForwardRun({ ...base, method: "grid", gridCombinations: 400, perBacktestSec: 20 });

    expect(verdict.status).toBe("too_long");
    if (verdict.status !== "too_long") return;
    expect(verdict.suggestions[0]).toMatchObject({ kind: "switch_to_bayesian" });
  });

  it("서버가 실행할 수 없는 설정은 시간보다 먼저 막는다", () => {
    expect(judgeWalkForwardRun({ ...base, totalBars: 40 })).toEqual({ status: "too_short", totalBars: 40 });
    expect(judgeWalkForwardRun({ ...base, method: "grid", gridCombinations: 900 }).status).toBe("too_many_combinations");

    const windows = judgeWalkForwardRun({ ...base, windowBars: 60, windows: 30 });
    expect(windows.status).toBe("too_many_windows");
    if (windows.status !== "too_many_windows") return;
    expect(windows.suggestions[0]).toMatchObject({ kind: "window_bars" });
    const [suggestion] = windows.suggestions;
    expect(suggestion.kind === "window_bars" && suggestion.windows).toBeLessThanOrEqual(24);
  });
});
