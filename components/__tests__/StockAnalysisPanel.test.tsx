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
  it("종목명은 표시하고 Recommendation 배지는 표시하지 않는다", () => {
    render(<StockAnalysisPanel result={makeResult()} />);
    expect(screen.getByText("삼성전자")).toBeInTheDocument();
    expect(screen.queryByText("분할 매수")).not.toBeInTheDocument();
  });

  it("데이터가 없는 신호는 '데이터 없음'으로 표시한다", () => {
    render(<StockAnalysisPanel result={makeResult({ signals: { trend: null, valuation: null, news_sentiment: null, risk: null } })} />);
    expect(screen.getAllByText("데이터 없음").length).toBeGreaterThan(0);
  });

  it("INSUFFICIENT_DATA도 Recommendation 배지를 표시하지 않는다", () => {
    render(<StockAnalysisPanel result={makeResult({ recommendation: "INSUFFICIENT_DATA" })} />);
    expect(screen.queryByText("데이터 부족")).not.toBeInTheDocument();
  });

  it("리스크 요인을 나열한다", () => {
    render(<StockAnalysisPanel result={makeResult()} />);
    expect(screen.getByText(/반도체 업황 리스크/)).toBeInTheDocument();
  });

  // 규제(유사투자자문업) 회피 — AI 예측/뉴스 감성은 화면에 노출하지 않는다(코드/데이터는 보존).
  it("AI 예측은 방향 예측(상승/하락 우위)을 노출하지 않는다", () => {
    render(<StockAnalysisPanel result={makeResult({
      ai_forecast: { down_risk_level: "elevated", up_pctl: 40, down_pctl: 92 },
    })} />);
    expect(screen.queryByText("AI 예측")).not.toBeInTheDocument();
    expect(screen.queryByText("하락 우위")).not.toBeInTheDocument();
    expect(screen.queryByText("상승 우위")).not.toBeInTheDocument();
  });

  it("뉴스 감성은 노출하지 않는다", () => {
    render(<StockAnalysisPanel result={makeResult({
      signals: { trend: "up", valuation: "neutral", news_sentiment: "positive", forecast: null, risk: "medium" },
    })} />);
    expect(screen.queryByText("뉴스 감성")).not.toBeInTheDocument();
  });

  it("뉴스에서 파생된 리스크 요인은 표시하지 않고, 나머지는 표시한다", () => {
    render(<StockAnalysisPanel result={makeResult({
      risk_factors: ["높은 변동성(연율 79%)", "부정적 뉴스 흐름", "뉴스 고위험 경보"],
    })} />);
    expect(screen.getByText(/높은 변동성/)).toBeInTheDocument();
    expect(screen.queryByText(/부정적 뉴스 흐름/)).not.toBeInTheDocument();
    expect(screen.queryByText(/뉴스 고위험 경보/)).not.toBeInTheDocument();
  });

  it("뉴스 리스크 요인만 있으면 리스크 요인 섹션을 숨긴다", () => {
    render(<StockAnalysisPanel result={makeResult({
      risk_factors: ["부정적 뉴스 흐름"],
    })} />);
    expect(screen.queryByText("리스크 요인")).not.toBeInTheDocument();
  });

});
