import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MyStrategiesView from "./MyStrategiesView";

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

describe("MyStrategiesView", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("내 전략 화면은 저장된 전략 빈 상태를 보여준다", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ strategies: [] }),
    }));

    render(<MyStrategiesView />);


    expect(await screen.findByText("아직 저장된 전략이 없습니다")).toBeInTheDocument();
  });

  it("내 전략 로딩 중에는 빈 카드 placeholder를 보여주지 않는다", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    const { container } = render(<MyStrategiesView />);


    expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
  });

  it("내 전략 로딩 중에는 진행 표시를 보여주고 완료되면 감춘다", async () => {
    const user = userEvent.setup();
    let resolveFetch: ((value: unknown) => void) | undefined;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise((resolve) => {
      resolveFetch = resolve;
    })));

    render(<MyStrategiesView />);


    expect(screen.getByTestId("strategy-my-loading")).toBeInTheDocument();

    await act(async () => {
      resolveFetch?.({ ok: true, json: async () => ({ strategies: [] }) });
    });

    expect(screen.queryByTestId("strategy-my-loading")).not.toBeInTheDocument();
    expect(screen.getByText("아직 저장된 전략이 없습니다")).toBeInTheDocument();
  });

  it("내 전략 카드의 삭제 버튼을 누르면 DB 삭제 API를 호출하고 목록에서 제거한다", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === "/api/dashboard/strategy-list") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            strategies: [
              {
                id: "strategy-1",
                name: "급등주 전략",
                description: "최근 상승 종목 기반 전략",
                type: "모멘텀",
                universe: "KOSPI",
                aiScore: null,
                avgReturnPct: 0,
                accountCount: 0,
                createdAt: "2026-06-29T00:00:00.000Z",
              },
            ],
          }),
        });
      }
      if (url === "/api/strategy/strategy-1" && init?.method === "DELETE") {
        return Promise.resolve({ ok: true, json: async () => ({ ok: true }) });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MyStrategiesView />);


    expect(await screen.findByText("급등주 전략")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /급등주 전략/i })).toHaveAttribute("href", "/analytics/strategy-1");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "급등주 전략 전략 삭제" }));
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/strategy/strategy-1", { method: "DELETE" });
      expect(screen.queryByText("급등주 전략")).not.toBeInTheDocument();
    });
  });
});
