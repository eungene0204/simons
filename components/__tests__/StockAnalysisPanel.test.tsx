import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StockAnalysisPanel, { type StockAnalysisResult } from "@/components/strategy/StockAnalysisPanel";

function makeResult(overrides: Partial<StockAnalysisResult> = {}): StockAnalysisResult {
  return {
    intent: "STOCK_ANALYSIS",
    symbol: "005930",
    name: "삼성전자",
    recommendation: "ACCUMULATE",
    confidence: 0.68,
    summary: "추세는 중립 이상이나 단기 변동성 리스크가 존재합니다.",
    explanation: "삼성전자는 현재 추세와 뉴스 흐름은 중립 이상입니다.",
    signals: { trend: "up", valuation: "neutral", news_sentiment: "positive", forecast: null, risk: "medium" },
    metrics: {
      current_price: 70000, change_pct: 1.2, volume: 1000, per: 12.3, pbr: 1.1, roe: 14.0,
      debt_ratio: null, market_cap: null, sector: "반도체", volatility_pct: 25, as_of: "2026-06-09",
    },
    news_summary: "최근 뉴스 3건",
    risk_factors: ["반도체 업황 리스크"],
    missing_data: ["AI 예측", "시가총액"],
    disclaimer: "이 분석은 투자 판단을 위한 참고 정보이며, 최종 투자 결정은 본인의 책임입니다.",
    ...overrides,
  };
}

describe("StockAnalysisPanel", () => {
  it("종목명과 Recommendation 배지를 표시한다", () => {
    render(<StockAnalysisPanel result={makeResult()} />);
    expect(screen.getByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("분할 매수")).toBeInTheDocument();  // ACCUMULATE 라벨
  });

  it("데이터가 없는 신호는 '데이터 없음'으로 표시한다", () => {
    render(<StockAnalysisPanel result={makeResult({ signals: { trend: null, valuation: null, news_sentiment: null, risk: null } })} />);
    expect(screen.getAllByText("데이터 없음").length).toBeGreaterThan(0);
  });

  it("INSUFFICIENT_DATA는 '데이터 부족' 배지로 표시한다", () => {
    render(<StockAnalysisPanel result={makeResult({ recommendation: "INSUFFICIENT_DATA" })} />);
    expect(screen.getByText("데이터 부족")).toBeInTheDocument();
  });

  it("리스크 요인을 나열한다", () => {
    render(<StockAnalysisPanel result={makeResult()} />);
    expect(screen.getByText(/반도체 업황 리스크/)).toBeInTheDocument();
  });

  it("AI 예측은 up/down 퍼센타일 중 더 높은 쪽을 표시한다 (상승 우위)", () => {
    render(<StockAnalysisPanel result={makeResult({
      ai_forecast: { down_risk_level: "calm", up_pctl: 80, down_pctl: 40 },
    })} />);
    expect(screen.getByText("상승 우위")).toBeInTheDocument();
  });

  it("AI 예측 — down_pctl이 더 높으면 하락 우위", () => {
    render(<StockAnalysisPanel result={makeResult({
      ai_forecast: { down_risk_level: "elevated", up_pctl: 40, down_pctl: 92 },
    })} />);
    expect(screen.getByText("하락 우위")).toBeInTheDocument();
  });

  it("AI 예측 데이터가 없으면 '데이터 없음'", () => {
    render(<StockAnalysisPanel result={makeResult({ ai_forecast: null })} />);
    expect(screen.getByText("AI 예측")).toBeInTheDocument();
    expect(screen.getAllByText("데이터 없음").length).toBeGreaterThan(0);
  });

});
