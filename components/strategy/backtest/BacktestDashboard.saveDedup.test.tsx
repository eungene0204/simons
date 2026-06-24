// @ts-nocheck
/**
 * BacktestDashboard 저장 시 중복 히스토리 카드 회귀 테스트.
 *
 * 버그: result.cacheKey 가 없을 때 save-with-backtest 는 cacheKey 로 strategy.id 를
 * 폴백해 행을 만드는데(원본 DSL conditions = 배지 없음), 이어지는
 * /api/backtest/history POST 는 cacheKey 로 null 을 보내 별도 행을 만들었다.
 * → 같은 전략이 "배지 없는 카드 + 배지 카드" 두 장으로 중복 생성됨.
 *
 * 수정: 두 번째 POST 가 result.cacheKey ?? data.strategyId 를 cacheKey 로 보내
 * save-with-backtest 가 만든 행을 찾아 표시용 배지 conditions 로 갱신(중복 제거) → 회귀 고정.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
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

// result.cacheKey 를 일부러 비워 폴백 경로(중복 버그가 났던 경로)를 탄다.
const baseResult = {
  executionId: "exec-1",
  strategyId: "strat-1",
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

const STRATEGY_ID = "1:6cb4b5877d7a3e3e";

describe("BacktestDashboard 저장 — 히스토리 중복 카드 방지", () => {
  beforeEach(() => {
    cleanup();
  });

  it("result.cacheKey 가 없으면 두 번째 히스토리 POST 가 save-with-backtest 의 strategyId 를 cacheKey 로 써서 같은 행을 갱신한다", async () => {
    const historyPosts: any[] = [];

    const calledUrls: string[] = [];
    const fetchMock = vi.fn((url: string, init?: any) => {
      calledUrls.push(String(url));
      const body = init?.body ? JSON.parse(init.body) : undefined;
      if (typeof url === "string" && url.includes("/api/strategy/save-with-backtest")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategyId: STRATEGY_ID }) });
      }
      if (typeof url === "string" && url.includes("/api/backtest/history")) {
        historyPosts.push(body);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }
      // AI 리포트/종목명 등 그 외 fetch 는 빈 응답으로 무력화.
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <BacktestDashboard
        result={baseResult}
        onRestart={() => {}}
        disableHistorySave // 자동 저장 효과는 끄고 명시적 저장 경로만 검증
        promptText="pbr, roe 전략"
        backtestDsl={{ universe: { id: "KOSPI" }, entry: {}, exit: {} }}
        strategySummary={{
          strategyName: "pbr, roe 전략",
          universeName: "KOSPI",
          entryLogic: "AND",
          exitLogic: "AND",
          entryBlocks: ["PBR <= 1"],
          exitBlocks: ["익절 20% 이상 수익시 매도"],
          blockNames: ["PBR <= 1", "익절 20% 이상 수익시 매도"],
          positionText: "최대 5종목",
          riskText: "손절 10%, 익절 20%",
        }}
      />
    );

    const user = userEvent.setup();

    // 저장 모달 열기 → 이름 입력 → 저장
    await user.click(screen.getByRole("button", { name: /전략 저장/ }));
    const nameInput = await screen.findByPlaceholderText("전략 이름을 입력하세요");
    await user.type(nameInput, "pbr, roe 전략");
    // 모달의 저장 버튼(정확히 "저장" — 트리거 "전략 저장"과 구분).
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() => expect(historyPosts.length).toBeGreaterThan(0), { timeout: 3000 }).catch(() => {
      throw new Error("history POST 미발생. 호출된 URL: " + JSON.stringify(calledUrls));
    });

    const lastPost = historyPosts[historyPosts.length - 1];
    // 핵심: 두 번째 히스토리 POST 의 cacheKey 가 save-with-backtest 의 strategyId 와 같아야
    // 중복 행이 아니라 동일 행이 갱신된다.
    expect(lastPost.cacheKey).toBe(STRATEGY_ID);
    // 그리고 표시용 배지(names) conditions 로 갱신해야 한다.
    expect(lastPost.conditions.entry.names).toContain("PBR <= 1");
  });
});
