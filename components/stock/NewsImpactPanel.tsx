"use client";

import { ArrowClockwise } from "phosphor-react";

import { useStockNews } from "@/lib/hooks/useStockNews";
import type { NewsItemV2, NewsStatus, Sentiment } from "@/types/news-v2";

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
    const diff = (Date.now() - new Date(timestamp).getTime()) / 1000;
    if (diff < 60) return "방금";
    if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
    return `${Math.floor(diff / 86400)}일 전`;
  } catch {
    return "";
  }
}

function normalizePreviewText(text: string | null | undefined): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

function stripTrailingSource(text: string, source: string): string {
  const normalizedSource = normalizePreviewText(source);
  const candidate = normalizePreviewText(text);
  if (!normalizedSource) return candidate;
  if (!candidate.endsWith(normalizedSource)) return candidate;
  return candidate.slice(0, -normalizedSource.length).replace(/[-:|/\s]+$/, "").trim();
}

function canonicalizePreviewText(text: string | null | undefined, source: string): string {
  return stripTrailingSource(normalizePreviewText(text), source)
    .replace(/[\s"'`.,:;!?()[\]{}<>|/-]+/g, "")
    .toLowerCase();
}

function getArticlePreview(article: NewsItemV2): string | null {
  const title = normalizePreviewText(article.title);
  const preview = stripTrailingSource(article.bodyPreview ?? article.summary ?? "", article.source);
  if (!preview) return null;
  if (canonicalizePreviewText(preview, article.source) === canonicalizePreviewText(title, article.source)) {
    return null;
  }
  if (title && preview.startsWith(title)) {
    const remainder = preview.slice(title.length).replace(/^[-:|/\s]+/, "").trim();
    if (!remainder) return null;
    if (canonicalizePreviewText(remainder, article.source) === canonicalizePreviewText(title, article.source)) {
      return null;
    }
    return remainder;
  }
  return preview;
}

function SentimentBadge({ sentiment }: { sentiment?: Sentiment | null }) {
  if (!sentiment) return null;
  const cfg = sentiment === "positive"
    ? "text-[var(--main-red)] border-white/[0.16]"
    : sentiment === "negative"
      ? "text-[var(--main-blue)] border-white/[0.16]"
      : "text-green-400 border-white/[0.16]";
  const label = sentiment === "positive" ? "긍정" : sentiment === "negative" ? "부정" : "중립";
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md border ${cfg}`}>
      {label}
    </span>
  );
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
      <div className="rounded-xl border border-amber-400/20 p-4 text-center">
        <p className="text-sm text-amber-300 mb-1">
          <span className="inline-block w-2 h-2 bg-amber-400 rounded-full animate-pulse mr-2" />
          {message ?? "최근 뉴스가 준비 중입니다."}
        </p>
        <p className="text-xs text-gray-500">준비된 캐시가 생기면 자동으로 표시됩니다.</p>
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
  const highImportance = article.importance === "high";
  const preview = getArticlePreview(article);
  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className={`flat-card rounded-2xl border overflow-hidden flex hover:border-white/[0.16] transition-colors ${
        highImportance ? "border-red-400/30 bg-red-500/[0.03]" : "border-white/[0.08]"
      }`}
    >
      <div className="flex-1 min-w-0 p-5">
        <p className="text-sm font-bold text-gray-200 leading-snug mb-1.5">
          {article.title}
        </p>
        {preview && (
          <p className="text-xs text-gray-400 leading-snug mb-2 line-clamp-2">
            {preview}
          </p>
        )}
        <div className="flex items-center gap-2">
          <p className="text-xs text-gray-500 truncate min-w-0 flex-1">
            {article.source} · {timeAgo(article.publishedAt)}
          </p>
          <div className="flex items-center gap-1.5 shrink-0">
            <SentimentBadge sentiment={article.sentiment} />
          </div>
        </div>
      </div>
    </a>
  );
}

export default function NewsImpactPanel({ symbol }: { symbol: string }) {
  const { data, status, isLoading, isRevalidating, error, refresh } = useStockNews(symbol);

  if (isLoading && !data?.items?.length) {
    return <SkeletonList />;
  }

  const items = data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {data?.lastUpdatedAt && (
            <span className="text-xs text-gray-500">
              마지막 업데이트: {timeAgo(data.lastUpdatedAt)}
            </span>
          )}
          {isRevalidating && (
            <span className="text-xs text-amber-400 animate-pulse">
              갱신 중...
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

      {error && items.length === 0 ? (
        <div className="rounded-xl border border-red-500/20 bg-red-500/[0.04] p-4 text-center">
          <p className="text-sm text-red-400">뉴스 캐시를 읽지 못했습니다.</p>
        </div>
      ) : null}

      {items.length > 0 ? (
        <div className="space-y-2">
          {items.map((article) => (
            <ArticleCard key={article.newsId} article={article} />
          ))}
        </div>
      ) : status === "READY" || status === "STALE" ? (
        <div className="py-10 text-center">
          <p className="text-sm text-gray-500">최근 뉴스가 없습니다.</p>
        </div>
      ) : null}
    </div>
  );
}
