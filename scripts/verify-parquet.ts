import { DataCache } from "../lib/strategy/pipeline/DataCache";
import { StrategyDataset } from "../types/strategy";

async function testParquetStorage() {
  const cache = new DataCache();
  const symbol = "TEST_STOCK";
  
  const mockDataset: StrategyDataset = {
    symbol,
    dates: ["2024-01-01", "2024-01-02"],
    prices: {
      open: [100, 101],
      high: [105, 106],
      low: [95, 96],
      close: [102, 103],
      volume: [1000, 1100],
    },
    features: {},
  };

  console.log(`Setting mock data for ${symbol}...`);
  await cache.set(symbol, mockDataset);

  console.log(`Retrieving data for ${symbol}...`);
  const retrieved = await cache.get(symbol, "full");

  if (retrieved && retrieved.symbol === symbol && retrieved.dates.length === 2) {
    console.log("PASS: Data retrieved correctly from Parquet.");
    console.log("Retrieved Close Prices:", retrieved.prices.close);
  } else {
    console.log("FAIL: Data retrieval failed or mismatched.");
  }
}

testParquetStorage().catch(console.error);
