import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import StockSearchModal from "@/components/stock/StockSearchModal";

const metadata = {
  "488080": { name: "TIGER 반도체TOP10레버리지", sector: "ETF" },
  "005930": { name: "삼성전자", sector: "전기전자" },
  "035720": { name: "카카오", sector: "서비스업" },
};

const universes = {
  kospi: ["005930"],
  kosdaq: ["035720"],
  kospi200: ["005930"],
};

function mockUniverseFetch() {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    if (String(input) === "/api/stocks/names") {
      return Promise.resolve({ ok: true, json: async () => metadata } as Response);
    }
    if (String(input) === "/api/universe/data") {
      return Promise.resolve({ ok: true, json: async () => ({ universes }) } as Response);
    }
    return Promise.reject(new Error(`Unexpected request: ${String(input)}`));
  }));
}

describe("StockSearchModal universe filtering", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    ["etf", "ETF", "TIGER 반도체TOP10레버리지", ["삼성전자", "카카오"]],
    ["kospi", "KOSPI", "삼성전자", ["TIGER 반도체TOP10레버리지", "카카오"]],
    ["kosdaq", "KOSDAQ", "카카오", ["TIGER 반도체TOP10레버리지", "삼성전자"]],
    ["kospi200", "KOSPI200", "삼성전자", ["TIGER 반도체TOP10레버리지", "카카오"]],
  ])("%s 유니버스 종목만 표시한다", async (universeId, label, visibleName, hiddenNames) => {
    mockUniverseFetch();

    render(
      <StockSearchModal
        isOpen
        onClose={vi.fn()}
        onSelect={vi.fn()}
        universeId={universeId}
      />
    );

    expect(screen.getByPlaceholderText(`${label} 유니버스 종목만 검색됩니다`)).toBeInTheDocument();
    expect(await screen.findByText(visibleName)).toBeInTheDocument();
    for (const hiddenName of hiddenNames) {
      expect(screen.queryByText(hiddenName)).not.toBeInTheDocument();
    }
  });

  it("제한된 유니버스 밖의 종목은 검색해도 표시하지 않는다", async () => {
    mockUniverseFetch();

    render(
      <StockSearchModal
        isOpen
        onClose={vi.fn()}
        onSelect={vi.fn()}
        universeId="ETF"
      />
    );

    const input = screen.getByPlaceholderText("ETF 유니버스 종목만 검색됩니다");
    await screen.findByText("TIGER 반도체TOP10레버리지");
    fireEvent.change(input, { target: { value: "삼성전자" } });

    await waitFor(() => {
      expect(screen.getByText("검색 결과가 없습니다")).toBeInTheDocument();
    });
    expect(screen.queryByText("삼성전자")).not.toBeInTheDocument();
  });
});
