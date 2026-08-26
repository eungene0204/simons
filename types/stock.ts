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

export interface StockListItem {
  symbol: string; // 종목 코드 (예: 005930)
  name: string; // 종목명 (예: 삼성전자)
  market: 'KOSPI' | 'KOSDAQ'; // 시장 구분
  sector?: string; // 섹터
  industry?: string; // 업종
  marketCap?: number; // 시가총액
  listedDate?: string; // 상장일
  name_en?: string; // 영문 종목명 (예: SamsungElec) — scripts/backfill_kr_stock_info.py로 백필
}

export interface UsStockListItem {
  symbol: string; // 티커 (예: AAPL)
  name: string; // 종목명 (예: Apple Inc.)
  market: string; // 거래소 (NYSE, NASDAQ, NYSE AMEX 등)
  sector?: string;
  industry?: string;
  cik?: string;
  financial_currency?: string; // 재무제표 통화 — 거래 통화(USD)와 다를 수 있음(ADR)
  name_kr?: string; // 한글 종목명 (예: 애플) — scripts/backfill_us_stock_info.py로 백필
  isin?: string;
  listed_date?: string; // 상장일 (YYYY-MM-DD)
  shares_outstanding?: number; // 발행주식수
}
