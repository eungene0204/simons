import { describe, expect, it } from "vitest";

import { contributionStartCapital, totalContributed } from "./contributions";

const settings = (risk: object, mode = "single_asset") =>
  JSON.stringify({ backtest_mode: mode, risk });

describe("가상계좌 정액 적립식 계산", () => {
  it("수익률 분모는 초기 자본 + 누적 납입액이고, 납입이 없으면 초기 자본 그대로다", () => {
    expect(totalContributed("1000000", "500000")).toBe(1_500_000);
    expect(totalContributed(1_000_000, null)).toBe(1_000_000);
    expect(totalContributed(1_000_000, 0)).toBe(1_000_000);
  });

  it("적립식 전략은 전략의 초기 자본으로 시작하되 플랜 투자금을 넘지 않는다", () => {
    const plan = { contribution_amount: 500_000, contribution_period: "monthly" };
    expect(contributionStartCapital(settings({ ...plan, init_cash: 1_000_000 }), 10_000_000)).toBe(1_000_000);
    expect(contributionStartCapital(settings({ ...plan, init_cash: 50_000_000 }), 10_000_000)).toBe(10_000_000);
    expect(contributionStartCapital(settings(plan), 10_000_000)).toBe(10_000_000);
  });

  it("납입액·주기 중 하나라도 없거나 지정 종목 전략이 아니면 적립 계좌가 아니다", () => {
    expect(contributionStartCapital(settings({ contribution_amount: 500_000 }), 10_000_000)).toBeNull();
    expect(
      contributionStartCapital(
        settings({ contribution_amount: 500_000, contribution_period: "monthly" }, "universe"),
        10_000_000,
      ),
    ).toBeNull();
    expect(contributionStartCapital(settings({ init_cash: 1_000_000 }), 10_000_000)).toBeNull();
    expect(contributionStartCapital(null, 10_000_000)).toBeNull();
    expect(contributionStartCapital("{broken", 10_000_000)).toBeNull();
  });
});
