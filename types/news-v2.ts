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
export type Importance = "low" | "medium" | "high";

export interface NewsItemV2 {
  newsId: string;
  title: string;
  url: string;
  source: string;
  publishedAt: string;
  summary?: string | null;
  bodyPreview?: string | null;
  sentiment?: Sentiment | null;
  impactScore: number;
  importance: Importance;
}

export interface NewsResponseV2 {
  symbol: string;
  items: NewsItemV2[];
  lastUpdatedAt?: string | null;
  isStale: boolean;
  status: NewsStatus;
  source: NewsSource;
  message?: string | null;
}

export interface NewsStatusV2 {
  symbol: string;
  status: NewsStatus;
  last_success_at?: string | null;
  last_attempt_at?: string | null;
  attempt_count: number;
}
