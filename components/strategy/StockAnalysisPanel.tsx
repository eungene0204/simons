"use client";

import { Warning } from "phosphor-react";

// ─── Types (백엔드 StockAnalysisResult 미러) ────────────────────────────────────

// [규제 안전] 매수/매도/보유 '행동 지시'가 아니라 지표 종합 '객관적 상태 등급'이다(백엔드 미러).
export type Recommendation =
  | "FAVORABLE"
  | "MILDLY_FAVORABLE"
  | "NEUTRAL"
  | "ELEVATED_RISK"
  | "HIGH_RISK"
  | "INSUFFICIENT_DATA";

export interface StockSignals {
  trend?: string | null;
  valuation?: string | null;
  news_sentiment?: string | null;
  forecast?: string | null;
  risk?: string | null;
}

export interface AIForecastGauge {
  down_risk_level?: string | null; // elevated | moderate | calm
  down_pctl?: number | null;
  up_pctl?: number | null;
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
  ai_forecast?: AIForecastGauge | null;
  news_summary?: string | null;
  news_url?: string | null;
  risk_factors: string[];
  missing_data: string[];
  disclaimer: string;
}

// ─── 라벨 매핑 ──────────────────────────────────────────────────────────────────

const NO_DATA = "데이터 없음";

const TREND_LABEL: Record<string, string> = {
  strong_up: "강한 상승", up: "상승", neutral_positive: "중립 이상", neutral: "중립",
  neutral_negative: "중립 이하", down: "하락", strong_down: "강한 하락",
};
const VALUATION_LABEL: Record<string, string> = { cheap: "저평가", neutral: "적정", expensive: "고평가" };
const SENTIMENT_LABEL: Record<string, string> = { positive: "긍정", neutral: "중립", negative: "부정" };
const RISK_LABEL: Record<string, string> = { low: "낮음", medium: "보통", high: "높음" };

// AI 예측 — 상승/하락 신호를 종목 자기 이력 대비 퍼센타일로 보정한 뒤 더 두드러진 쪽을
// 보여준다. raw 확률은 down>up로 구조적 편향이 있어(거의 항상 하락) 퍼센타일로 비교한다.
function aiForecastDisplay(f?: AIForecastGauge | null): { value: string; missing: boolean } {
  if (!f || f.up_pctl == null || f.down_pctl == null) return { value: NO_DATA, missing: true };
  if (f.up_pctl === f.down_pctl) return { value: "중립", missing: false };
  return { value: `${f.up_pctl > f.down_pctl ? "상승" : "하락"} 우위`, missing: false };
}

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
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs font-bold text-gray-500">{rowLabel}</span>
      <span className={`text-xs font-bold ${missing ? "text-slate-500" : "text-white"}`}>{value}</span>
    </div>
  );
}

// ─── Panel ───────────────────────────────────────────────────────────────────

export default function StockAnalysisPanel({ result }: { result: StockAnalysisResult }) {
  const m = result.metrics;
  const s = result.signals;
  // 규제 회피로 AI 예측 행을 노출하지 않음 — 재노출 시 주석 해제(aiForecastDisplay 보존).
  // const ai = aiForecastDisplay(result.ai_forecast);
  // 위험도 점수 산출에는 뉴스가 반영되지만(보존), 뉴스 비노출 방침에 따라
  // 뉴스에서 파생된 리스크 요인 항목은 화면에 표시하지 않는다.
  const visibleRiskFactors = result.risk_factors.filter((f) => !f.includes("뉴스"));
  const changeColor =
    m.change_pct == null ? "text-slate-500" : m.change_pct >= 0 ? "text-red-400" : "text-blue-400";

  return (
    <div className="w-full rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3">
      {/* 헤더: 종목 식별 정보 */}
      <div className="flex items-center gap-2">
        <div className="flex items-baseline gap-2">
          <h3 className="text-sm font-black text-white">{result.name}</h3>
          <span className="text-[11px] font-bold text-gray-500">{result.symbol}</span>
        </div>
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

      {/* 신호 요약 + 핵심 지표 (단일 테이블) */}
      <div className="rounded-xl bg-white/[0.02] px-3 py-1">
        <Row label="추세" value={label(TREND_LABEL, s.trend)} missing={!s.trend} />
        <Row label="밸류에이션" value={label(VALUATION_LABEL, s.valuation)} missing={!s.valuation} />
        {/* 규제(유사투자자문업) 회피 — 뉴스 감성/AI 예측은 노출하지 않는다(코드/데이터는 보존). */}
        {/* <Row label="뉴스 감성" value={label(SENTIMENT_LABEL, s.news_sentiment)} missing={!s.news_sentiment} /> */}
        {/* <Row label="AI 예측" value={ai.value} missing={ai.missing} /> */}
        <Row label="위험도" value={label(RISK_LABEL, s.risk)} missing={!s.risk} />
        <Row label="PER" value={num(m.per, "배")} missing={m.per == null} />
        <Row label="PBR" value={num(m.pbr, "배")} missing={m.pbr == null} />
        <Row label="ROE" value={num(m.roe, "%")} missing={m.roe == null} />
        <Row label="연율 변동성" value={num(m.volatility_pct, "%", 0)} missing={m.volatility_pct == null} />
        <Row label="섹터" value={m.sector ?? NO_DATA} missing={!m.sector} />
      </div>

      {/* 리스크 요인 */}
      {visibleRiskFactors.length > 0 && (
        <div className="flex flex-col gap-1.5 p-3 rounded-xl border border-amber-500/20">
          <span className="text-[11px] font-black text-amber-300">리스크 요인</span>
          <ul className="space-y-0.5">
            {visibleRiskFactors.map((f, i) => (
              <li key={i} className="text-xs font-bold text-gray-300 leading-relaxed">• {f}</li>
            ))}
          </ul>
        </div>
      )}

    </div>
  );
}
