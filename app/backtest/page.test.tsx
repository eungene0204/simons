import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BacktestHistoryPage from "./page";

const push = vi.fn();
const fetchMock = vi.fn();

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
});
