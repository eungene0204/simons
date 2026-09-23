import { describe, expect, it } from "vitest";

import { buildExportFile, exportFileName, isExportFormat } from "./backtest-export";
import { buildTearsheetHtml, equitySvg, type TearsheetPayload } from "./tearsheet";

const payload: TearsheetPayload = {
  strategyName: "PER 저평가 전략",
  generatedAt: "2026-09-23T12:00:00+09:00",
  period: { from: "2023-01-02", to: "2024-12-30" },
  universe: "KOSPI200",
  currency: "KRW",
  initialCapital: 10_000_000,
  finalEquity: 12_500_000,
  metrics: [{ label: "CAGR", value: "12.0%" }, { label: "MDD", value: "-15.0%" }],
  summaryLines: ["진입: PER 10 이하", "리밸런싱: 매월"],
  dates: ["2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"],
  equity: [10_000_000, 10_200_000, 9_900_000, 12_500_000],
  benchmarkEquity: [10_000_000, 10_050_000, null, 10_100_000],
  monthlyReturns: { "2023-01": 2.0, "2023-02": -1.5, "2024-12": 3.0 },
  sections: [{ title: "성과 귀인", header: ["종목", "기여도"], rows: [["삼성전자 (005930)", "+3.1%"]] }],
  warnings: ["거래 수가 30건 미만입니다."],
};

describe("tearsheet", () => {
  it("독립 HTML 문서를 만들고 값·요약·경고·면책을 담는다", () => {
    const html = buildTearsheetHtml(payload);
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain("PER 저평가 전략");
    expect(html).toContain("25.00%");                   // 총수익률
    expect(html).toContain("진입: PER 10 이하");
    expect(html).toContain("삼성전자 (005930)");
    expect(html).toContain("거래 수가 30건 미만입니다.");
    expect(html).toContain("window.print()");
    expect(html).toContain("미래 수익은 보장되지 않으며");
    expect(html).not.toContain("<script src=");         // 외부 자원 없음
  });

  it("월별 표는 연도별 행과 연간 복리를 계산한다", () => {
    const html = buildTearsheetHtml(payload);
    expect(html).toContain("<td>2023</td>");
    expect(html).toContain("<td>2024</td>");
    // 2023: (1.02)(0.985)-1 = 0.47%
    expect(html).toContain(">0.5<");
  });

  it("자산곡선 SVG는 벤치마크 결측을 끊어 그린다", () => {
    const svg = equitySvg(payload.dates, payload.equity, payload.benchmarkEquity);
    expect(svg).toContain("stroke=\"#0ea5e9\"");
    expect(svg).toContain("stroke=\"#9ca3af\"");
    expect(svg).toContain("최대 낙폭");
  });

  it("html 포맷 내보내기는 티어시트 파일명·MIME으로 나간다", () => {
    expect(isExportFormat("html")).toBe(true);
    const exportPayload = { metadata: { strategyName: "PER Value", exportedAt: "2026-09-23T12:00:00+09:00" } as any, tearsheet: payload };
    expect(exportFileName(exportPayload, "html")).toBe("per_value_backtest_result_tearsheet_20260923.html");
    const file = buildExportFile(exportPayload, "html");
    expect(file.mimeType).toContain("text/html");
    expect(file.content).toContain("PER 저평가 전략");
    expect(() => buildExportFile({ metadata: exportPayload.metadata } as any, "html")).toThrow();
  });
});
