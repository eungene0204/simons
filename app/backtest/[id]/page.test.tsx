import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, beforeEach, vi } from "vitest";
import BacktestDetailPage from "./page";

const fetchMock = vi.fn();

const { routerBack, routerPush } = vi.hoisted(() => ({
  routerBack: vi.fn(),
  routerPush: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "hist-1" }),
  useRouter: () => ({ push: routerPush, back: routerBack }),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/strategy/backtest/BacktestDashboard", () => ({
  default: ({
    result,
    backtestDsl,
    onWalkForward,
    onRestart,
  }: {
    result?: any;
    backtestDsl?: any;
    onWalkForward?: (settings: any) => Promise<any>;
    onRestart?: () => void;
  }) => (
    <div
      data-testid="backtest-dashboard"
      data-has-dsl={backtestDsl ? "yes" : "no"}
      data-trades-count={result?.tradesList?.length ?? -1}
    >
      backtest dashboard
      {onRestart && (
        <button type="button" onClick={onRestart}>
          결과 닫기
        </button>
      )}
      {onWalkForward && (
        <button
          type="button"
          onClick={() =>
            onWalkForward({
              n_splits: 4,
              train_pct: 0.7,
              anchor: false,
              target_metric: "cagr",
              n_trials: 20,
              method: "grid",
            })
          }
        >
          워크포워드 실행
        </button>
      )}
    </div>
  ),
}));

function baseHistoryResponse(overrides: Record<string, unknown> = {}) {
  return {
    id: "hist-1",
    timestamp: Date.now(),
    strategyName: "저PBR 전략",
    prompt: "PBR 1 이하 매수",
    universe: "KOSPI",
    conditions: { entry: { names: ["PBR <= 1"] }, exit: { names: ["손절"] } },
    metrics: { totalReturn: 10, cagr: 8, mdd: -5, winRate: 50, profitFactor: 1.3, buyHold: 4, trades: 20 },
    result: {
      symbols: ["005930"],
      totalReturn: 10,
      cagr: 8,
      maxDrawdown: -5,
      winRate: 50,
      profitFactor: 1.3,
      sharpe: 1,
      trades: 20,
      finalEquity: 11_000_000,
      initialCapital: 10_000_000,
      equity: [10_000_000, 11_000_000],
      dates: ["2024-01-01", "2024-06-01"],
      tradesList: [],
      monthlyReturns: {},
      yearlyReturns: {},
      signals: [],
    },
    ...overrides,
  };
}

describe("BacktestDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("저장된 전략 settings가 있으면 워크포워드 실행 핸들러와 backtestDsl을 전달한다", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/backtest/history/hist-1") {
        return Promise.resolve({
          ok: true,
          json: async () =>
            baseHistoryResponse({
              settings: {
                risk: { stop_loss_pct: 10 },
                entry: { conditions: [{ id: "pbr", params: { value: 1 } }] },
              },
            }),
        });
      }
      if (url === "/api/backtest/walk-forward") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: "ok", n_splits: 4 }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(<BacktestDetailPage />);

    const dashboard = await screen.findByTestId("backtest-dashboard");
    expect(dashboard).toHaveAttribute("data-has-dsl", "yes");

    await userEvent.click(await screen.findByRole("button", { name: "워크포워드 실행" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/backtest/walk-forward",
        expect.objectContaining({ method: "POST" })
      );
    });

    const call = fetchMock.mock.calls.find(([url]) => url === "/api/backtest/walk-forward");
    const body = JSON.parse((call?.[1]?.body as string) ?? "{}");
    expect(body).toMatchObject({
      n_splits: 4,
      method: "grid",
      ranges: { "risk.stop_loss_pct": expect.any(Array) },
    });
  });

  it("저장된 전략 settings가 없으면 워크포워드 버튼을 노출하지 않는다", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/backtest/history/hist-1") {
        return Promise.resolve({
          ok: true,
          json: async () => baseHistoryResponse({ settings: null }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(<BacktestDetailPage />);

    const dashboard = await screen.findByTestId("backtest-dashboard");
    expect(dashboard).toHaveAttribute("data-has-dsl", "no");
    expect(screen.queryByRole("button", { name: "워크포워드 실행" })).not.toBeInTheDocument();
  });

  it("'결과 닫기'는 전략연구소가 아니라 직전 페이지로 돌아간다(router.back)", async () => {
    // 회귀: onRestart가 router.push("/analytics/new")로 배선돼 있어 닫기 시 항상
    // 전략연구소로 이동했다. 기록 상세는 목록 등 진입 경로로 돌아가야 한다.
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/backtest/history/hist-1") {
        return Promise.resolve({ ok: true, json: async () => baseHistoryResponse() });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(<BacktestDetailPage />);

    await userEvent.click(await screen.findByRole("button", { name: "결과 닫기" }));

    expect(routerBack).toHaveBeenCalledTimes(1);
    expect(routerPush).not.toHaveBeenCalled();
  });

  it("result.tradesList가 비어 있어도 signals로부터 매매 기록을 복원한다", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/backtest/history/hist-1") {
        return Promise.resolve({
          ok: true,
          json: async () => {
            const { tradesList, ...resultWithoutTradesList } = baseHistoryResponse().result as any;
            return baseHistoryResponse({
              result: {
                ...resultWithoutTradesList,
                signals: [
                  { date: "2024-01-02", symbol: "005930", type: "buy", price: 70000, quantity: 10, amount: 700000, condition: "PBR <= 1" },
                  { date: "2024-05-30", symbol: "005930", type: "sell", price: 77000, quantity: 10, amount: 770000, condition: "손절" },
                ],
              },
            });
          },
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(<BacktestDetailPage />);

    const dashboard = await screen.findByTestId("backtest-dashboard");
    expect(dashboard).toHaveAttribute("data-trades-count", "2");
  });
});
