import { describe, expect, it } from "vitest";
import {
  backtestPeriodTooShort,
  isBacktestConfirmation,
  isBacktestPrompt,
} from "./backtestConfirmation";

describe("isBacktestPrompt", () => {
  it("detects the proceed-with-backtest confirmation question", () => {
    expect(
      isBacktestPrompt(
        "전략이 아직 완전히 구성되지는 않았습니다.\n\n손절, 익절, 청산 조건이 비어 있지만 현재 상태로도 백테스트를 실행할 수 있습니다.\n\n먼저 결과를 확인해 보고, 필요하면 나중에 조건을 추가해 보세요.\n\n백테스트를 시작할까요?",
      ),
    ).toBe(true);
  });

  it("detects the valid-strategy completion message", () => {
    expect(
      isBacktestPrompt("전략 정의가 완료되었습니다. 백테스트를 실행할 수 있습니다."),
    ).toBe(true);
  });

  it("detects the coach-failed fallback that still offers a backtest", () => {
    expect(
      isBacktestPrompt(
        "전략 검증 결과를 가져오지 못했습니다. 전략 요약은 준비되어 있으니 백테스트는 계속 실행할 수 있습니다.",
      ),
    ).toBe(true);
  });

  it("does not match a greeting that merely mentions backtesting", () => {
    expect(isBacktestPrompt("반갑습니다. 백테스트해 보고 싶은 전략이 있으신가요?")).toBe(false);
  });

  it("handles null/empty", () => {
    expect(isBacktestPrompt(null)).toBe(false);
    expect(isBacktestPrompt("")).toBe(false);
  });
});

describe("isBacktestConfirmation", () => {
  it.each(["네", "넵", "네네", "예", "응", "ㅇㅇ", "좋아요", "좋습니다", "확인", "그래", "콜", "ok", "yes", "고"])(
    "treats %s as confirmation",
    (text) => {
      expect(isBacktestConfirmation(text)).toBe(true);
    },
  );

  it("accepts affirmatives with punctuation", () => {
    expect(isBacktestConfirmation("네!")).toBe(true);
    expect(isBacktestConfirmation("넵.")).toBe(true);
    expect(isBacktestConfirmation("네~")).toBe(true);
  });

  it.each(["진행해줘", "백테스트 실행해줘", "지금 돌려주세요", "네 진행해주세요"])(
    "treats explicit run request %s as confirmation",
    (text) => {
      expect(isBacktestConfirmation(text)).toBe(true);
    },
  );

  it("does not treat strategy modifications as confirmation", () => {
    expect(isBacktestConfirmation("손절을 -10%로 바꿔줘")).toBe(false);
    expect(isBacktestConfirmation("PBR 0.5 이하로 바꿔주세요")).toBe(false);
    expect(isBacktestConfirmation("종목 수를 10개로 늘려줘")).toBe(false);
  });

  it.each(["백테스트 1주일로 해줘", "백테스트 3년으로 해줘", "백테스트 6개월로 돌려줘"])(
    "does not treat a period-bearing message %s as confirmation (must reparse)",
    (text) => {
      expect(isBacktestConfirmation(text)).toBe(false);
    },
  );


  it("does not treat a negative reply as confirmation", () => {
    expect(isBacktestConfirmation("아니요")).toBe(false);
    expect(isBacktestConfirmation("아니 익절도 넣어줘")).toBe(false);
  });

  it("handles empty input", () => {
    expect(isBacktestConfirmation("")).toBe(false);
    expect(isBacktestConfirmation("   ")).toBe(false);
  });
});

describe("backtestPeriodTooShort", () => {
  it.each([
    "백테스트 1주일로 해줘",
    "백테스트 2주로 해줘",
    "백테스트를 일주일로 돌려줘",
    "백테스트 기간을 10일로 해줘",
    "백테스트 30일로 해줘",
    "백테스트 6개월로 해줘",
    "백테스트 기간 한 달로 해줘",
    "백테스트 반년으로 해줘",
    "백테스트 며칠로만 해줘",
  ])("flags sub-1-year backtest period %s", (text) => {
    expect(backtestPeriodTooShort(text)).toBe(true);
  });

  it.each([
    "백테스트 1년으로 해줘",
    "백테스트 3년으로 해줘",
    "백테스트 12개월로 해줘",
    "백테스트 전체 기간으로 해줘",
    "백테스트 5년으로 돌려줘",
  ])("does not flag valid (>=1 year) period %s", (text) => {
    expect(backtestPeriodTooShort(text)).toBe(false);
  });

  it.each([
    "20일선 위에 있으면 매수",
    "한 번 사면 20일 보유 후 매도",
    "RSI 14일 기준으로 매수",
    "골든크로스 매수, 데드크로스 매도",
  ])("does not flag non-backtest duration mentions %s", (text) => {
    expect(backtestPeriodTooShort(text)).toBe(false);
  });
});
