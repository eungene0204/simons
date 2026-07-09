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
