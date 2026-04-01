export interface DashboardBacktestRecord {
  id: string;
  timestamp: number;
  strategyName: string;
  universe: string;
  metrics: {
    totalReturn?: number;
    cagr?: number;
    sharpe?: number;
    mdd?: number;
    score?: number;
    startDate?: string;
    endDate?: string;
    trades?: number;
  };
}

export interface MarketSnapshotItem {
  symbol: string;
  name: string;
  value: number;
  change: number;
  changePercent: number;
}
