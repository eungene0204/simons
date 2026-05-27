// 상장 상태 관리 — 프론트엔드 타입 및 규칙

export const ListingStatus = {
  NORMAL:               "NORMAL",
  WARNING:              "WARNING",
  RISK:                 "RISK",
  TRADING_SUSPENDED:    "TRADING_SUSPENDED",
  DELISTING_REVIEW:     "DELISTING_REVIEW",
  DELISTING_SCHEDULED:  "DELISTING_SCHEDULED",
  DELISTED:             "DELISTED",
} as const;

export type ListingStatusValue = (typeof ListingStatus)[keyof typeof ListingStatus];

export const DelistingPolicy = {
  AUTO_LIQUIDATE:       "AUTO_LIQUIDATE",
  HOLD_AS_WORTHLESS:    "HOLD_AS_WORTHLESS",
  HOLD_WITH_MANUAL_REVIEW: "HOLD_WITH_MANUAL_REVIEW",
} as const;

export type DelistingPolicyValue = (typeof DelistingPolicy)[keyof typeof DelistingPolicy];

// ── 거래 허용 규칙 ─────────────────────────────────────────────────────────────

const BUY_ALLOWED: Record<ListingStatusValue, boolean> = {
  NORMAL:               true,
  WARNING:              true,
  RISK:                 true,
  TRADING_SUSPENDED:    false,
  DELISTING_REVIEW:     false,
  DELISTING_SCHEDULED:  false,
  DELISTED:             false,
};

const SELL_ALLOWED: Record<ListingStatusValue, boolean> = {
  NORMAL:               true,
  WARNING:              true,
  RISK:                 true,
  TRADING_SUSPENDED:    false,
  DELISTING_REVIEW:     true,
  DELISTING_SCHEDULED:  true,
  DELISTED:             false,
};

export function isBuyAllowed(status: ListingStatusValue | string): boolean {
  return BUY_ALLOWED[status as ListingStatusValue] ?? false;
}

export function isSellAllowed(status: ListingStatusValue | string): boolean {
  return SELL_ALLOWED[status as ListingStatusValue] ?? false;
}

export function isZeroValuation(status: ListingStatusValue | string): boolean {
  return status === ListingStatus.DELISTED;
}

export function getTradeBlockReason(status: ListingStatusValue | string, side: "buy" | "sell"): string | null {
  if (side === "buy" && !isBuyAllowed(status)) {
    const msgs: Partial<Record<ListingStatusValue, string>> = {
      TRADING_SUSPENDED:   "매매거래정지 종목은 매수할 수 없습니다.",
      DELISTING_REVIEW:    "상장적격성 심사 중인 종목은 신규 매수가 불가합니다.",
      DELISTING_SCHEDULED: "상장폐지가 확정된 종목은 신규 매수가 불가합니다.",
      DELISTED:            "상장폐지 종목은 거래할 수 없습니다.",
    };
    return msgs[status as ListingStatusValue] ?? `현재 상태(${status})에서 매수할 수 없습니다.`;
  }
  if (side === "sell" && !isSellAllowed(status)) {
    const msgs: Partial<Record<ListingStatusValue, string>> = {
      TRADING_SUSPENDED: "매매거래정지 종목은 거래가 정지된 상태입니다.",
      DELISTED:          "상장폐지 종목은 거래할 수 없습니다.",
    };
    return msgs[status as ListingStatusValue] ?? `현재 상태(${status})에서 매도할 수 없습니다.`;
  }
  return null;
}

// ── UI 표현 ────────────────────────────────────────────────────────────────────

export type StatusBadgeVariant = "red" | "yellow" | "orange" | "blue" | null;

export function getStatusBadge(status: ListingStatusValue | string): {
  label: string;
  variant: StatusBadgeVariant;
} | null {
  switch (status) {
    case ListingStatus.DELISTED:
      return { label: "상장폐지", variant: "red" };
    case ListingStatus.DELISTING_SCHEDULED:
      return { label: "폐지예정", variant: "red" };
    case ListingStatus.TRADING_SUSPENDED:
      return { label: "거래정지", variant: "orange" };
    case ListingStatus.DELISTING_REVIEW:
      return { label: "심사중", variant: "orange" };
    case ListingStatus.WARNING:
      return { label: "폐지주의", variant: "yellow" };
    case ListingStatus.RISK:
      return { label: "위험", variant: "yellow" };
    default:
      return null;
  }
}

export function getStatusBadgeClasses(variant: StatusBadgeVariant): string {
  switch (variant) {
    case "red":
      return "bg-red-500/20 text-red-400 border border-red-500/30";
    case "orange":
      return "bg-orange-500/15 text-orange-400 border border-orange-500/25";
    case "yellow":
      return "bg-yellow-500/15 text-yellow-400 border border-yellow-500/25";
    default:
      return "";
  }
}

export function getRiskLevel(status: ListingStatusValue | string): "high" | "medium" | "low" | null {
  switch (status) {
    case ListingStatus.DELISTED:
    case ListingStatus.DELISTING_SCHEDULED:
    case ListingStatus.TRADING_SUSPENDED:
      return "high";
    case ListingStatus.DELISTING_REVIEW:
    case ListingStatus.RISK:
      return "medium";
    case ListingStatus.WARNING:
      return "low";
    default:
      return null;
  }
}

// ── 카운트다운 ─────────────────────────────────────────────────────────────────

export function daysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const target = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.ceil((target.getTime() - today.getTime()) / 86400000);
  return diff;
}
