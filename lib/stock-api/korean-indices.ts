// Market Indices Provider (Mock Data Only)
import type { MarketIndex } from "@/types/market";

// Generate mock time series data for charts
export function generateMockTimeSeries(
  currentValue: number,
  days: number = 30
): Array<{ date: string; value: number }> {
  const data: Array<{ date: string; value: number }> = [];
  const today = new Date();

  // Generate data with some random variation
  let baseValue = currentValue * 0.95; // Start 5% lower

  for (let i = days; i >= 0; i--) {
    const date = new Date(today);
    date.setDate(date.getDate() - i);

    // Add some random variation (±2%)
    const variation = (Math.random() - 0.5) * 0.04;
    baseValue = baseValue * (1 + variation);

    // Gradually move towards current value
    const progress = (days - i) / days;
    const value = baseValue + (currentValue - baseValue) * progress;

    data.push({
      date: date.toISOString().split("T")[0],
      value: Math.round(value * 100) / 100,
    });
  }

  return data;
}

// Mock data for Korean indices
export function getMockKoreanIndices(): {
  kospi: MarketIndex;
  kosdaq: MarketIndex;
} {
  const now = new Date();

  return {
    kospi: {
      name: "코스피",
      symbol: "KOSPI",
      value: 2650.45,
      change: 15.23,
      changePercent: 0.58,
      volume: 850000000,
      high: 2665.12,
      low: 2635.89,
      open: 2638.5,
      previousClose: 2635.22,
      timestamp: now,
    },
    kosdaq: {
      name: "코스닥",
      symbol: "KOSDAQ",
      value: 890.12,
      change: -8.45,
      changePercent: -0.94,
      volume: 450000000,
      high: 905.67,
      low: 885.23,
      open: 898.56,
      previousClose: 898.57,
      timestamp: now,
    },
  };
}

// Mock data for US indices
export function getMockUSIndices(): {
  nasdaq: MarketIndex;
  dow: MarketIndex;
  sp500: MarketIndex;
} {
  const now = new Date();

  return {
    nasdaq: {
      name: "나스닥",
      symbol: "NASDAQ",
      value: 14689.52,
      change: 125.34,
      changePercent: 0.86,
      volume: 2500000000,
      high: 14720.15,
      low: 14580.3,
      open: 14605.2,
      previousClose: 14564.18,
      timestamp: now,
    },
    dow: {
      name: "다우지수",
      symbol: "DJI",
      value: 34567.89,
      change: 234.56,
      changePercent: 0.68,
      volume: 350000000,
      high: 34680.12,
      low: 34450.78,
      open: 34500.45,
      previousClose: 34333.33,
      timestamp: now,
    },
    sp500: {
      name: "S&P 500",
      symbol: "SPX",
      value: 4567.89,
      change: 45.67,
      changePercent: 1.01,
      volume: 4200000000,
      high: 4580.12,
      low: 4545.67,
      open: 4550.23,
      previousClose: 4522.22,
      timestamp: now,
    },
  };
}

// Mock data for VIX index
export function getMockVIX(): MarketIndex {
  const now = new Date();

  return {
    name: "VIX",
    symbol: "VIX",
    value: 18.45,
    change: -1.23,
    changePercent: -6.25,
    volume: 0, // VIX는 거래량이 없음
    high: 20.12,
    low: 17.89,
    open: 19.67,
    previousClose: 19.68,
    timestamp: now,
  };
}

// Mock exchange rate data (USD/KRW)
export function getMockExchangeRate(): MarketIndex {
  const now = new Date();
  const currentRate = 1350.5;
  const change = 5.3;
  const changePercent = 0.39;

  return {
    name: "USD/KRW",
    symbol: "USDKRW",
    value: currentRate,
    change: change,
    changePercent: changePercent,
    volume: 0, // 환율에는 거래량이 없음
    high: 1355.8,
    low: 1345.2,
    open: 1348.9,
    previousClose: 1345.2,
    timestamp: now,
  };
}

// Mock gold price data (Gold Spot, USD/oz)
export function getMockGoldPrice(): MarketIndex {
  const now = new Date();
  const currentPrice = 2045.5;
  const change = 12.3;
  const changePercent = 0.6;

  return {
    name: "금",
    symbol: "GOLD",
    value: currentPrice,
    change: change,
    changePercent: changePercent,
    volume: 0, // 금에는 거래량이 없음
    high: 2050.8,
    low: 2035.2,
    open: 2040.9,
    previousClose: 2033.2,
    timestamp: now,
  };
}

// Mock oil price data (WTI Crude Oil, USD/barrel)
export function getMockOilPrice(): MarketIndex {
  const now = new Date();
  const currentPrice = 78.45;
  const change = -1.2;
  const changePercent = -1.51;

  return {
    name: "석유",
    symbol: "WTI",
    value: currentPrice,
    change: change,
    changePercent: changePercent,
    volume: 0, // 석유에는 거래량이 없음
    high: 79.8,
    low: 77.9,
    open: 79.2,
    previousClose: 79.65,
    timestamp: now,
  };
}

// Mock silver price data (Silver, USD/oz)
export function getMockSilverPrice(): MarketIndex {
  const now = new Date();
  const currentPrice = 24.85;
  const change = 0.35;
  const changePercent = 1.43;

  return {
    name: "은",
    symbol: "SILVER",
    value: currentPrice,
    change: change,
    changePercent: changePercent,
    volume: 0,
    high: 25.12,
    low: 24.45,
    open: 24.67,
    previousClose: 24.5,
    timestamp: now,
  };
}

// Mock natural gas price data (Natural Gas, USD/MMBtu)
export function getMockNaturalGasPrice(): MarketIndex {
  const now = new Date();
  const currentPrice = 2.85;
  const change = -0.12;
  const changePercent = -4.04;

  return {
    name: "천연가스",
    symbol: "NG",
    value: currentPrice,
    change: change,
    changePercent: changePercent,
    volume: 0,
    high: 3.02,
    low: 2.78,
    open: 2.95,
    previousClose: 2.97,
    timestamp: now,
  };
}

// Mock copper price data (Copper, USD/lb)
export function getMockCopperPrice(): MarketIndex {
  const now = new Date();
  const currentPrice = 4.25;
  const change = 0.08;
  const changePercent = 1.92;

  return {
    name: "구리",
    symbol: "COPPER",
    value: currentPrice,
    change: change,
    changePercent: changePercent,
    volume: 0,
    high: 4.32,
    low: 4.15,
    open: 4.18,
    previousClose: 4.17,
    timestamp: now,
  };
}

// Mock wheat price data (Wheat, USD/bushel)
export function getMockWheatPrice(): MarketIndex {
  const now = new Date();
  const currentPrice = 6.45;
  const change = -0.15;
  const changePercent = -2.27;

  return {
    name: "밀",
    symbol: "WHEAT",
    value: currentPrice,
    change: change,
    changePercent: changePercent,
    volume: 0,
    high: 6.68,
    low: 6.32,
    open: 6.58,
    previousClose: 6.6,
    timestamp: now,
  };
}

// Mock data for Japanese indices
export function getMockJapaneseIndices(): {
  nikkei: MarketIndex;
  topix: MarketIndex;
} {
  const now = new Date();

  return {
    nikkei: {
      name: "니케이 225",
      symbol: "NIKKEI",
      value: 33850.45,
      change: 245.67,
      changePercent: 0.73,
      volume: 1200000000,
      high: 33950.12,
      low: 33650.89,
      open: 33750.5,
      previousClose: 33604.78,
      timestamp: now,
    },
    topix: {
      name: "TOPIX",
      symbol: "TOPIX",
      value: 2456.78,
      change: 18.45,
      changePercent: 0.76,
      volume: 1500000000,
      high: 2465.12,
      low: 2435.89,
      open: 2440.5,
      previousClose: 2438.33,
      timestamp: now,
    },
  };
}

// Mock data for Chinese indices
export function getMockChineseIndices(): {
  shanghai: MarketIndex;
  shenzhen: MarketIndex;
} {
  const now = new Date();

  return {
    shanghai: {
      name: "상해종합지수",
      symbol: "SSE",
      value: 3125.67,
      change: -15.23,
      changePercent: -0.48,
      volume: 2800000000,
      high: 3145.12,
      low: 3115.89,
      open: 3135.5,
      previousClose: 3140.9,
      timestamp: now,
    },
    shenzhen: {
      name: "심천종합지수",
      symbol: "SZSE",
      value: 1985.34,
      change: -8.45,
      changePercent: -0.42,
      volume: 2200000000,
      high: 2005.67,
      low: 1975.23,
      open: 1995.56,
      previousClose: 1993.79,
      timestamp: now,
    },
  };
}
