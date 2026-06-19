import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BacktestHistoryPage from "./page";
import type { BacktestHistoryItem } from "@/types/strategy";

const push = vi.fn();
const fetchMock = vi.fn();

function makeHistoryItem(overrides: Partial<BacktestHistoryItem> = {}): BacktestHistoryItem {
  return {
    id: "history-1",
    timestamp: new Date("2026-06-19T07:20:00+09:00").getTime(),
    strategyName: "모멘텀 전략",
    universe: "KOSPI",
    conditions: {
      entry: { names: ["20일 신고가"] },
      exit: { names: ["손절"] },
      position: "동일 비중",
      risk: "손절 -8%",
    },
    metrics: {
      totalReturn: 12.3,
      cagr: 9.8,
      mdd: -4.5,
      winRate: 55,
      profitFactor: 1.4,
      buyHold: 3.2,
      trades: 18,
      executionTime: 1.23,
      score: 76,
    },
    ...overrides,
  };
}

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/strategy/StrategyWaveBackground", () => ({
  StrategyWaveBackground: () => <div>배경</div>,
}));

describe("BacktestHistoryPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [],
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  it("캐시된 빈 기록이 있으면 API 응답 전 empty state를 바로 보여준다", () => {
    window.sessionStorage.setItem("simons.backtestHistory", "[]");
    fetchMock.mockReturnValue(new Promise(() => {}));

    render(<BacktestHistoryPage />);

    expect(screen.getByRole("button", { name: "전략 만들기" })).toBeInTheDocument();
    expect(screen.queryByText("백테스트 기록")).not.toBeInTheDocument();
    expect(screen.queryByText("최근 50개 기록")).not.toBeInTheDocument();
  });

  it("저장된 백테스트가 없으면 empty state와 전략 생성 CTA를 보여준다", async () => {
    render(<BacktestHistoryPage />);

    const ctaButton = await screen.findByRole("button", { name: "전략 만들기" });

    await waitFor(() => {
      expect(document.body).toHaveTextContent("전략을 만들고");
      expect(document.body).toHaveTextContent("백테스트 해보세요");
    });
    expect(screen.queryByText("백테스트 기록")).not.toBeInTheDocument();
    expect(screen.queryByText("최근 50개 기록")).not.toBeInTheDocument();

    fireEvent.click(ctaButton);

    expect(push).toHaveBeenCalledWith("/analytics");
  });

  it("전략 카드 삭제 전에 확인 모달을 보여주고 확인 후 삭제한다", async () => {
    const historyItem = makeHistoryItem();
    window.sessionStorage.setItem("simons.backtestHistory", JSON.stringify([historyItem]));
    fetchMock.mockImplementation((url: string, options?: RequestInit) => {
      if (options?.method === "DELETE") {
        return Promise.resolve({ ok: true });
      }
      return new Promise(() => {});
    });

    render(<BacktestHistoryPage />);

    expect(screen.getByText("모멘텀 전략")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "모멘텀 전략 기록 삭제" }));

    const dialog = screen.getByRole("dialog", { name: "백테스트 기록을 삭제할까요?" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).queryByText("모멘텀 전략")).not.toBeInTheDocument();
    expect(within(dialog).getByText("백테스트 기록이 삭제됩니다. 삭제한 기록은 다시 복구할 수 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "삭제" }).className).toContain("border-white/[0.10]");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(screen.queryByRole("dialog", { name: "백테스트 기록을 삭제할까요?" })).not.toBeInTheDocument();
    expect(screen.getByText("모멘텀 전략")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "모멘텀 전략 기록 삭제" }));
    fireEvent.click(screen.getByRole("button", { name: "삭제" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/backtest/history?id=history-1", {
        method: "DELETE",
      });
      expect(screen.queryByText("모멘텀 전략")).not.toBeInTheDocument();
    });
  });
});
