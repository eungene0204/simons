import { describe, it, expect } from "vitest";

import {
  getPositionLabel,
  getSelectionScope,
  type ParsedSummary,
} from "./strategy-summary";

// 종목 선정 범위(설계 스펙 § 6). 판정 정본은 백엔드 engine/selection_scope.py이고
// 여기는 배지 문구용 미러다 — 두 규칙이 갈리면 화면과 실제 실행이 어긋난다.
// 아래 케이스는 backend/tests/test_selection_scope.py와 같은 조합을 쓴다.

const base: ParsedSummary = {
  description: "테스트",
  universe: ["kospi"],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  backtest_period: "full",
  initial_capital: 10000000,
};

const themeSymbols = Array.from({ length: 36 }, (_, i) => String(i).padStart(6, "0"));

describe("getSelectionScope — 백엔드 판정 미러", () => {
  it("지정 종목이 없으면 유니버스 전략이다", () => {
    expect(getSelectionScope(base)).toBe("UNIVERSE");
  });

  it("사용자가 지목한 종목은 랭킹이 있어도 지정이다", () => {
    expect(
      getSelectionScope({
        ...base,
        target_symbols: ["005930", "000660"],
        ranking_metric: "return",
      }),
    ).toBe("EXPLICIT");
  });

  it("테마 유래여도 선정 기준이 없으면 지정이다(임의 절단 금지)", () => {
    expect(
      getSelectionScope({
        ...base,
        target_symbols: themeSymbols,
        theme_universe: "이차전지",
      }),
    ).toBe("EXPLICIT");
  });

  it("테마 유래 + 랭킹이면 고를 대상이다", () => {
    expect(
      getSelectionScope({
        ...base,
        target_symbols: themeSymbols,
        theme_universe: "이차전지",
        ranking_metric: "return",
      }),
    ).toBe("CANDIDATE_POOL");
  });
});

describe("getPositionLabel — 배지가 실제 실행과 일치해야 한다", () => {
  it("[회귀] 테마 후보군에서 선정하는 전략을 '지정 36개 균등'으로 표시하지 않는다", () => {
    // 엔진은 랭킹으로 10개만 산다 — 배지가 36개 균등이라고 하면 화면이 거짓말을 한다.
    expect(
      getPositionLabel({
        ...base,
        target_symbols: themeSymbols,
        theme_universe: "이차전지",
        ranking_metric: "return",
      }),
    ).toBe("최대 10종목");
  });

  it("사용자 지목 종목은 그대로 집중 투자 문구를 유지한다", () => {
    expect(getPositionLabel({ ...base, target_symbols: ["005930"] })).toBe(
      "단일 종목 집중 투자",
    );
    expect(getPositionLabel({ ...base, target_symbols: ["005930", "000660"] })).toBe(
      "지정 종목 2개 균등 투자",
    );
  });

  it("선정 기준 없는 테마는 기존 문구 그대로다", () => {
    expect(
      getPositionLabel({
        ...base,
        target_symbols: themeSymbols,
        theme_universe: "이차전지",
      }),
    ).toBe("지정 종목 36개 균등 투자");
  });
});
