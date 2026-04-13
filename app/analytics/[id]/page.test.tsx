import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import StrategyResultPage from "./page";

const pushMock = vi.fn();
const fetchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "strategy-1" }),
  useRouter: () => ({
    push: pushMock,
  }),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/strategy/backtest/BacktestDashboard", () => ({
  default: () => <div data-testid="backtest-dashboard">backtest dashboard</div>,
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
            settings: {
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
              risk: { max_positions: 3, init_cash: 10000000 },
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

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);
  });

  it("페이지 로드만으로는 백테스트를 자동 재실행하지 않는다", async () => {
    render(<StrategyResultPage />);

    expect(await screen.findByText("레거시 전략")).toBeInTheDocument();
    expect(await screen.findByTestId("backtest-dashboard")).toBeInTheDocument();
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
});
