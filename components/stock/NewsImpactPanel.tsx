"use client";

import { useEffect, useState } from "react";
import {
  Minus,
  Warning,
  ArrowSquareOut,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
} from "phosphor-react";

interface NewsItem {
  id: string;
  title: string;
  summary?: string;
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

interface ImpactSummary {
  symbol: string;
  risk_alert_level: string;
  latest_alpha?: {
    value: number;
    direction: string;
    confidence: number;
    event_type?: string;
    risk_alert?: string;
    article_title?: string;
  };
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  earnings_beat: "어닝 서프라이즈",
  earnings_miss: "어닝 쇼크",
  guidance_up: "가이던스 상향",
  guidance_down: "가이던스 하향",
  large_contract: "대규모 수주",
  share_buyback: "자사주 매입",
  rights_offering: "유상증자",
  convertible_bond: "전환사채",
  ceo_change: "CEO 교체",
  regulatory_probe: "규제 조사",
  lawsuit_loss: "소송 패소",
  lawsuit_win: "소송 승소",
  factory_fire: "공장 사고",
  product_launch: "신제품 출시",
  product_failure: "제품 결함",
  dividend_increase: "배당 증가",
  dividend_cut: "배당 삭감",
  mna: "M&A",
  delisting_risk: "상장폐지 위험",
  accounting_issue: "회계 이슈",
  analyst_upgrade: "목표가 상향",
  analyst_downgrade: "목표가 하향",
  macro_rate: "금리 변동",
  policy_change: "정책 변화",
  sector_tailwind: "업황 개선",
  sector_headwind: "업황 악화",
  general_positive: "긍정적",
  general_negative: "부정적",
  general_neutral: "중립",
};

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
  if (!direction || direction === "neutral") {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md bg-white/[0.06] text-gray-400">
        <Minus size={10} weight="bold" />
        중립
      </span>
    );
  }

  const isUp = direction === "up";
  const magnitude = score ? Math.abs(score) : 0;
  const label = isUp
    ? magnitude > 0.5 ? "강한 상승" : "상승"
    : magnitude > 0.5 ? "강한 하락" : "하락";

  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md ${
      isUp
        ? "bg-[var(--main-red)]/10 text-[var(--main-red)]"
        : "bg-[var(--main-blue)]/10 text-[var(--main-blue)]"
    }`}>
      {isUp
        ? <ArrowUpRight size={11} weight="bold" />
        : <ArrowDownRight size={11} weight="bold" />
      }
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

function OverallImpactCard({ impact }: { impact: ImpactSummary | null }) {
  if (!impact) return null;

  const alert = impact.risk_alert_level;
  const alpha = impact.latest_alpha;

  if (alert === "none" && !alpha) return null;

  const isPositive = alpha?.direction === "up";
  const isNegative = alpha?.direction === "down";

  return (
    <div className="mb-1 px-2 py-3 border-b border-white/[0.05]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
            임팩트 요약
          </span>
          {alert && alert !== "none" && <RiskBadge level={alert} />}
          {alpha && (
            <ImpactBadge direction={alpha.direction} score={alpha.value} />
          )}
          {alpha?.event_type && (
            <span className="text-xs font-bold text-gray-400">
              {EVENT_TYPE_LABELS[alpha.event_type] ?? alpha.event_type}
            </span>
          )}
        </div>
        {alpha?.confidence !== undefined && (
          <span className="text-xs font-bold tabular-nums font-outfit text-gray-500">
            신뢰도 {Math.round(alpha.confidence * 100)}%
          </span>
        )}
      </div>
      {alpha?.article_title && (
        <p className="text-xs text-gray-500 mt-1.5 truncate">{alpha.article_title}</p>
      )}
    </div>
  );
}

export default function NewsImpactPanel({ symbol }: { symbol: string }) {
  const [articles, setArticles] = useState<NewsItem[]>([]);
  const [impact, setImpact] = useState<ImpactSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      setLoading(true);
      try {
        const [newsRes, impactRes] = await Promise.allSettled([
          fetch(`/api/news/symbol/${symbol}?page_size=10`),
          fetch(`/api/news/impact/${symbol}`),
        ]);

        if (cancelled) return;

        if (newsRes.status === "fulfilled" && newsRes.value.ok) {
          const data = await newsRes.value.json();
          setArticles(data.items ?? []);
        }
        if (impactRes.status === "fulfilled" && impactRes.value.ok) {
          setImpact(await impactRes.value.json());
        }
      } catch {
        // Silently handle — backend may not be running
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchData();
    return () => { cancelled = true; };
  }, [symbol]);

  if (loading) {
    return (
      <div className="pt-4">
        <div className="border-b border-white/[0.05] mb-1" />
        <div className="space-y-0 divide-y divide-white/[0.04] mt-1">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="px-4 py-3 animate-pulse">
              <div className="h-3 bg-white/[0.04] rounded w-4/5 mb-2" />
              <div className="flex gap-2">
                <div className="h-4 bg-white/[0.04] rounded w-16" />
                <div className="h-4 bg-white/[0.04] rounded w-12" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!articles.length && !impact?.latest_alpha) {
    return (
      <div className="pt-4">
        <div className="px-4 pb-3 border-b border-white/[0.05]" />
        <div className="py-10 text-center">
          <p className="text-sm text-gray-500">분석된 뉴스가 없습니다</p>
          <p className="text-xs text-gray-600 mt-1">뉴스 수집 후 자동으로 분석됩니다</p>
        </div>
      </div>
    );
  }

  return (
    <div className="pt-4">
      {/* Panel header */}
      {articles.length > 0 && (
        <div className="px-2 pb-3 border-b border-white/[0.05] flex items-center justify-end">
          <span className="text-xs font-bold tabular-nums font-outfit text-gray-500">
            {articles.length}개 기사
          </span>
        </div>
      )}

      {/* Overall impact summary bar */}
      <OverallImpactCard impact={impact} />

      {/* Table header */}
      <div className="grid grid-cols-[minmax(0,1fr)_90px_72px_64px] gap-2 px-2 mb-2">
        {["제목", "이벤트", "임팩트", "시간"].map((h) => (
          <span key={h} className="text-xs font-bold uppercase tracking-widest text-gray-600">
            {h}
          </span>
        ))}
      </div>
      <div className="border-t border-white/[0.05] mb-1" />

      {/* Article rows */}
      <div className="divide-y divide-white/[0.04] overflow-y-auto max-h-[480px] [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
        {articles.map((article) => {
          const isExpanded = expanded === article.id;
          const hasRisk = article.risk_alert_level && article.risk_alert_level !== "none";

          return (
            <div key={article.id}>
              {/* Main row */}
              <div
                className="grid grid-cols-[minmax(0,1fr)_90px_72px_64px] gap-2 items-center px-2 py-3 hover:bg-white/[0.02] rounded-xl transition-colors cursor-pointer"
                onClick={() => setExpanded(isExpanded ? null : article.id)}
              >
                {/* Title cell */}
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`flex-shrink-0 w-1.5 h-1.5 rounded-full ${
                    article.sentiment === "positive" ? "bg-[var(--main-red)]" :
                    article.sentiment === "negative" ? "bg-[var(--main-blue)]" :
                    "bg-gray-600"
                  }`} />
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-gray-200 truncate leading-tight">
                      {article.title}
                    </p>
                    {hasRisk && (
                      <div className="mt-0.5">
                        <RiskBadge level={article.risk_alert_level} />
                      </div>
                    )}
                  </div>
                </div>

                {/* Event type cell */}
                <div className="min-w-0">
                  {article.event_type && article.event_type !== "general_neutral" ? (
                    <span className="inline-flex items-center text-xs font-bold px-2 py-0.5 rounded-md bg-white/[0.06] text-gray-400 truncate max-w-full">
                      {EVENT_TYPE_LABELS[article.event_type] ?? article.event_type}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-600">—</span>
                  )}
                </div>

                {/* Impact cell */}
                <div>
                  <ImpactBadge direction={article.impact_direction} score={article.impact_score} />
                </div>

                {/* Time cell */}
                <div className="flex items-center gap-1 text-gray-500">
                  <Clock size={10} weight="bold" />
                  <span className="text-xs font-bold tabular-nums font-outfit">
                    {_timeAgo(article.published_at)}
                  </span>
                </div>
              </div>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="mx-2 mb-2 p-3 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                  {article.summary && (
                    <p className="text-xs text-gray-400 mb-3 leading-relaxed">
                      {article.summary}
                    </p>
                  )}

                  {/* Risk flags */}
                  {article.risk_flags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {article.risk_flags.map((flag) => (
                        <span
                          key={flag}
                          className="inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md bg-red-500/10 text-red-400"
                        >
                          <Warning size={9} weight="fill" />
                          {RISK_FLAG_LABELS[flag] ?? flag}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Metrics grid */}
                  <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-3">
                    {article.impact_score !== undefined && (
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-600 mb-0.5">
                          임팩트 스코어
                        </p>
                        <p className={`text-sm font-black tabular-nums font-outfit leading-none ${
                          (article.impact_score ?? 0) > 0 ? "text-[var(--main-red)]" :
                          (article.impact_score ?? 0) < 0 ? "text-[var(--main-blue)]" :
                          "text-gray-400"
                        }`}>
                          {(article.impact_score ?? 0) > 0 ? "+" : ""}
                          {((article.impact_score ?? 0) * 100).toFixed(1)}
                        </p>
                      </div>
                    )}
                    {article.expected_alpha_1d !== undefined && (
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-600 mb-0.5">
                          예상 1일 알파
                        </p>
                        <p className={`text-sm font-black tabular-nums font-outfit leading-none ${
                          (article.expected_alpha_1d ?? 0) > 0 ? "text-[var(--main-red)]" :
                          (article.expected_alpha_1d ?? 0) < 0 ? "text-[var(--main-blue)]" :
                          "text-gray-400"
                        }`}>
                          {(article.expected_alpha_1d ?? 0) > 0 ? "+" : ""}
                          {((article.expected_alpha_1d ?? 0) * 100).toFixed(2)}%
                        </p>
                      </div>
                    )}
                    {article.credibility !== undefined && (
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-600 mb-0.5">
                          신뢰도
                        </p>
                        <p className="text-sm font-black tabular-nums font-outfit leading-none text-gray-300">
                          {Math.round((article.credibility ?? 0) * 100)}%
                        </p>
                      </div>
                    )}
                    {article.severity !== undefined && (
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-600 mb-0.5">
                          중요도
                        </p>
                        <p className="text-sm font-black tabular-nums font-outfit leading-none text-gray-300">
                          {Math.round((article.severity ?? 0) * 100)}%
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-white/[0.05]">
                    <span className="text-xs font-bold text-gray-600">{article.source}</span>
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="flex items-center gap-1 text-xs font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
                    >
                      원문 보기
                      <ArrowSquareOut size={11} weight="bold" />
                    </a>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {articles.length === 0 && impact?.latest_alpha && (
        <div className="py-8 text-center">
          <p className="text-sm text-gray-500">세부 기사를 불러오는 중입니다</p>
        </div>
      )}
    </div>
  );
}
