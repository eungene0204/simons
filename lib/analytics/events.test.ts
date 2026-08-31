import { afterEach, describe, expect, it, vi } from "vitest";
import { backtestRunParamsFromRequest, trackEvent } from "./events";

type GtagWindow = { gtag?: unknown };

afterEach(() => {
  delete (window as GtagWindow).gtag;
});

describe("trackEvent", () => {
  it("gtag가 있으면 ('event', 이벤트명, 파라미터)로 호출한다", () => {
    const gtag = vi.fn();
    (window as GtagWindow).gtag = gtag;

    trackEvent("sign_up", { method: "email" });

    expect(gtag).toHaveBeenCalledWith("event", "sign_up", { method: "email" });
  });

  it("gtag가 없으면(GA 미설정·스크립트 차단) 조용히 no-op한다", () => {
    expect(() => trackEvent("login", { method: "google" })).not.toThrow();
  });

  it("gtag가 함수가 아니면 호출하지 않는다", () => {
    (window as GtagWindow).gtag = "not-a-function";
    expect(() => trackEvent("login", { method: "email" })).not.toThrow();
  });

  it("gtag가 던져도 서비스 동작에 영향을 주지 않는다(삼킨다)", () => {
    (window as GtagWindow).gtag = () => {
      throw new Error("GA down");
    };
    expect(() =>
      trackEvent("purchase", {
        transaction_id: "txn_1",
        value: 49000,
        currency: "KRW",
        plan_name: "PREMIUM",
      })
    ).not.toThrow();
  });
});

describe("backtestRunParamsFromRequest", () => {
  it("KR 유니버스·상대 기간·심볼 수를 backtest_run 파라미터로 접는다", () => {
    expect(
      backtestRunParamsFromRequest({
        universe_id: "kospi200",
        rebalancing_period: "monthly",
        period: "5Y",
        symbols: ["005930", "000660"],
      })
    ).toEqual({
      strategy_name: "unnamed",
      market: "KOSPI",
      rebalance_period: "monthly",
      backtest_period: "5Y",
      stock_count: 2,
    });
  });

  it("명시 창(startDate~endDate)이 상대 기간보다 우선한다", () => {
    const params = backtestRunParamsFromRequest({
      universe_id: "kosdaq150",
      period: "5Y",
      startDate: "2020-01-01",
      endDate: "2024-12-31",
    });
    expect(params.market).toBe("KOSDAQ");
    expect(params.backtest_period).toBe("2020-01-01~2024-12-31");
    expect(params.stock_count).toBeUndefined();
  });

  it("거래소로 접히지 않는 US 유니버스는 id 대문자로 보낸다", () => {
    expect(backtestRunParamsFromRequest({ universe_id: "sp500" }).market).toBe("SP500");
    expect(backtestRunParamsFromRequest({ universe_id: "nasdaq100" }).market).toBe("NASDAQ");
  });

  it("리밸런싱·유니버스가 없으면 none/UNKNOWN으로 접는다(빈 요청도 안전)", () => {
    expect(backtestRunParamsFromRequest(null)).toEqual({
      strategy_name: "unnamed",
      market: "UNKNOWN",
      rebalance_period: "none",
      backtest_period: "unknown",
    });
  });
});
