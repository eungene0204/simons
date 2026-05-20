"use client";

import { ArrowClockwise, Warning } from "phosphor-react";

import { useStockNews } from "@/lib/hooks/useStockNews";
import type { ImpactLevel, NewsItemV2, NewsStatus, Sentiment } from "@/types/news-v2";

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return "방금";
    if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
    return `${Math.floor(diff / 86400)}일 전`;
  } catch {
    return "";
  }
}

function SentimentBadge({ sentiment, score }: { sentiment?: Sentiment | null; score?: number | null }) {
  if (!sentiment) return null;
  const cfg = sentiment === "positive"
    ? "text-[var(--main-red)] border-[var(--main-red)]/30"
    : sentiment === "negative"
      ? "text-[var(--main-blue)] border-[var(--main-blue)]/30"
      : "text-green-400 border-green-400/30";
  const label = sentiment === "positive" ? "긍정" : sentiment === "negative" ? "부정" : "중립";
  const display = typeof score === "number" ? `${label} ${(score * 100).toFixed(0)}%` : label;
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md border ${cfg}`}>
      {display}
    </span>
  );
}

function ImpactBadge({ level }: { level?: ImpactLevel | null }) {
  if (!level || level === "low") return null;
  const cfg = level === "high"
    ? "bg-red-500/10 text-red-400"
    : "bg-amber-500/10 text-amber-400";
  const label = level === "high" ? "고영향" : "중영향";
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md ${cfg}`}>
      <Warning size={10} weight="fill" />
      {label}
    </span>
  );
}

function ImpactStripe({ sentiment }: { sentiment?: Sentiment | null }) {
  const cls = sentiment === "positive"
    ? "bg-[var(--main-red)]"
    : sentiment === "negative"
      ? "bg-[var(--main-blue)]"
      : "bg-green-500/50";
  return <div className={`w-1 shrink-0 ${cls}`} />;
}

function SkeletonList() {
  return (
    <div className="space-y-2">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 animate-pulse">
          <div className="h-3 bg-white/[0.04] rounded w-1/4 mb-2 ml-auto" />
          <div className="h-4 bg-white/[0.04] rounded w-4/5 mb-1.5" />
          <div className="h-4 bg-white/[0.04] rounded w-3/5 mb-2" />
          <div className="flex gap-2">
            <div className="h-5 bg-white/[0.06] rounded-md w-16" />
            <div className="h-5 bg-white/[0.06] rounded-md w-20" />
          </div>
        </div>
      ))}
    </div>
  );
}

function StatusBanner({ status, message }: { status: NewsStatus; message?: string | null }) {
  if (status === "COLLECTING" || status === "NOT_COLLECTED") {
    return (
      <div className="rounded-xl border border-amber-400/20 bg-amber-400/[0.04] p-4 text-center">
        <p className="text-sm text-amber-300 mb-1">
          <span className="inline-block w-2 h-2 bg-amber-400 rounded-full animate-pulse mr-2" />
          {message ?? "뉴스를 수집하고 있습니다."}
        </p>
        <p className="text-xs text-gray-500">수 초 안에 자동으로 갱신됩니다.</p>
      </div>
    );
  }
  if (status === "NO_NEWS_FOUND") {
    return (
      <div className="py-10 text-center">
        <p className="text-sm text-gray-500">최근 뉴스가 없습니다.</p>
      </div>
    );
  }
  if (status === "FAILED") {
    return (
      <div className="rounded-xl border border-red-500/20 bg-red-500/[0.04] p-4 text-center">
        <p className="text-sm text-red-400">{message ?? "뉴스 수집에 실패했습니다."}</p>
      </div>
    );
  }
  return null;
}

function ArticleCard({ article }: { article: NewsItemV2 }) {
  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flat-card rounded-2xl border border-white/[0.08] overflow-hidden flex hover:border-white/[0.14] transition-colors"
    >
      <ImpactStripe sentiment={article.sentiment} />
      <div className="flex-1 min-w-0 p-5">
        <p className="text-sm font-bold text-gray-200 leading-snug mb-1.5">
          {article.title}
        </p>
        {article.ai_summary && (
          <p className="text-xs text-gray-400 leading-snug mb-2 line-clamp-2">
            {article.ai_summary}
          </p>
        )}
        <div className="flex items-center gap-2">
          <p className="text-xs text-gray-500 truncate min-w-0 flex-1">
            {article.source} · {timeAgo(article.published_at)}
          </p>
          <div className="flex items-center gap-1.5 shrink-0">
            <SentimentBadge sentiment={article.sentiment} score={article.sentiment_score} />
            <ImpactBadge level={article.impact_level} />
          </div>
        </div>
      </div>
    </a>
  );
}

export default function NewsImpactPanel({ symbol }: { symbol: string }) {
  const { data, status, isLoading, isRevalidating, refresh } = useStockNews(symbol);

  if (isLoading && !data?.items?.length) {
    return <SkeletonList />;
  }

  const items = data?.items ?? [];
  const headerStale = data?.stale ?? false;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {data?.fetched_at && (
            <span className="text-xs text-gray-500">
              마지막 업데이트: {timeAgo(data.fetched_at)}
            </span>
          )}
          {(isRevalidating || headerStale) && (
            <span className="text-xs text-amber-400 animate-pulse">
              {headerStale ? "최신 뉴스 확인 중..." : "갱신 중..."}
            </span>
          )}
        </div>
        <button
          onClick={() => refresh()}
          disabled={isRevalidating}
          className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-40"
        >
          <ArrowClockwise size={13} weight="bold" className={isRevalidating ? "animate-spin" : ""} />
          새로고침
        </button>
      </div>

      {status && status !== "READY" && status !== "STALE" && items.length === 0 ? (
        <StatusBanner status={status} message={data?.message} />
      ) : null}

      {items.length > 0 ? (
        <div className="space-y-2">
          {items.map((article) => (
            <ArticleCard key={article.id} article={article} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
