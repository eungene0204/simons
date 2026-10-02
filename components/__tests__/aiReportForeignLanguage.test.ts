import { describe, expect, it } from "vitest";
import { hasForeignLanguageReportText } from "@/components/strategy/backtest/aiReportMetrics";

// 2026-10-02 사고: AI 리포트 서술에 일본어 어미·한자·영어 문장이 섞여 저장됐다.
describe("hasForeignLanguageReportText", () => {
  it("일본어 가나·한자·키릴 문자를 잡는다(언어 무관)", () => {
    expect(hasForeignLanguageReportText(["포착하지 못했을 가능성があります."], "ko")).toBe(true);
    expect(hasForeignLanguageReportText([["표본이 充分합니다."]], "ko")).toBe(true);
    expect(hasForeignLanguageReportText(["Сигнал 과다"], "ko")).toBe(true);
    expect(hasForeignLanguageReportText(["The sample is small, 可能性があります."], "en")).toBe(true);
  });

  it("한국어 UI에서 영어 문장을 잡지만 지표 약어·고유 명칭은 통과시킨다", () => {
    expect(hasForeignLanguageReportText(["This strategy depends on a single regime."], "ko")).toBe(true);
    expect(
      hasForeignLanguageReportText(
        [
          "CAGR 대비 MDD가 깊고 Profit Factor가 1에 가까워 RSI·MACD 조건의 Walk-Forward 검증이 필요합니다.",
          ["KOSPI 200 구간 수익이 2023년에 집중됐습니다 — 샤프 비율(Sharpe Ratio)도 같습니다."],
          undefined,
          "",
        ],
        "ko",
      ),
    ).toBe(false);
  });

  it("영어 UI의 영어 리포트는 통과시킨다", () => {
    expect(hasForeignLanguageReportText(["This strategy depends on a single regime."], "en")).toBe(false);
  });
});
