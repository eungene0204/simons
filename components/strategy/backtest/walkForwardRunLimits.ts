// 워크포워드 실행 전 판정 — 서버가 실행할 수 없는 설정과 너무 오래 걸리는 설정을 막고,
// 같은 비용 모델로 시간 안에 끝나는 설정을 찾아 안내한다.

// 실행 전에 막는 예상 소요 시간 상한(초).
export const MAX_WALK_FORWARD_RUN_SECONDS = 600;
// 백엔드 engine/walk_forward.py — 이보다 짧은 기간은 분할 전에 오류로 끝난다.
export const MIN_WALK_FORWARD_TOTAL_BARS = 60;
// 백엔드 engine/walk_forward.py의 MAX_WINDOWS와 동일한 값으로 유지한다.
export const MAX_WALK_FORWARD_WINDOWS = 24;
// 백엔드 engine/grid_optimizer.py의 MAX_GRID_COMBINATIONS와 동일한 값으로 유지한다.
export const MAX_GRID_COMBINATIONS = 500;
// 베이지안 시도 횟수 선택지 — 화면 버튼과 같은 목록.
export const BAYESIAN_TRIAL_OPTIONS = [20, 30, 50] as const;
// 백엔드는 최적화 세션 동안 종목별 데이터 준비(Phase1)를 재사용한다 — 한 구간의 두 번째
// 시도부터는 전체 비용의 일부만 든다(2026-08-19 실측 ≈ 6%, 보수적으로 10%).
export const CACHED_TRIAL_COST_RATIO = 0.1;

// 총 백테스트 수 = 준비(0~1회) + 구간 수 × (구간당 백테스트 수 + OOS 1회).
// 전체 비용은 준비 + 구간마다 첫 시도 1회 + OOS 1회, 나머지 시도는 캐시 재사용 비용.
export function estimateWalkForwardSeconds(input: {
  windows: number;
  backtestsPerWindow: number;
  prepareBacktests: number;
  perBacktestSec: number;
}): number {
  const { windows, backtestsPerWindow, prepareBacktests, perBacktestSec } = input;
  if (backtestsPerWindow <= 0) return 0;
  const total = prepareBacktests + windows * (backtestsPerWindow + 1);
  const fullCost = prepareBacktests + windows * 2;
  return (fullCost + Math.max(0, total - fullCost) * CACHED_TRIAL_COST_RATIO) * perBacktestSec;
}

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

// 백엔드 _split_windows(is_bars/oos_bars)와 같은 규칙 — 검증 길이를 다 채우는 창만 센다.
export function deriveSplitCount(totalBars: number, trainBars: number, validationBars: number) {
  if (validationBars <= 0 || totalBars <= trainBars) return 1;
  return Math.max(1, Math.floor((totalBars - trainBars) / validationBars));
}

// 화면의 '구간 길이·학습 비중' 슬라이더가 두 기간을 정하는 규칙과 같다.
export function splitWindowBars(windowBars: number, trainRatioPct: number, minWindowBars: number) {
  const trainBars = clamp(
    Math.round(windowBars * (trainRatioPct / 100)),
    minWindowBars,
    Math.max(minWindowBars, windowBars - minWindowBars)
  );
  return { trainBars, validationBars: Math.max(minWindowBars, windowBars - trainBars) };
}

export type WalkForwardRunState = {
  totalBars: number;
  minWindowBars: number;
  windowBars: number;
  windowBarsMax: number;
  trainRatioPct: number;
  windows: number;
  method: "bayesian" | "grid";
  nTrials: number;
  gridCombinations: number;
  prepareBacktests: number;
  perBacktestSec: number;
};

export type WalkForwardSuggestion =
  | { kind: "trials"; trials: number; seconds: number }
  | { kind: "switch_to_bayesian"; trials: number; seconds: number }
  | { kind: "window_bars"; windowBars: number; windows: number; seconds: number }
  | { kind: "shrink_strategy" };

export type WalkForwardRunVerdict =
  | { status: "ok"; seconds: number }
  | { status: "too_short"; totalBars: number }
  | { status: "too_many_windows"; windows: number; suggestions: WalkForwardSuggestion[] }
  | { status: "too_many_combinations"; combinations: number; suggestions: WalkForwardSuggestion[] }
  | { status: "too_long"; seconds: number; suggestions: WalkForwardSuggestion[] };

const backtestsPerWindow = (state: Pick<WalkForwardRunState, "method" | "nTrials" | "gridCombinations">) =>
  state.method === "grid" ? state.gridCombinations : state.nTrials;

const secondsFor = (state: WalkForwardRunState, overrides: Partial<WalkForwardRunState> = {}) => {
  const next = { ...state, ...overrides };
  return estimateWalkForwardSeconds({
    windows: next.windows,
    backtestsPerWindow: backtestsPerWindow(next),
    prepareBacktests: next.prepareBacktests,
    perBacktestSec: next.perBacktestSec,
  });
};

// 현재 학습 비중을 유지한 채 구간 길이만 늘려, 조건을 만족하는 가장 짧은 구간 길이를 찾는다.
function shortestFittingWindowBars(state: WalkForwardRunState, fits: (windows: number, seconds: number) => boolean) {
  for (let bars = state.windowBars + 1; bars <= state.windowBarsMax; bars += 1) {
    const { trainBars, validationBars } = splitWindowBars(bars, state.trainRatioPct, state.minWindowBars);
    const windows = deriveSplitCount(state.totalBars, trainBars, validationBars);
    const seconds = secondsFor(state, { windows });
    if (fits(windows, seconds)) return { kind: "window_bars" as const, windowBars: bars, windows, seconds };
  }
  return null;
}

const withinTime = (seconds: number) => seconds <= MAX_WALK_FORWARD_RUN_SECONDS;

function bayesianFallback(state: WalkForwardRunState): WalkForwardSuggestion | null {
  const trials = [...BAYESIAN_TRIAL_OPTIONS].reverse().find((n) =>
    withinTime(secondsFor(state, { method: "bayesian", nTrials: n }))
  );
  return trials ? { kind: "switch_to_bayesian", trials, seconds: secondsFor(state, { method: "bayesian", nTrials: trials }) } : null;
}

function timeSuggestions(state: WalkForwardRunState): WalkForwardSuggestion[] {
  const suggestions: WalkForwardSuggestion[] = [];
  if (state.method === "bayesian") {
    // 줄일 수 있는 시도 횟수 중 가장 큰 것 — 탐색량을 최대한 지킨다.
    const trials = [...BAYESIAN_TRIAL_OPTIONS]
      .filter((n) => n < state.nTrials)
      .reverse()
      .find((n) => withinTime(secondsFor(state, { nTrials: n })));
    if (trials) suggestions.push({ kind: "trials", trials, seconds: secondsFor(state, { nTrials: trials }) });
  } else {
    const bayesian = bayesianFallback(state);
    if (bayesian) suggestions.push(bayesian);
  }
  const longer = shortestFittingWindowBars(state, (_windows, seconds) => withinTime(seconds));
  if (longer) suggestions.push(longer);
  if (suggestions.length === 0) suggestions.push({ kind: "shrink_strategy" });
  return suggestions;
}

export function judgeWalkForwardRun(state: WalkForwardRunState): WalkForwardRunVerdict {
  if (state.totalBars < MIN_WALK_FORWARD_TOTAL_BARS) {
    return { status: "too_short", totalBars: state.totalBars };
  }
  if (state.windows > MAX_WALK_FORWARD_WINDOWS) {
    // 상한을 지키면서 시간 안에도 끝나는 길이를 먼저 찾고, 없으면 상한만 지키는 길이를 안내한다.
    const longer =
      shortestFittingWindowBars(state, (windows, seconds) => windows <= MAX_WALK_FORWARD_WINDOWS && withinTime(seconds)) ??
      shortestFittingWindowBars(state, (windows) => windows <= MAX_WALK_FORWARD_WINDOWS);
    return { status: "too_many_windows", windows: state.windows, suggestions: longer ? [longer] : [] };
  }
  if (state.method === "grid" && state.gridCombinations > MAX_GRID_COMBINATIONS) {
    const bayesian = bayesianFallback(state);
    return {
      status: "too_many_combinations",
      combinations: state.gridCombinations,
      suggestions: bayesian ? [bayesian] : [{ kind: "shrink_strategy" }],
    };
  }
  const seconds = secondsFor(state);
  if (!withinTime(seconds)) return { status: "too_long", seconds, suggestions: timeSuggestions(state) };
  return { status: "ok", seconds };
}
