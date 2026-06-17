import { describe, expect, it } from "vitest";

import {
  resolveHoldingDisplayNames,
  resolveStockDisplayName,
  resolveTrackedDisplayNames,
} from "@/components/virtual-account/stockDisplayNames";
import type { PortfolioHolding } from "@/types/portfolio";

describe("virtual account stock display names", () => {
  const stockMetadata = {
    "001755": { name: "한양증권우", sector: "증권" },
    "019175": { name: "신풍제약우", sector: "제약" },
  };

  it("resolves preferred stock names from stock metadata when the current name is only a code", () => {
    expect(resolveStockDisplayName("001755", "001755", stockMetadata)).toBe(
      "한양증권우"
    );
    expect(resolveStockDisplayName("019175", undefined, stockMetadata)).toBe(
      "신풍제약우"
    );
  });

  it("keeps existing names when metadata does not include the symbol", () => {
    expect(resolveStockDisplayName("005930", "삼성전자", stockMetadata)).toBe(
      "삼성전자"
    );
  });

  it("applies preferred stock names to holdings and tracked symbols", () => {
    const holdings: PortfolioHolding[] = [
      {
        symbol: "001755",
        name: "001755",
        quantity: 1,
        averagePrice: 10000,
        currentPrice: 11000,
        totalValue: 11000,
        profit: 1000,
        profitPercent: 10,
      },
    ];
    const trackedSymbols = [{ symbol: "019175", name: "019175" }];

    expect(resolveHoldingDisplayNames(holdings, stockMetadata)[0].name).toBe(
      "한양증권우"
    );
    expect(resolveTrackedDisplayNames(trackedSymbols, stockMetadata)[0].name).toBe(
      "신풍제약우"
    );
  });
});
