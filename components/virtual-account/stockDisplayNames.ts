import type { PortfolioHolding } from "@/types/portfolio";

export type StockMetadataMap = Record<
  string,
  | string
  | {
      name?: string | null;
    }
  | undefined
>;

export function resolveStockDisplayName(
  symbol: string,
  currentName: string | null | undefined,
  stockMetadata: StockMetadataMap
) {
  const metadata = stockMetadata[symbol];
  const metadataName =
    typeof metadata === "string" ? metadata : metadata?.name ?? "";
  const trimmedMetadataName = metadataName.trim();

  if (trimmedMetadataName) return trimmedMetadataName;

  const trimmedCurrentName = currentName?.trim() ?? "";
  if (trimmedCurrentName && trimmedCurrentName !== symbol) {
    return trimmedCurrentName;
  }

  return symbol;
}

export function resolveHoldingDisplayNames(
  holdings: PortfolioHolding[],
  stockMetadata: StockMetadataMap
): PortfolioHolding[] {
  return holdings.map((holding) => ({
    ...holding,
    name: resolveStockDisplayName(holding.symbol, holding.name, stockMetadata),
  }));
}

export function resolveTrackedDisplayNames(
  trackedSymbols: { symbol: string; name: string }[],
  stockMetadata: StockMetadataMap
) {
  return trackedSymbols.map((tracked) => ({
    ...tracked,
    name: resolveStockDisplayName(tracked.symbol, tracked.name, stockMetadata),
  }));
}
