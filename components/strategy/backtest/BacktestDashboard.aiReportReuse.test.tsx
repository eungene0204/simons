// @ts-nocheck
/**
 * BacktestDashboard AI 리포트 백그라운드 생성 재사용 회귀 테스트.
 *
 * 버그: 백테스트 완료 직후 AI 리포트를 백그라운드에서 생성하기 시작하는데,
 * 사용자가 그 사이에 저장을 누르면 handleSaveStrategy 가 cachedAiSummary 가
 * 아직 비어있다는 이유로 /api/backtest/summarize 를 한 번 더(처음부터) 호출했다.
 * → 동일한 무거운 LLM 요청 2회 + 저장이 새 요청 완료까지 불필요하게 대기.
 *
 * 수정: 진행 중인 생성 약속(aiReportPromiseRef)을 저장 경로가 그대로 재사용한다.
 * → summarize 는 정확히 1회만 호출되고, 이미 끝났다면 즉시 저장된다.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

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
  dates: [],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

const SUMMARY_RESPONSE = {
  summary: "과거 데이터 기준 시뮬레이션 결과입니다.",
  score: 62,
  strengths: ["거래 횟수 안정"],
  weaknesses: ["변동성 높음"],
  improvements: ["손절 추가 검토"],
  advisorScore: 55,
  riskScore: 40,
  overfitRisk: "low",
};

describe("BacktestDashboard 저장 — 백그라운드 AI 리포트 재사용", () => {
  beforeEach(() => {
    cleanup();
  });

  it("저장 시 진행 중인 summarize 를 재사용해 중복 호출하지 않는다", async () => {
    let summarizeCalls = 0;
    // summarize 를 의도적으로 늦게 resolve → 저장 시점에 in-flight 상태로 만든다.
    let resolveSummarize: (v: any) => void = () => {};
    const summarizePromise = new Promise((r) => {
      resolveSummarize = r;
    });

    const fetchMock = vi.fn((url: string, init?: any) => {
      if (typeof url === "string" && url.includes("/api/backtest/summarize")) {
        summarizeCalls += 1;
        return summarizePromise.then(() => ({
          ok: true,
          json: () => Promise.resolve(SUMMARY_RESPONSE),
        }));
      }
      if (typeof url === "string" && url.includes("/api/strategy/save-with-backtest")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategyId: "strat-1" }) });
      }
      // AI 리포트는 프로/프리미엄 전용 — 백그라운드 생성이 돌려면 유료 플랜이어야 한다.
      if (typeof url === "string" && url.includes("/api/user/plan")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ plan: { planId: "PRO" } }) });
      }
      // ai-report PATCH / history / 종목명 등은 빈 응답.
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <BacktestDashboard
        result={baseResult}
        onRestart={() => {}}
        disableHistorySave
        promptText="pbr, roe 전략"
        backtestDsl={{ universe: { id: "KOSPI" }, entry: {}, exit: {} }}
        strategySummary={{
          strategyName: "pbr, roe 전략",
          universeName: "KOSPI",
          entryLogic: "AND",
          exitLogic: "AND",
          entryBlocks: ["PBR <= 1"],
          exitBlocks: ["익절 20% 이상"],
          blockNames: ["PBR <= 1", "익절 20% 이상"],
          positionText: "최대 5종목",
          riskText: "손절 10%",
        }}
      />
    );

    const user = userEvent.setup();

    // 마운트 직후 백그라운드 생성이 시작됐는지 확인.
    await waitFor(() => expect(summarizeCalls).toBe(1));

    // 아직 summarize 가 끝나지 않은 상태에서 저장 시도.
    await user.click(screen.getByRole("button", { name: /전략 저장/ }));
    const nameInput = await screen.findByPlaceholderText("전략 이름을 입력하세요");
    await user.type(nameInput, "pbr, roe 전략");
    await user.click(screen.getByRole("button", { name: "저장" }));

    // 백그라운드 요청을 완료시킨다 → 저장이 같은 결과로 진행되어야 한다.
    resolveSummarize(undefined);

    await waitFor(() =>
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("/api/strategy/save-with-backtest"))).toBe(true)
    );

    // 핵심: summarize 는 정확히 1회만 호출(중복 없음).
    expect(summarizeCalls).toBe(1);

    // 저장 요청에 백그라운드에서 받은 AI 리포트가 실려야 한다.
    const saveCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes("/api/strategy/save-with-backtest")
    );
    const savedBody = JSON.parse(saveCall![1].body);
    expect(savedBody.aiSummary).toBe(SUMMARY_RESPONSE.summary);
    expect(savedBody.aiScore).toBe(SUMMARY_RESPONSE.score);
  });
});
