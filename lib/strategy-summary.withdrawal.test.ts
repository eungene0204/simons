import { describe, expect, it } from "vitest";

import { hasBuyCriteria, hasWithdrawalPlan } from "./strategy-summary";
import { buildReferenceRateRow } from "@/components/strategy/backtest/promptSummaryRows";

// 정기 인출(엔진 v16.33)과 결과 기준값 행의 프론트 계약.
// 인출만 말한 전략도 '지정 종목을 조건 없이 보유'가 매수 규칙이다 — 여기서 빠지면 실행 버튼이
// 열려 있는데도 빌더가 "매수 기준 없음"으로 처음부터 되묻는다(적립식 2026-09-22 사고의 거울).

const base = {
  universe: [],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 1,
  backtest_period: "5y",
  initial_capital: 10_000_000,
  rebalancing_period: "none",
} as unknown as Record<string, unknown>;

// 테스트 픽스처를 요약 모델로 좁히는 헬퍼(필드 전수 선언 없이 계약만 본다).
const parsed = (extra: Record<string, unknown>) =>
  ({ ...base, ...extra }) as unknown as Parameters<typeof hasWithdrawalPlan>[0];

describe("hasWithdrawalPlan", () => {
  it("인출액·주기·대상이 모두 있어야 인출 계획이다", () => {
    expect(
      hasWithdrawalPlan(
        parsed({
          withdrawal_amount: 2_000_000,
          withdrawal_period: "monthly",
          target_symbols: ["069500"],
        }),
      ),
    ).toBe(true);
  });

  it("반쪽 요청(주기 없음·대상 없음)은 인출 계획이 아니다", () => {
    expect(
      hasWithdrawalPlan(parsed({ withdrawal_amount: 2_000_000, target_symbols: ["069500"] })),
    ).toBe(false);
    expect(
      hasWithdrawalPlan(parsed({ withdrawal_amount: 2_000_000, withdrawal_period: "monthly" })),
    ).toBe(false);
  });

  it("인출 계획만 있어도 매수 기준으로 센다", () => {
    expect(
      hasBuyCriteria(
        parsed({
          withdrawal_amount: 2_000_000,
          withdrawal_period: "monthly",
          target_symbols: ["069500"],
        }),
      ),
    ).toBe(true);
  });
});

describe("buildReferenceRateRow", () => {
  it("기준 금리와 실질 수익률을 한 행으로 만든다", () => {
    const row = buildReferenceRateRow(
      { annualPct: 3.04, source: "market", series: "kr3m" },
      {
        totalPct: 13.7,
        annualPct: 3.27,
        realCagrPct: -0.1,
        series: "kr_cpi",
        label: "한국 소비자물가지수",
        from: "2021-12-31",
        to: "2025-12-31",
        windowTo: "2026-09-22",
        covered: false,
      },
    );
    expect(row).not.toBeNull();
    expect(row?.values.join(" ")).toContain("3.04%");
    expect(row?.values.join(" ")).toContain("-0.10%");
    // 물가 자료가 창 끝까지 닿지 않았다는 사실을 감추지 않는다.
    expect(row?.values.some((v) => v.includes("2025-12-31"))).toBe(true);
  });

  it("자료가 없으면 행을 만들지 않는다(구버전 저장 결과)", () => {
    expect(buildReferenceRateRow(null, null)).toBeNull();
    expect(buildReferenceRateRow({ annualPct: 0, source: "unavailable" }, null)).toBeNull();
  });
});
