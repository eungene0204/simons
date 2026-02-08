import { NextResponse } from "next/server";
import { loadStockList } from "@/lib/krx-stocks";

export async function GET() {
  try {
    const stocks = await loadStockList();
    const symbolToSector: Record<string, string> = {};
    const universes: Record<string, string[]> = {
      kospi: [],
      kosdaq: [],
      kospi200: [
        "005930", "000660", "373220", "207940", "005380", 
        "000270", "068270", "005490", "051910", "003670",
        "035420", "035720", "105560", "055550", "034730",
        "017670", "011200", "010130", "009150", "012330",
        "096770", "078930", "267250", "005090", "006400",
        "011070", "000810", "033780", "003550", "010950",
        "018260", "032640", "010140", "000100", "004020",
        "000080", "001450", "005940", "005830", "006800",
        "000720", "008770", "004990", "015760", "024110",
        "000120", "009540", "010120", "034220", "004170",
        "001040", "036570", "035250", "012450", "009830",
        "003470", "001060", "020150", "021240", "028260",
        "071050", "001740", "002380", "003490", "011170",
        "012750", "023530", "028050", "030000", "030200",
        "034020", "051900", "069500", "069620", "078935",
        "086280", "086790", "090430", "093370", "096775",
        "103140", "128940", "138040", "138930", "139480"
      ]
    };

    stocks.forEach(stock => {
      if (stock.sector) {
        symbolToSector[stock.symbol] = stock.sector;
      }
      
      if (stock.market === "KOSPI") {
        universes.kospi.push(stock.symbol);
      } else if (stock.market === "KOSDAQ") {
        universes.kosdaq.push(stock.symbol);
      }
    });

    return NextResponse.json({
      symbolToSector,
      universes
    });
  } catch (error) {
    console.error("Failed to load universe data:", error);
    return NextResponse.json({ error: "Failed to load universe data" }, { status: 500 });
  }
}
