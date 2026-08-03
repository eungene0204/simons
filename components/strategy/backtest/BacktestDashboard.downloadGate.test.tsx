// @ts-nocheck
/**
 * BacktestDashboard 결과 다운로드 플랜 게이트 회귀 테스트.
 *
 * 결과 다운로드는 Pro/Premium 전용 기능이다.
 * - 상단 "백테스트 결과 익스포트" 버튼은 제거되고 종목 분석 탭 상단에
 *   CSV/JSON 직접 내보내기 버튼이 노출된다.
 * - 무료 플랜: 버튼 클릭 시 업그레이드 안내만 보이고 /api/backtest/export 호출이 발생하지 않는다.
 * - 유료 플랜: 버튼 클릭 시 해당 포맷 export API 를 바로 호출한다.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => <div /> }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import BacktestDashboard from "./BacktestDashboard";

const baseResult = {
  executionId: "exec-1",
  strategyId: "strat-1",
  cacheKey: "ck-1",
  symbols: [],
  totalReturn: 0,
  cagr: 0,
  buyAndHoldReturn: 0,
  maxDrawdown: 0,
  winRate: 0,
  profitFactor: 0,
  sharpe: 0,
  sortino: 0,
  trades: 0,
  finalEquity: 10000000,
  initialCapital: 10000000,
  equity: [],
  dates: ["2022-01-01", "2026-07-08"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
  perAssetStats: {},
} as any;

function renderWith(planId: string) {
  let exportCalls = 0;
  const fetchMock = vi.fn((url: string) => {
    if (typeof url === "string" && url.includes("/api/backtest/export")) {
      exportCalls += 1;
      return Promise.resolve({ ok: true, blob: () => Promise.resolve(new Blob(["x"])) });
    }
    if (typeof url === "string" && url.includes("/api/user/plan")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ plan: { planId } }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <BacktestDashboard
      result={baseResult}
      onRestart={() => {}}
      disableHistorySave
      promptText="볼린저 전략"
      backtestDsl={{ universe: { id: "KOSPI" }, entry: {}, exit: {} }}
      strategySummary={{ strategyName: "볼린저 전략", universeName: "KOSPI" }}
    />
  );
  return () => exportCalls;
}

describe("BacktestDashboard 결과 다운로드 플랜 게이트", () => {
  beforeEach(() => {
    cleanup();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:mock-download"),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  it("무료 플랜은 종목 분석 탭의 CSV 내보내기 버튼에서 업그레이드 안내만 보이고 export API 를 호출하지 않는다", async () => {
    const getCalls = renderWith("FREE");
    const user = userEvent.setup();

    expect(screen.queryByRole("button", { name: "백테스트 결과 익스포트" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "종목 분석" }));

    const button = await screen.findByRole("button", { name: "CSV 내보내기" });
    await vi.waitFor(() => expect(button).not.toBeDisabled());
    await user.click(button);

    expect(await screen.findByRole("link", { name: "요금제 보기" })).toHaveAttribute("href", "/pricing");
    expect(screen.queryByRole("button", { name: "CSV 다운로드" })).toBeNull();
    expect(screen.queryByRole("button", { name: "JSON 다운로드" })).toBeNull();

    await new Promise((r) => setTimeout(r, 0));
    expect(getCalls()).toBe(0);
  });

  it("Pro 플랜은 종목 분석 탭에 CSV/JSON 내보내기 버튼을 보여주고 클릭 시 export API 를 호출한다", async () => {
    const getCalls = renderWith("PRO");
    const user = userEvent.setup();

    expect(screen.queryByRole("button", { name: "백테스트 결과 익스포트" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "종목 분석" }));

    const csvButton = await screen.findByRole("button", { name: "CSV 내보내기" });
    const jsonButton = screen.getByRole("button", { name: "JSON 내보내기" });
    await vi.waitFor(() => expect(csvButton).not.toBeDisabled());

    expect(csvButton).toBeInTheDocument();
    expect(jsonButton).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "요금제 보기" })).toBeNull();

    await user.click(csvButton);
    await vi.waitFor(() => expect(getCalls()).toBe(1));
  });
});
