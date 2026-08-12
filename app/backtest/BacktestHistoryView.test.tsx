import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BacktestHistoryView from "./BacktestHistoryView";
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

describe("BacktestHistoryView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue({ ok: true });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("서버가 넘긴 목록을 첫 렌더에 바로 그리고 목록을 다시 요청하지 않는다", () => {
    render(<BacktestHistoryView initialHistory={[makeHistoryItem()]} />);

    expect(screen.getByText("모멘텀 전략")).toBeInTheDocument();
    expect(screen.queryByTestId("backtest-history-loading")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("저장된 백테스트가 없으면 empty state와 전략 생성 CTA를 보여준다", async () => {
    render(<BacktestHistoryView initialHistory={[]} />);

    const ctaButton = await screen.findByRole("button", { name: "전략 만들기" });

    await waitFor(() => {
      expect(document.body).toHaveTextContent("전략을 만들고");
      expect(document.body).toHaveTextContent("백테스트 해보세요");
    });
    expect(screen.queryByText("전략 백테스트 기록")).not.toBeInTheDocument();
    expect(screen.queryByText("최근 50개 기록")).not.toBeInTheDocument();

    fireEvent.click(ctaButton);

    expect(push).toHaveBeenCalledWith("/analytics");
  });

  it("모바일 카드 헤더를 세로 배치하고 데스크톱 레이아웃을 복원한다", async () => {
    render(<BacktestHistoryView initialHistory={[makeHistoryItem()]} />);

    expect(await screen.findByTestId("backtest-history-page")).toHaveClass(
      "p-3",
      "sm:p-4",
      "lg:p-6"
    );
    expect(screen.getByTestId("backtest-history-card")).toHaveClass(
      "p-4",
      "lg:p-5"
    );
    expect(screen.getByTestId("backtest-history-card-header")).toHaveClass(
      "flex-col",
      "lg:flex-row"
    );
    expect(screen.getByRole("button", { name: "모멘텀 전략 기록 삭제" })).toHaveClass(
      "opacity-100",
      "lg:opacity-0",
      "lg:group-hover:opacity-100"
    );
  });

  it("전략 카드를 클릭하면 로딩 인디케이터를 보여주고 상세 페이지로 이동한다", async () => {
    render(<BacktestHistoryView initialHistory={[makeHistoryItem()]} />);

    const card = await screen.findByTestId("backtest-history-card");
    expect(screen.queryByTestId("backtest-history-card-loading")).not.toBeInTheDocument();

    fireEvent.click(card);

    expect(screen.getByTestId("backtest-history-card-loading")).toBeInTheDocument();
    expect(push).toHaveBeenCalledWith("/backtest/history-1");
    expect(push).toHaveBeenCalledTimes(1);

    fireEvent.click(card);
    expect(push).toHaveBeenCalledTimes(1);
  });

  it("전략 카드 삭제 전에 확인 모달을 보여주고 확인 후 삭제한다", async () => {
    render(<BacktestHistoryView initialHistory={[makeHistoryItem()]} />);

    expect(await screen.findByRole("heading", { name: "전략 백테스트 기록" })).toBeInTheDocument();
    expect(screen.getByText("모멘텀 전략")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "기록 전체 삭제" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "모멘텀 전략 기록 삭제" }));

    const dialog = screen.getByRole("dialog", { name: "백테스트 기록을 삭제할까요?" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).queryByText("모멘텀 전략")).not.toBeInTheDocument();
    expect(within(dialog).getByText("백테스트 기록이 삭제됩니다. 삭제한 기록은 다시 복구할 수 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "삭제" }).className).toContain("border-white/[0.10]");
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(screen.queryByRole("dialog", { name: "백테스트 기록을 삭제할까요?" })).not.toBeInTheDocument();
    expect(screen.getByText("모멘텀 전략")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

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
