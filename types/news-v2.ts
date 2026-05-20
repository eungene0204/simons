/**
 * Type definitions for the v2 news pipeline.
 * Mirrors backend/news_v2/api.py NewsResponseOut.
 */

export type NewsStatus =
  | "READY"
  | "STALE"
  | "COLLECTING"
  | "NOT_COLLECTED"
  | "NO_NEWS_FOUND"
  | "FAILED";

export type NewsSource = "redis" | "postgres" | "queue";
export type Sentiment = "positive" | "neutral" | "negative";
export type ImpactLevel = "low" | "medium" | "high";

export interface NewsItemV2 {
  id: number;
  title: string;
  summary?: string | null;
  source: string;
  url: string;
  published_at: string;
  sentiment?: Sentiment | null;
  sentiment_score?: number | null;
  impact_level?: ImpactLevel | null;
  market_effect?: string | null;
  related_symbols: string[];
  ai_summary?: string | null;
}

export interface NewsResponseV2 {
  status: NewsStatus;
  source: NewsSource;
  stale: boolean;
  items: NewsItemV2[];
  fetched_at?: string | null;
  message?: string | null;
}

export interface NewsStatusV2 {
  symbol: string;
  status: NewsStatus;
  last_success_at?: string | null;
  last_attempt_at?: string | null;
  attempt_count: number;
}
