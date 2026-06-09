"use client";

import { Warning } from "phosphor-react";

// ─── Types (백엔드 StockAnalysisResult 미러) ────────────────────────────────────

export type Recommendation =
  | "STRONG_BUY"
  | "ACCUMULATE"
  | "HOLD"
  | "CAUTION"
  | "AVOID"
  | "INSUFFICIENT_DATA";

export interface StockSignals {
  trend?: string | null;
  valuation?: string | null;
  news_sentiment?: string | null;
  forecast?: string | null;
  risk?: string | null;
}

export interface StockMetrics {
  current_price?: number | null;
  change_pct?: number | null;
  volume?: number | null;
  per?: number | null;
  pbr?: number | null;
  roe?: number | null;
  debt_ratio?: number | null;
  market_cap?: number | null;
  sector?: string | null;
  volatility_pct?: number | null;
  as_of?: string | null;
}

export interface StockAnalysisResult {
  intent: string;
  symbol: string;
  name: string;
  recommendation: Recommendation;
  confidence: number;
  summary: string;
  explanation: string;
  signals: StockSignals;
  metrics: StockMetrics;
  news_summary?: string | null;
  news_url?: string | null;
  risk_factors: string[];
  missing_data: string[];
  disclaimer: string;
}

// ─── 라벨/색상 매핑 ──────────────────────────────────────────────────────────────

const NO_DATA = "데이터 없음";

const REC_META: Record<Recommendation, { label: string; cls: string }> = {
  STRONG_BUY: { label: "강한 긍정", cls: "text-emerald-300 border-emerald-500/40" },
  ACCUMULATE: { label: "분할 매수", cls: "text-teal-300 border-teal-500/40" },
  HOLD: { label: "보유/관망", cls: "text-gray-300 border-gray-500/40" },
  CAUTION: { label: "주의", cls: "text-amber-300 border-amber-500/40" },
  AVOID: { label: "회피", cls: "text-red-300 border-red-500/40" },
  INSUFFICIENT_DATA: { label: "데이터 부족", cls: "text-slate-300 border-slate-500/40" },
};

const TREND_LABEL: Record<string, string> = {
  strong_up: "강한 상승", up: "상승", neutral_positive: "중립 이상", neutral: "중립",
  neutral_negative: "중립 이하", down: "하락", strong_down: "강한 하락",
};
const VALUATION_LABEL: Record<string, string> = { cheap: "저평가", neutral: "적정", expensive: "고평가" };
const SENTIMENT_LABEL: Record<string, string> = { positive: "긍정", neutral: "중립", negative: "부정" };
const FORECAST_LABEL: Record<string, string> = {
  positive: "상승 우위", slightly_positive: "약한 상승", neutral: "중립",
  slightly_negative: "약한 하락", negative: "하락 우위",
};
const RISK_LABEL: Record<string, string> = { low: "낮음", medium: "보통", high: "높음" };

function label(map: Record<string, string>, value?: string | null): string {
  if (!value) return NO_DATA;
  return map[value] ?? value;
}

function num(value: number | null | undefined, suffix = "", digits = 1): string {
  if (value === null || value === undefined) return NO_DATA;
  return `${value.toLocaleString("ko-KR", { maximumFractionDigits: digits })}${suffix}`;
}

// ─── Row ─────────────────────────────────────────────────────────────────────

function Row({ label: rowLabel, value, missing }: { label: string; value: string; missing?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-white/[0.04] last:border-0">
      <span className="text-xs font-bold text-gray-500">{rowLabel}</span>
      <span className={`text-xs font-bold ${missing ? "text-slate-500" : "text-white"}`}>{value}</span>
    </div>
  );
}

// ─── Panel ───────────────────────────────────────────────────────────────────

export default function StockAnalysisPanel({ result }: { result: StockAnalysisResult }) {
  const m = result.metrics;
  const s = result.signals;
  const rec = REC_META[result.recommendation] ?? REC_META.INSUFFICIENT_DATA;
  const changeColor =
    m.change_pct == null ? "text-slate-500" : m.change_pct >= 0 ? "text-red-400" : "text-blue-400";

  return (
    <div className="w-full rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3">
      {/* 헤더: 종목명 + Recommendation 배지 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <h3 className="text-sm font-black text-white">{result.name}</h3>
          <span className="text-[11px] font-bold text-gray-500">{result.symbol}</span>
        </div>
        <span className={`px-2.5 py-1 rounded-full border text-[11px] font-black ${rec.cls}`}>
          {rec.label}
        </span>
      </div>

      {/* 현재가 / 등락률 */}
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-black text-white">
          {m.current_price == null ? NO_DATA : `${m.current_price.toLocaleString("ko-KR")}원`}
        </span>
        {m.change_pct != null && (
          <span className={`text-xs font-bold ${changeColor}`}>
            {m.change_pct >= 0 ? "+" : ""}
            {m.change_pct.toFixed(2)}%
          </span>
        )}
        {m.as_of && <span className="text-[10px] font-bold text-gray-600 ml-auto">{m.as_of} 기준</span>}
      </div>

      {/* 신호 요약 */}
      <div className="rounded-xl bg-white/[0.02] px-3 py-1">
        <Row label="추세" value={label(TREND_LABEL, s.trend)} missing={!s.trend} />
        <Row label="밸류에이션" value={label(VALUATION_LABEL, s.valuation)} missing={!s.valuation} />
        <Row label="뉴스 감성" value={label(SENTIMENT_LABEL, s.news_sentiment)} missing={!s.news_sentiment} />
        <Row label="AI 예측" value={label(FORECAST_LABEL, s.forecast)} missing={!s.forecast} />
        <Row label="위험도" value={label(RISK_LABEL, s.risk)} missing={!s.risk} />
      </div>

      {/* 핵심 지표 */}
      <div className="rounded-xl bg-white/[0.02] px-3 py-1">
        <Row label="PER" value={num(m.per, "배")} missing={m.per == null} />
        <Row label="PBR" value={num(m.pbr, "배")} missing={m.pbr == null} />
        <Row label="ROE" value={num(m.roe, "%")} missing={m.roe == null} />
        <Row label="연율 변동성" value={num(m.volatility_pct, "%", 0)} missing={m.volatility_pct == null} />
        <Row label="섹터" value={m.sector ?? NO_DATA} missing={!m.sector} />
      </div>

      {/* 리스크 요인 */}
      {result.risk_factors.length > 0 && (
        <div className="flex flex-col gap-1.5 p-3 rounded-xl border border-amber-500/20">
          <span className="text-[11px] font-black text-amber-300">리스크 요인</span>
          <ul className="space-y-0.5">
            {result.risk_factors.map((f, i) => (
              <li key={i} className="text-xs font-bold text-gray-300 leading-relaxed">• {f}</li>
            ))}
          </ul>
        </div>
      )}

    </div>
  );
}
