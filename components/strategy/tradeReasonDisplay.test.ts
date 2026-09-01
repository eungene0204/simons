import { afterEach, describe, expect, it } from "vitest";
import { resolveTradeReasonDisplay } from "./legacyBreakout";
import { setLanguage, __resetLanguageForTests } from "@/lib/i18n";
import type { TradeReasonSegment } from "@/lib/trade-reason";

/**
 * 매매사유 표시 — 엔진이 준 구조화 사유(템플릿+인자)를 화면 언어로 렌더링한다.
 * 사고(2026-09-01): /us 거래 내역의 매매사유가 한국어로 나왔다(완성 문장이라 번역 불가).
 */
const formatKrw = (v: number) => `${Math.round(v).toLocaleString()}원`;
const formatUsd = (v: number) => `$${Math.round(v).toLocaleString()}`;

const breakoutAndVolume: TradeReasonSegment[] = [
  { t: "{0}일 신고가 돌파", a: [252] },
  { s: " + " },
  { t: "거래량 OBV 골든크로스" },
];

const stopLossWithPnl: TradeReasonSegment[] = [
  { t: "손절매 실행 (-{0}%)", a: [10] },
  { t: " [수익률: {0}%, 손실: {1}]", a: ["-12.01", 1013], m: [1] },
];

afterEach(() => {
  __resetLanguageForTests();
});

describe("resolveTradeReasonDisplay", () => {
  it("한국어에서는 종전 문장 그대로 보여준다", () => {
    setLanguage("ko");

    expect(resolveTradeReasonDisplay("", breakoutAndVolume, "buy", null, formatKrw)).toBe(
      "52주 신고가 돌파 + 거래량 OBV 골든크로스"
    );
    expect(resolveTradeReasonDisplay("", stopLossWithPnl, "sell", null, formatKrw)).toBe(
      "손절매 실행 (-10%) [수익률: -12.01%, 손실: 1,013원]"
    );
  });

  it("영어에서는 템플릿을 번역하고 금액도 달러로 찍는다", () => {
    setLanguage("en");

    expect(resolveTradeReasonDisplay("", breakoutAndVolume, "buy", null, formatUsd)).toBe(
      "52-week high breakout + Volume OBV golden cross"
    );
    expect(resolveTradeReasonDisplay("", stopLossWithPnl, "sell", null, formatUsd)).toBe(
      "Stop-loss executed (-10%) [Return: -12.01%, Loss: $1,013]"
    );
  });

  it("랭킹 매수 사유의 중첩 인자(방향·리밸런싱 주기)까지 번역한다", () => {
    setLanguage("en");
    const rankingReason: TradeReasonSegment[] = [
      {
        t: "최근 {0}거래일 수익률 {1} {2}%{3}",
        a: [60, { t: "상위" }, 10, { t: ", {0} 리밸런싱 상위 {1}종목 편입 대상", a: [{ t: "월간" }, 10] }],
      },
    ];

    expect(resolveTradeReasonDisplay("", rankingReason, "buy", null, formatUsd)).toBe(
      "Top 10% by return over the last 60 trading days, selected in the top 10 names on Monthly rebalancing"
    );
  });

  it("일반 매도 사유는 전략의 청산 조건 서술로 바꿔 보여준다", () => {
    setLanguage("en");
    const strategy = {
      exit: {
        conditions: [
          { type: "indicator", id: "breakout", params: { lookbackPeriod: 252, signalType: "sell" } },
        ],
      },
    } as never;
    const genericSell: TradeReasonSegment[] = [
      { t: "전략 매도 조건 충족" },
      { t: " [수익률: {0}%, 수익: {1}]", a: ["+8.20", 500], m: [1] },
    ];

    expect(resolveTradeReasonDisplay("", genericSell, "sell", strategy, formatUsd)).toBe(
      "52-week low breakout met [Return: +8.20%, Profit: $500]"
    );
  });

  it("파츠가 없는 구버전 결과는 백엔드 문장을 그대로 쓴다", () => {
    setLanguage("en");

    expect(resolveTradeReasonDisplay("52주 신고가 돌파", undefined, "buy", null, formatUsd)).toBe(
      "52주 신고가 돌파"
    );
  });
});
