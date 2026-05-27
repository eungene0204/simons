import { describe, it, expect } from "vitest";
import {
  ListingStatus,
  isBuyAllowed,
  isSellAllowed,
  isZeroValuation,
  getTradeBlockReason,
  getStatusBadge,
  getRiskLevel,
  daysUntil,
} from "@/lib/listing-status";

// ── 거래 허용 규칙 ─────────────────────────────────────────────────────────────

describe("isBuyAllowed", () => {
  it("allows buy for NORMAL", () => expect(isBuyAllowed("NORMAL")).toBe(true));
  it("allows buy for WARNING", () => expect(isBuyAllowed("WARNING")).toBe(true));
  it("allows buy for RISK", () => expect(isBuyAllowed("RISK")).toBe(true));
  it("blocks buy for TRADING_SUSPENDED", () => expect(isBuyAllowed("TRADING_SUSPENDED")).toBe(false));
  it("blocks buy for DELISTING_REVIEW", () => expect(isBuyAllowed("DELISTING_REVIEW")).toBe(false));
  it("blocks buy for DELISTING_SCHEDULED", () => expect(isBuyAllowed("DELISTING_SCHEDULED")).toBe(false));
  it("blocks buy for DELISTED", () => expect(isBuyAllowed("DELISTED")).toBe(false));
});

describe("isSellAllowed", () => {
  it("allows sell for NORMAL", () => expect(isSellAllowed("NORMAL")).toBe(true));
  it("blocks sell for TRADING_SUSPENDED", () => expect(isSellAllowed("TRADING_SUSPENDED")).toBe(false));
  it("allows sell for DELISTING_SCHEDULED (정리매매)", () => expect(isSellAllowed("DELISTING_SCHEDULED")).toBe(true));
  it("allows sell for DELISTING_REVIEW", () => expect(isSellAllowed("DELISTING_REVIEW")).toBe(true));
  it("blocks sell for DELISTED", () => expect(isSellAllowed("DELISTED")).toBe(false));
});

// ── 0원 평가 ───────────────────────────────────────────────────────────────────

describe("isZeroValuation", () => {
  it("DELISTED → 0원", () => expect(isZeroValuation("DELISTED")).toBe(true));
  it("DELISTING_SCHEDULED → not 0원", () => expect(isZeroValuation("DELISTING_SCHEDULED")).toBe(false));
  it("NORMAL → not 0원", () => expect(isZeroValuation("NORMAL")).toBe(false));
});

// ── 거래 차단 사유 ─────────────────────────────────────────────────────────────

describe("getTradeBlockReason", () => {
  it("NORMAL buy → null", () => expect(getTradeBlockReason("NORMAL", "buy")).toBeNull());
  it("TRADING_SUSPENDED buy → contains 매매거래정지", () => {
    expect(getTradeBlockReason("TRADING_SUSPENDED", "buy")).toContain("매매거래정지");
  });
  it("DELISTED buy → contains 상장폐지", () => {
    expect(getTradeBlockReason("DELISTED", "buy")).toContain("상장폐지");
  });
  it("TRADING_SUSPENDED sell → contains 거래", () => {
    expect(getTradeBlockReason("TRADING_SUSPENDED", "sell")).toContain("거래");
  });
  it("DELISTING_SCHEDULED sell → null (정리매매 허용)", () => {
    expect(getTradeBlockReason("DELISTING_SCHEDULED", "sell")).toBeNull();
  });
  it("DELISTED sell → contains 상장폐지", () => {
    expect(getTradeBlockReason("DELISTED", "sell")).toContain("상장폐지");
  });
});

// ── UI 배지 ────────────────────────────────────────────────────────────────────

describe("getStatusBadge", () => {
  it("DELISTED → red badge '상장폐지'", () => {
    const badge = getStatusBadge("DELISTED");
    expect(badge?.label).toBe("상장폐지");
    expect(badge?.variant).toBe("red");
  });
  it("TRADING_SUSPENDED → orange badge '거래정지'", () => {
    const badge = getStatusBadge("TRADING_SUSPENDED");
    expect(badge?.label).toBe("거래정지");
    expect(badge?.variant).toBe("orange");
  });
  it("WARNING → yellow badge", () => {
    const badge = getStatusBadge("WARNING");
    expect(badge?.variant).toBe("yellow");
  });
  it("NORMAL → null", () => expect(getStatusBadge("NORMAL")).toBeNull());
});

// ── 위험 레벨 ──────────────────────────────────────────────────────────────────

describe("getRiskLevel", () => {
  it("DELISTED → high", () => expect(getRiskLevel("DELISTED")).toBe("high"));
  it("DELISTING_SCHEDULED → high", () => expect(getRiskLevel("DELISTING_SCHEDULED")).toBe("high"));
  it("TRADING_SUSPENDED → high", () => expect(getRiskLevel("TRADING_SUSPENDED")).toBe("high"));
  it("DELISTING_REVIEW → medium", () => expect(getRiskLevel("DELISTING_REVIEW")).toBe("medium"));
  it("WARNING → low", () => expect(getRiskLevel("WARNING")).toBe("low"));
  it("NORMAL → null", () => expect(getRiskLevel("NORMAL")).toBeNull());
});

// ── 카운트다운 ─────────────────────────────────────────────────────────────────

describe("daysUntil", () => {
  it("null input → null", () => expect(daysUntil(null)).toBeNull());
  it("undefined input → null", () => expect(daysUntil(undefined)).toBeNull());
  it("past date → negative number", () => {
    expect(daysUntil("2020-01-01")).toBeLessThan(0);
  });
  it("far future date → positive number", () => {
    expect(daysUntil("2099-12-31")).toBeGreaterThan(0);
  });
});
