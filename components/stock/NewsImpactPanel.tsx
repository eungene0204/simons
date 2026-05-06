"use client";

import { useCallback, useEffect, useState } from "react";
import { Warning } from "phosphor-react";


interface NewsItem {
  id: string;
  title: string;
  summary?: string;
  body?: string;
  url: string;
  source: string;
  published_at: string;
  category?: string;
  symbols: string[];
  scope?: string;
  sector?: string;
  event_type?: string;
  sentiment?: string;
  severity?: number;
  credibility?: number;
  risk_flags: string[];
  impact_direction?: string;
  impact_score?: number;
  confidence_score?: number;
  risk_alert_level?: string;
  expected_alpha_1d?: number;
}


const RISK_FLAG_LABELS: Record<string, string> = {
  delisting_risk: "상장폐지",
  accounting_fraud: "회계부정",
  liquidity_crisis: "유동성위기",
  legal_dispute: "법적분쟁",
  regulatory_investigation: "규제조사",
  management_instability: "경영불안",
  operational_disruption: "운영중단",
  dilution_risk: "희석위험",
};

function _timeAgo(iso: string): string {
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

function ImpactBadge({ direction, score }: { direction?: string; score?: number }) {
  const isUp = direction === "up";
  const isDown = direction === "down";
  const magnitude = score ? Math.abs(score) : 0;
  const label = isUp
    ? magnitude > 0.5 ? "강한 상승" : "상승"
    : isDown
      ? magnitude > 0.5 ? "강한 하락" : "하락"
      : "중립";

  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md bg-[var(--main-red)]/10 border border-white/20 ${
      isUp ? "text-[var(--main-red)]" : isDown ? "text-[var(--main-blue)]" : "text-green-400"
    }`}>
      {label}
    </span>
  );
}

function RiskBadge({ level }: { level?: string }) {
  if (!level || level === "none") return null;

  const cfg = {
    high: "bg-red-500/10 text-red-400",
    medium: "bg-amber-500/10 text-amber-400",
    low: "bg-yellow-500/10 text-yellow-400",
  }[level] ?? "bg-white/[0.06] text-gray-400";

  const label = level === "high" ? "고위험" : level === "medium" ? "중위험" : "저위험";

  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md ${cfg}`}>
      <Warning size={10} weight="fill" />
      {label}
    </span>
  );
}

export default function NewsImpactPanel({ symbol }: { symbol: string }) {
  const [articles, setArticles] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // 기존 뉴스 먼저 조회
      const existing = await fetch(`/api/news/symbol/${symbol}?page_size=10`);
      if (existing.ok) {
        const data = await existing.json();
        if ((data.items ?? []).length > 0) {
          setArticles(data.items);
          return;
        }
      }
      // 뉴스 없을 때만 수집
      await fetch('/api/news/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbols: [symbol], max_per_provider: 30 }),
        cache: 'no-store',
      });
      const url = `/api/news/symbol/${symbol}?page_size=10&as_of=${encodeURIComponent(new Date().toISOString())}`;
      const res = await fetch(url, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        setArticles(data.items ?? []);
      }
    } catch {
      // silent fail
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
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

  if (!articles.length) {
    return (
      <div className="pt-4">
        <div className="py-10 text-center">
          <p className="text-sm text-gray-500">분석된 뉴스가 없습니다</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {articles.map((article) => {
        const hasRisk = article.risk_alert_level && article.risk_alert_level !== "none";

        return (
          <a
            key={article.id}
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flat-card rounded-2xl border border-white/[0.08] overflow-hidden flex hover:border-white/[0.14] transition-colors"
          >
            {/* Left color bar */}
            <div className={`w-1 shrink-0 ${
              article.impact_direction === "up" ? "bg-[var(--main-red)]" :
              article.impact_direction === "down" ? "bg-[var(--main-blue)]" :
              "bg-green-500/50"
            }`} />

            <div className="flex-1 min-w-0 p-5">
              {/* Title */}
              <p className="text-sm font-bold text-gray-200 leading-snug mb-2">
                {article.title}
              </p>

              {/* Source · time + badges row */}
              <div className="flex items-center gap-2">
                <p className="text-xs text-gray-500 truncate min-w-0 flex-1">
                  {article.source} · {_timeAgo(article.published_at)}
                </p>
                <div className="flex items-center gap-1.5 shrink-0">
                  <ImpactBadge direction={article.impact_direction} score={article.impact_score} />
                  {hasRisk && <RiskBadge level={article.risk_alert_level} />}
                </div>
              </div>
            </div>
          </a>
        );
      })}
    </div>
  );
}
