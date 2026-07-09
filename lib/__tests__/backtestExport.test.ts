import { describe, it, expect } from "vitest";
import {
  buildExportFile,
  exportFileName,
  strategySlug,
  type BacktestExportPayload,
} from "@/lib/backtest-export";

const payload: BacktestExportPayload = {
  metadata: {
    strategyName: "볼린저 밴드 평균회귀 전략",
    backtestId: "bt_20260708_001",
    exportedAt: "2026-07-08T15:30:00+09:00",
    period: { from: "2022-01-01", to: "2026-07-08" },
    universe: "KOSPI",
    initialCapital: 10_000_000,
    finalEquity: 12_520_000,
    commission: 0.00015,
    slippage: 0.0005,
    benchmark: "KOSPI",
  },
  stockAnalysis: [
    {
      symbol: "005930",
      name: "삼성전자",
      tradeCount: 12,
      winRate: 0.583,
      totalReturn: 0.252,
      totalProfit: 252_000,
      avgBuyPrice: 70_000,
      avgSellPrice: 75_000,
    },
  ],
  tradeHistory: [
    {
      date: "2024-03-12",
      symbol: "005930",
      name: "삼성전자",
      type: "buy",
      price: 72_100,
      quantity: 10,
      amount: 721_000,
      reason: "볼린저 하단 터치",
    },
  ],
};

describe("strategySlug", () => {
  it("한글/기호를 제거하고 영숫자 슬러그를 만든다", () => {
    expect(strategySlug("Bollinger Mean Reversion")).toBe("bollinger_mean_reversion");
  });
  it("영숫자가 없으면 기본값 strategy 를 쓴다", () => {
    expect(strategySlug("볼린저 전략")).toBe("strategy");
  });
});

describe("exportFileName", () => {
  it("{slug}_backtest_result_{yyyyMMdd}.{ext} 형식을 따른다", () => {
    expect(exportFileName({ ...payload, metadata: { ...payload.metadata, strategyName: "bollinger mean reversion" } }, "csv"))
      .toBe("bollinger_mean_reversion_backtest_result_20260708.csv");
    expect(exportFileName(payload, "json")).toBe("strategy_backtest_result_20260708.json");
  });
});

describe("buildExportFile CSV", () => {
  const { content, mimeType } = buildExportFile(payload, "csv");

  it("UTF-8 BOM 으로 시작한다", () => {
    expect(content.charCodeAt(0)).toBe(0xfeff);
    expect(mimeType).toContain("text/csv");
  });

  it("전략명은 메타데이터에 한 번만 포함되고 데이터 행에는 반복되지 않는다", () => {
    const occurrences = content.split("볼린저 밴드 평균회귀 전략").length - 1;
    expect(occurrences).toBe(1);
    // 종목 데이터 행에는 종목코드로 시작하고 전략명이 없다
    const stockLine = content.split("\r\n").find((l) => l.startsWith("005930,삼성전자,"));
    expect(stockLine).toBeDefined();
    expect(stockLine).not.toContain("볼린저");
  });

  it("섹션 헤더와 비율(%) 표기를 포함한다", () => {
    expect(content).toContain("[종목 분석]");
    expect(content).toContain("[매매 기록]");
    expect(content).toContain("58.30%"); // winRate 0.583
    expect(content).toContain("수수료,0.015%");
    expect(content).toContain("슬리피지,0.05%");
    expect(content).toContain("매수"); // 매매 구분 한글화
  });

  it("종목 분석 행에 평균 매수가/매도가를 포함한다", () => {
    expect(content).toContain("평균매수가");
    expect(content).toContain("평균매도가");
    const stockLine = content.split("\r\n").find((l) => l.startsWith("005930,삼성전자,"));
    expect(stockLine).toContain("70,000");
    expect(stockLine).toContain("75,000");
  });

  it("금액은 천단위 콤마로 표시하고 소수점은 반올림해 제거한다", () => {
    // 콤마가 포함된 셀은 CSV 규칙상 따옴표로 감싸진다
    expect(content).toContain('초기자본,"10,000,000"');
    expect(content).toContain('최종자산,"12,520,000"');
  });

  it("소수점이 있는 금액도 정수로 반올림해 콤마 표기한다", () => {
    const decimalPayload: BacktestExportPayload = {
      ...payload,
      metadata: { ...payload.metadata, finalEquity: 14_511_541.2167603 },
    };
    const { content: decimalContent } = buildExportFile(decimalPayload, "csv");
    expect(decimalContent).toContain('최종자산,"14,511,541"');
    expect(decimalContent).not.toContain("14511541.");
  });
});

describe("buildExportFile — 전략 배지 메타데이터", () => {
  const payloadWithBadges: BacktestExportPayload = {
    ...payload,
    metadata: {
      ...payload.metadata,
      entrySignals: ["RSI 과매도", "거래량 급증"],
      exitSignals: ["RSI 과매수"],
      position: "종목당 10%",
      rebalancing: "월간 리밸런싱",
      risk: "손절 -8%",
    },
  };

  it("CSV 메타데이터에 진입/청산 신호와 포지션/리밸런싱/리스크를 포함한다", () => {
    const { content } = buildExportFile(payloadWithBadges, "csv");
    expect(content).toContain("진입 신호,RSI 과매도 / 거래량 급증");
    expect(content).toContain("청산 신호,RSI 과매수");
    expect(content).toContain("포지션,종목당 10%");
    expect(content).toContain("리밸런싱,월간 리밸런싱");
    expect(content).toContain("리스크,손절 -8%");
  });

  it("JSON 메타데이터에 동일한 필드를 포함한다", () => {
    const { content } = buildExportFile(payloadWithBadges, "json");
    const parsed = JSON.parse(content);
    expect(parsed.metadata.entrySignals).toEqual(["RSI 과매도", "거래량 급증"]);
    expect(parsed.metadata.risk).toBe("손절 -8%");
  });
});

describe("buildExportFile — 탭별 섹션 분리", () => {
  it("stockAnalysis만 있으면 종목 분석 섹션만 출력하고 파일명에 접미사가 붙는다", () => {
    const stockOnly: BacktestExportPayload = {
      metadata: payload.metadata,
      stockAnalysis: payload.stockAnalysis,
    };
    const { content } = buildExportFile(stockOnly, "csv");
    expect(content).toContain("[종목 분석]");
    expect(content).not.toContain("[매매 기록]");
    expect(exportFileName(stockOnly, "csv")).toContain("_stock_analysis_");
  });

  it("tradeHistory만 있으면 매매 기록 섹션만 출력하고 파일명에 접미사가 붙는다", () => {
    const tradesOnly: BacktestExportPayload = {
      metadata: payload.metadata,
      tradeHistory: payload.tradeHistory,
    };
    const { content } = buildExportFile(tradesOnly, "csv");
    expect(content).not.toContain("[종목 분석]");
    expect(content).toContain("[매매 기록]");
    expect(exportFileName(tradesOnly, "csv")).toContain("_trade_history_");
  });

  it("둘 다 있으면(과거 동작) 파일명에 접미사가 붙지 않는다", () => {
    expect(exportFileName(payload, "csv")).toBe("strategy_backtest_result_20260708.csv");
  });
});

describe("buildExportFile JSON", () => {
  const { content } = buildExportFile(payload, "json");
  const parsed = JSON.parse(content);

  it("strategyName 은 metadata 에만 있고 각 row 에는 없다", () => {
    expect(parsed.metadata.strategyName).toBe("볼린저 밴드 평균회귀 전략");
    expect(parsed.stockAnalysis[0].strategyName).toBeUndefined();
    expect(parsed.tradeHistory[0].strategyName).toBeUndefined();
  });

  it("비율은 소수로 유지하고 pretty print 한다", () => {
    expect(parsed.stockAnalysis[0].winRate).toBe(0.583);
    expect(content).toContain("\n  "); // 들여쓰기(pretty print)
  });
});
