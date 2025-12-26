// Stock Data Types

export interface StockQuote {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  marketCap?: number;
  high?: number;
  low?: number;
  open?: number;
  previousClose?: number;
  timestamp: Date;
}

export interface StockPrice {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  timestamp: Date;
}

export interface StockHistoricalData {
  symbol: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  adjustedClose?: number;
}

export interface StockSearchResult {
  symbol: string;
  name: string;
  type: string;
  region: string;
  currency: string;
  matchScore?: number;
  sector?: string;
  industry?: string;
}

export interface StockOverview {
  symbol: string;
  name: string;
  description?: string;
  sector?: string;
  industry?: string;
  marketCap?: number;
  peRatio?: number;
  pbr?: number;
  beta?: number;
  eps?: number;
  revenue?: number;
  profitMargin?: number;
}

export interface StockNews {
  id: string;
  title: string;
  summary: string;
  source: string;
  url: string;
  publishedAt: Date;
  imageUrl?: string;
}

export interface StockTimeSeries {
  symbol: string;
  interval: '1min' | '5min' | '15min' | '30min' | '60min' | 'daily' | 'weekly' | 'monthly';
  data: StockHistoricalData[];
}

export interface APIError {
  message: string;
  code?: string;
  statusCode?: number;
}


