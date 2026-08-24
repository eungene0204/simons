// quick-search route의 종목 매칭 로직 (route 파일은 표준 export만 허용되므로 형제 모듈로 분리)

import { scoreSmartMatch } from "@/lib/smart-search";
import type { StockListItem, UsStockListItem } from "@/types/stock";
import type { QuickSearchStockItem } from "@/types/quick-search";

interface ScoredStock {
  score: number;
  item: QuickSearchStockItem;
}

function scoreStock(
  query: string,
  stock: Pick<StockListItem | UsStockListItem, "symbol" | "name" | "market" | "sector" | "industry">,
  names: Array<string | undefined>,
  region: string,
  currency: string
): ScoredStock {
  const score =
    scoreSmartMatch(query, [stock.symbol]) * 5 +
    scoreSmartMatch(query, names) * 4 +
    scoreSmartMatch(query, [stock.market, stock.sector, stock.industry]);

  return {
    score,
    item: {
      symbol: stock.symbol,
      name: stock.name,
      type: stock.market,
      region,
      currency,
      matchScore: score,
      sector: stock.sector,
      industry: stock.industry,
    },
  };
}

/**
 * 한국·미국 종목 목록을 함께 매칭해 점수순으로 반환합니다.
 * region/currency는 목록별로 부여된다 (KR/KRW, US/USD — 거래 통화 기준).
 * 이름 매칭은 교차 언어 지원: 한국 종목은 영문명(name_en), 미국 종목은 한글명(name_kr)도 본다.
 */
export function matchStocks(
  query: string,
  krStocks: StockListItem[],
  usStocks: UsStockListItem[]
): QuickSearchStockItem[] {
  return [
    ...krStocks.map((stock) => scoreStock(query, stock, [stock.name, stock.name_en], "KR", "KRW")),
    ...usStocks.map((stock) => scoreStock(query, stock, [stock.name, stock.name_kr], "US", "USD")),
  ]
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.item);
}
