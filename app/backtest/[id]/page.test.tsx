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
      if (url === "/api/backtest/walk-forward/stream") {
        const encoder = new TextEncoder();
        const body = new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(`data: ${JSON.stringify({ type: "result", data: { status: "ok", n_splits: 4 } })}\n\n`)
            );
            controller.enqueue(encoder.encode("data: [DONE]\n\n"));
            controller.close();
          },
        });
        return Promise.resolve({ ok: true, body });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(<BacktestDetailPage />);

    const dashboard = await screen.findByTestId("backtest-dashboard");
    expect(dashboard).toHaveAttribute("data-has-dsl", "yes");

    await userEvent.click(await screen.findByRole("button", { name: "워크포워드 실행" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/backtest/walk-forward/stream",
        expect.objectContaining({ method: "POST" })
      );
    });

    const call = fetchMock.mock.calls.find(([url]) => url === "/api/backtest/walk-forward/stream");
    const body = JSON.parse((call?.[1]?.body as string) ?? "{}");
    expect(body).toMatchObject({
      n_splits: 4,
      method: "grid",
      ranges: { "risk.stop_loss_pct": expect.any(Array) },
    });
    // 저장 DSL에는 symbols가 없어도 백엔드 필수 필드로 빈 배열이 채워진다 (422 회귀 방지).
    expect(body.base_strategy.symbols).toEqual([]);
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

  it("settings가 없어도 결과에 저장된 실행 요청(executedRequest)이 있으면 재실행 DSL로 쓴다", async () => {
    // 회귀(2026-08-18): 원천 Strategy 행이 없는 기록에서 리밸런싱 기간별 비교 탭이
    // "요청이 저장되어 있지 않아 실행 불가"만 보였다. 기록 저장 시 result.executedRequest를 남기고
    // 이 페이지가 settings → executedRequest 순으로 폴백한다.
    fetchMock.mockImplementation((url: string) => {
      if (url === "/api/backtest/history/hist-1") {
        const base = baseHistoryResponse({ settings: null });
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...base,
            result: {
              ...(base.result as Record<string, unknown>),
              executedRequest: {
                symbols: ["005930"],
                entry: { conditions: [{ id: "pbr", params: { value: 1 } }] },
                exit: { conditions: [] },
                risk: { stop_loss_pct: 10, max_positions: 5 },
              },
            },
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(<BacktestDetailPage />);

    const dashboard = await screen.findByTestId("backtest-dashboard");
    expect(dashboard).toHaveAttribute("data-has-dsl", "yes");
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

  it("기록 조회 실패 상태에서 안내 영역을 중앙 정렬하고 돌아가기 버튼은 router.back을 호출한다", async () => {
    fetchMock.mockResolvedValue({ ok: false });

    render(<BacktestDetailPage />);

    const message = await screen.findByText("기록을 찾을 수 없습니다.");
    expect(message.parentElement).toHaveClass(
      "min-h-[calc(100vh-var(--top-menu-bar-height,76px))]",
      "justify-center",
      "text-center"
    );

    await userEvent.click(screen.getByRole("button", { name: "돌아가기" }));

    expect(routerBack).toHaveBeenCalledTimes(1);
  });

  it("상세 결과가 없는 기록도 안내 영역을 중앙 정렬한다", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => baseHistoryResponse({ result: null }),
    });

    render(<BacktestDetailPage />);

    const message = await screen.findByText("이 기록에는 상세 결과가 저장되어 있지 않습니다.");
    expect(message.parentElement).toHaveClass(
      "min-h-[calc(100vh-var(--top-menu-bar-height,76px))]",
      "justify-center",
      "text-center"
    );
  });
});
