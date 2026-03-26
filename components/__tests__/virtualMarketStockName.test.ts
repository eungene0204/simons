// @ts-nocheck
/**
 * 가상시장 자동매매 시 종목명 조회 로직 회귀 테스트
 *
 * 버그 수정 이력:
 * - step/route.ts의 executeAutoTrade/executeAutoSell에서 포지션/주문 생성 시
 *   name 필드에 종목명 대신 종목코드가 저장되던 문제 수정 (name: symbol → name: getStockName(symbol))
 * - 수정 후: korea-stocks.json에서 종목명을 조회해 저장, 없을 경우 symbol 코드로 폴백
 */
import { describe, it, expect } from "vitest";
import koreaStocks from "@/data/korea-stocks.json";

// step/route.ts의 getStockName 로직 그대로 추출
const stockNameMap: Record<string, string> = Object.fromEntries(
  (koreaStocks as Array<{ symbol: string; name: string }>).map((s) => [s.symbol, s.name])
);

function getStockName(symbol: string): string {
  return stockNameMap[symbol] || symbol;
}

// ── 테스트 ──────────────────────────────────────────────────────────────────

describe("getStockName (virtual-market step)", () => {
  it("알려진 종목코드에 대해 한글 종목명을 반환해야 함", () => {
    expect(getStockName("005930")).toBe("삼성전자");
    expect(getStockName("000660")).toBe("SK하이닉스");
    expect(getStockName("035420")).toBe("NAVER");
  });

  it("버그 수정 대상 종목들이 올바른 이름을 반환해야 함 (이전엔 코드 자체가 저장됨)", () => {
    expect(getStockName("028050")).toBe("삼성E&A");
    expect(getStockName("034020")).toBe("두산에너빌리티");
    expect(getStockName("005380")).toBe("현대자동차");
    expect(getStockName("035720")).toBe("카카오");
  });

  it("반환값이 종목코드와 달라야 함 (name ≠ symbol 이 되어야 버그 수정 효과 있음)", () => {
    const knownSymbols = ["005930", "028050", "034020", "000660", "035420"];
    knownSymbols.forEach((symbol) => {
      expect(getStockName(symbol)).not.toBe(symbol);
    });
  });

  it("존재하지 않는 종목코드는 코드 자체를 폴백으로 반환해야 함", () => {
    expect(getStockName("999999")).toBe("999999");
    expect(getStockName("UNKNOWN")).toBe("UNKNOWN");
  });

  it("stockNameMap이 비어있지 않아야 함 (korea-stocks.json 로드 확인)", () => {
    expect(Object.keys(stockNameMap).length).toBeGreaterThan(100);
  });

  it("모든 맵 엔트리의 값이 비어있지 않아야 함", () => {
    Object.entries(stockNameMap).forEach(([symbol, name]) => {
      expect(name).toBeTruthy();
      expect(name).not.toBe("");
    });
  });
});
