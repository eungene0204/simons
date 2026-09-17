// @ts-nocheck
/**
 * 백테스트 로그 ↔ 지표 카드 표기 일치 회귀 테스트 (2026-09-17 PER·PBR 워크스루 실측).
 *
 * 버그 ①: 응답에 calmar가 없으면 카드는 CAGR ÷ |MDD|로 0.14를 보이는데, 로그는 `calmar ?? 0`이라
 *        "Calmar: 0.00"이 찍혔다.
 * 버그 ②: 로그의 최종자산이 원 단위 부동소수를 그대로 찍어 "22,349,475.411원"이 나왔다.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

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

import BacktestDashboard, { resolveCalmar } from "./BacktestDashboard";

const result = {
  executionId: "exec-per-pbr",
  strategyId: "strat-per-pbr",
  symbols: [],
  totalReturn: 123.49,
  cagr: 8.38,
  buyAndHoldReturn: 383.76,
  maxDrawdown: -58.33,
  winRate: 60.7,
  profitFactor: 1.99,
  sharpe: 0.52,
  sortino: 0.73,
  trades: 262,
  initialCapital: 10000000,
  finalEquity: 22349475.411029488,
  equity: [10000000, 22349475.411029488],
  dates: ["2016-09-19", "2026-09-16"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

describe("백테스트 로그 지표 표기", () => {
  beforeEach(() => {
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }))
    );
  });

  it("calmar가 없으면 CAGR ÷ |MDD|로 계산한다", () => {
    expect(resolveCalmar({ cagr: 8.38, maxDrawdown: -58.33 }).toFixed(2)).toBe("0.14");
    expect(resolveCalmar({ calmar: 0.5, cagr: 8.38, maxDrawdown: -58.33 })).toBe(0.5);
    expect(resolveCalmar({ cagr: 8.38, maxDrawdown: 0 })).toBe(0);
  });

  it("로그의 Calmar와 최종자산이 카드와 같은 값으로 찍힌다", () => {
    render(<BacktestDashboard result={result} onRestart={() => {}} disableHistorySave promptText="PER·PBR" />);

    const body = document.body.textContent ?? "";
    expect(body).toContain("Calmar: 0.14");
    expect(body).not.toContain("Calmar: 0.00");
    expect(body).toContain("최종자산 22,349,475원");
    expect(body).not.toMatch(/22,349,475\.\d+원/);
    expect(screen.getAllByText("0.14").length).toBeGreaterThan(0);
  });

  // 2026-09-17 AI 관련주 워크스루 실측: 테마 66종목(코스닥 61)인데 로그가 "유니버스: KOSPI"였다 —
  // 지정 종목·테마 유니버스는 universeId가 비어 있어 기본값 KOSPI로 떨어졌다.
  it("universeId가 비어 있으면 시장 이름을 추정하지 않고 지정 종목으로 찍는다", () => {
    render(<BacktestDashboard result={{ ...result, universeId: "" }} onRestart={() => {}} disableHistorySave promptText="AI 관련주" />);

    const body = document.body.textContent ?? "";
    expect(body).toContain("유니버스: 지정 종목");
    expect(body).not.toContain("유니버스: KOSPI");
  });

  it("universeId가 있으면 시장 이름을 찍는다", () => {
    render(<BacktestDashboard result={{ ...result, universeId: "kosdaq" }} onRestart={() => {}} disableHistorySave promptText="코스닥" />);

    expect(document.body.textContent ?? "").toContain("유니버스: KOSDAQ");
  });
});
