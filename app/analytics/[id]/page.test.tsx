import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, beforeEach, vi } from "vitest";
import StrategyResultPage from "./page";

const pushMock = vi.fn();
const backMock = vi.fn();
const fetchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "strategy-1" }),
  useRouter: () => ({
    push: pushMock,
    back: backMock,
  }),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/strategy/backtest/BacktestDashboard", () => ({
  default: ({
    promptText,
    strategySummary,
    onWalkForward,
    onRestart,
  }: {
    promptText?: string;
    strategySummary?: any;
    onWalkForward?: (settings: any) => Promise<any>;
    onRestart?: () => void;
  }) => (
    <div
      data-testid="backtest-dashboard"
      data-prompt={promptText ?? ""}
      data-entry-blocks={(strategySummary?.entryBlocks ?? []).join(",")}
      data-exit-blocks={(strategySummary?.exitBlocks ?? []).join(",")}
      data-position={strategySummary?.positionText ?? ""}
      data-risk={strategySummary?.riskText ?? ""}
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
            })
          }
        >
          워크포워드 실행
        </button>
      )}
    </div>
  ),
}));

describe("StrategyResultPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/strategy/strategy-1") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            name: "레거시 전략",
            description: "전략 이름처럼 보이는 fallback 설명",
            settings: {
              description: "KOSPI 대형주 중 PBR 1 이하만 골라서 전략을 만들어줘.",
              universe: { id: "kospi", filters: {} },
              entry: {
                conditions: [
                  {
                    id: "breakout",
                    type: "indicator",
                    params: { lookbackPeriod: 52, signalType: "buy" },
                  },
                ],
              },
              exit: { conditions: [] },
              risk: { max_positions: 3, init_cash: 10000000, stop_loss_pct: 12 },
            },
            historySummary: {
              strategyName: "레거시 전략",
              universeName: "KOSPI",
              entryBlocks: ["PBR <= 1"],
              exitBlocks: ["손절 -12% 하락시 매도"],
              positionText: "최대 8종목 · 126일 보유",
              riskText: "손절 12%",
            },
            backtestResult: {
              symbols: ["005930", "000660"],
              equity: [10000000, 10100000],
              dates: ["2025-01-01", "2025-01-02"],
              signals: [],
              aiStrengths: [],
              aiRisks: [],
            },
          }),
        });
      }

      if (url === "/api/backtest/run") {
        return Promise.resolve({
          ok: true,
          json: async () => ({}),
        });
      }

      if (url === "/api/backtest/walk-forward/stream") {
        const encoder = new TextEncoder();
        const resultEvent = JSON.stringify({
          type: "result",
          data: {
            status: "ok",
            windows: [],
            aggregate: {},
            combined_equity: [],
            combined_dates: [],
            walk_forward_efficiency: 0,
          },
        });
        return Promise.resolve({
          ok: true,
          body: new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode(`data: ${resultEvent}\n\ndata: [DONE]\n\n`));
              controller.close();
            },
          }),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);
  });

  it("전략 결과를 불러오는 동안 중앙 회전 인디케이터만 보여준다", () => {
    fetchMock.mockImplementation(() => new Promise<Response>(() => undefined));

    render(<StrategyResultPage />);

    const loadingIndicator = screen.getByRole("status", {
      name: "전략 결과 불러오는 중",
    });
    expect(loadingIndicator).toHaveClass(
      "min-h-[calc(100vh-var(--top-menu-bar-height,76px))]",
      "items-center",
      "justify-center"
    );
    expect(screen.queryByText("불러오는 중...")).not.toBeInTheDocument();
  });

  it("페이지 로드만으로는 백테스트를 자동 재실행하지 않는다", async () => {
    render(<StrategyResultPage />);

    expect(await screen.findByText("레거시 전략")).toBeInTheDocument();
    const dashboard = await screen.findByTestId("backtest-dashboard");
    expect(dashboard).toBeInTheDocument();
    expect(dashboard).toHaveAttribute(
      "data-prompt",
      "KOSPI 대형주 중 PBR 1 이하만 골라서 전략을 만들어줘."
    );
    expect(dashboard).toHaveAttribute("data-entry-blocks", "PBR <= 1");
    expect(dashboard).toHaveAttribute("data-exit-blocks", "손절 -12% 하락시 매도");
    expect(dashboard).toHaveAttribute("data-position", "최대 8종목 · 126일 보유");
    expect(dashboard).toHaveAttribute("data-risk", "손절 12%");
    expect(
      screen.getByText("기존 52일 breakout 버그가 감지되었습니다. 필요하면 재실행 버튼으로 252일 기준 결과를 다시 계산해 주세요.")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/strategy/strategy-1");
    });

    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/backtest/run",
      expect.anything()
    );
  });

  it("저장된 전략/전략모음에서 흘러온 경우 결과 닫기와 상단 뒤로가기는 전략연구소가 아닌 직전 화면으로 돌아간다", async () => {
    render(<StrategyResultPage />);

    await userEvent.click(await screen.findByRole("button", { name: "결과 닫기" }));
    expect(backMock).toHaveBeenCalledTimes(1);
    expect(pushMock).not.toHaveBeenCalledWith("/analytics");

    await userEvent.click(screen.getByRole("button", { name: "" }));
    expect(backMock).toHaveBeenCalledTimes(2);
  });

  it("저장된 전략 결과에서도 워크포워드 실행 핸들러를 전달한다", async () => {
    render(<StrategyResultPage />);

    await userEvent.click(await screen.findByRole("button", { name: "워크포워드 실행" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/backtest/walk-forward/stream",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
        })
      );
    });

    const walkForwardCall = fetchMock.mock.calls.find(([url]) => url === "/api/backtest/walk-forward/stream");
    expect(JSON.parse(walkForwardCall?.[1]?.body as string)).toMatchObject({
      n_splits: 4,
      train_pct: 0.7,
      anchor: false,
      target_metric: "cagr",
      n_trials: 20,
      ranges: {
        "risk.stop_loss_pct": expect.any(Array),
      },
    });
  });
});
