// @ts-nocheck
/**
 * 초기자금·총수익·ROI는 엔진이 동봉한 초기자본 기준이다(엔진 v16.12, 2026-09-17 실측).
 *
 * 창 첫날 시가 체결로 자산곡선 첫 값(첫 거래일 종가 평가액)이 초기자본과 달라졌는데, 결과 매퍼가
 * initialCapital = equity[0]로 채워 로그 "초기자금: 9,748,557원"·카드 ROI +42.11%(실제 +38.54%)가 나갔다.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/react";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/" }));

import BacktestDashboard from "./BacktestDashboard";
import { mapRawBacktestResult } from "@/app/analytics/new/backtestResultMapper";

describe("초기자본 기준 표시", () => {
  beforeEach(() => {
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })));
  });

  it("첫날 체결로 equity[0]이 초기자본과 달라도 로그·카드는 엔진 동봉 초기자본을 쓴다", () => {
    const raw = {
      symbols: [], totalReturn: 38.54, cagr: 11.5, maxDrawdown: -54.29, trades: 163,
      initialCapital: 10_000_000,
      equity: [9_748_557, 13_853_831],
      dates: ["2023-09-18", "2026-09-16"],
      signals: [],
    };
    const result = mapRawBacktestResult(raw, "exec-day1");
    expect(result.initialCapital).toBe(10_000_000);

    render(<BacktestDashboard result={result} onRestart={() => {}} disableHistorySave promptText="AI 테마" />);
    const body = document.body.textContent ?? "";
    expect(body).toContain("초기자금: 10,000,000원");
    expect(body).not.toContain("9,748,557원");
    expect(body).toContain("투자 수익률ROI+38.54%");
    expect(body).toContain("총 수익Total Profit3,853,831원");
    expect(body).toContain("최종자산 13,853,831원 / 수익률 38.54%");
  });
});
