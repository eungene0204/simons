import type { PortfolioHolding } from "@/types/portfolio";

export type StockMetadataMap = Record<
  string,
  | string
  | {
      name?: string | null;
    }
  | undefined
>;

function getMetadataName(symbol: string, stockMetadata: StockMetadataMap) {
  const metadata = stockMetadata[symbol];
  const metadataName =
    typeof metadata === "string" ? metadata : metadata?.name ?? "";
  return metadataName.trim();
}

function resolvePreferredStockName(
  symbol: string,
  stockMetadata: StockMetadataMap
) {
  if (!/^\d{6}$/.test(symbol) || !symbol.endsWith("5")) {
    return "";
  }

  const commonStockSymbol = `${symbol.slice(0, 5)}0`;
  const commonStockName = getMetadataName(commonStockSymbol, stockMetadata);
  return commonStockName ? `${commonStockName}우` : "";
}

export function resolveStockDisplayName(
  symbol: string,
  currentName: string | null | undefined,
  stockMetadata: StockMetadataMap
) {
  const trimmedMetadataName = getMetadataName(symbol, stockMetadata);

  if (trimmedMetadataName) return trimmedMetadataName;

  const preferredStockName = resolvePreferredStockName(symbol, stockMetadata);
  if (preferredStockName) return preferredStockName;

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
