import { describe, expect, it } from "vitest";
import { matchStocks } from "@/app/api/quick-search/stock-search";
import type { StockListItem, UsStockListItem } from "@/types/stock";

const KR_STOCKS: StockListItem[] = [
  { symbol: "005930", name: "삼성전자", market: "KOSPI", sector: "전기전자", industry: "반도체", name_en: "SamsungElec" },
  { symbol: "035420", name: "NAVER", market: "KOSPI", sector: "서비스업", industry: "인터넷" },
];

const US_STOCKS: UsStockListItem[] = [
  {
    symbol: "AAPL",
    name: "Apple Inc.",
    market: "NASDAQ",
    sector: "Information Technology",
    industry: "Technology Hardware, Storage & Peripherals",
    cik: "0000320193",
    financial_currency: "USD",
    name_kr: "애플",
  },
  {
    symbol: "AACG",
    name: "ATA Creativity Global",
    market: "NASDAQ",
    sector: "Consumer Staples",
    industry: "Education & Training Services",
    cik: "0001420529",
    financial_currency: "CNY", // ADR — 재무 통화가 CNY여도 거래 통화는 USD
  },
];

describe("quick-search 종목 매칭 (KR+US 병합)", () => {
  it("한국 종목은 region KR / currency KRW로 매칭된다", () => {
    const results = matchStocks("삼성전자", KR_STOCKS, US_STOCKS);
    expect(results[0]).toMatchObject({
      symbol: "005930",
      region: "KR",
      currency: "KRW",
      type: "KOSPI",
    });
  });

  it("미국 티커는 소문자 입력도 매칭된다", () => {
    const results = matchStocks("aapl", KR_STOCKS, US_STOCKS);
    expect(results[0]).toMatchObject({
      symbol: "AAPL",
      name: "Apple Inc.",
      region: "US",
      currency: "USD",
      type: "NASDAQ",
    });
  });

  it("미국 종목은 영문명으로도 매칭된다", () => {
    const results = matchStocks("apple", KR_STOCKS, US_STOCKS);
    expect(results.map((r) => r.symbol)).toContain("AAPL");
  });

  it("미국 종목은 한글명(name_kr)으로도 검색된다", () => {
    const results = matchStocks("애플", KR_STOCKS, US_STOCKS);
    expect(results[0]).toMatchObject({ symbol: "AAPL", region: "US" });
  });

  it("한국 종목은 영문명(name_en)으로도 검색된다", () => {
    const results = matchStocks("samsung", KR_STOCKS, US_STOCKS);
    expect(results[0]).toMatchObject({ symbol: "005930", region: "KR" });
  });

  it("한글명 초성 검색도 동작한다", () => {
    const results = matchStocks("ㅇㅍ", KR_STOCKS, US_STOCKS);
    expect(results.map((r) => r.symbol)).toContain("AAPL");
  });

  it("재무 통화가 USD가 아닌 ADR도 거래 통화는 USD다", () => {
    const results = matchStocks("AACG", KR_STOCKS, US_STOCKS);
    expect(results[0]).toMatchObject({ symbol: "AACG", currency: "USD" });
  });

  it("점수순으로 정렬되어 정확 일치가 먼저 온다", () => {
    const results = matchStocks("naver", KR_STOCKS, US_STOCKS);
    expect(results[0]?.symbol).toBe("035420");
  });

  it("매칭이 없으면 빈 배열을 반환한다", () => {
    expect(matchStocks("존재하지않는종목", KR_STOCKS, US_STOCKS)).toEqual([]);
  });

  it("미국 목록이 비어 있어도(백필 미실행) 한국 검색은 동작한다", () => {
    const results = matchStocks("삼성전자", KR_STOCKS, []);
    expect(results[0]?.symbol).toBe("005930");
  });
});
