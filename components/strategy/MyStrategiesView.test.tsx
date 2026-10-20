import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MyStrategiesView from "./MyStrategiesView";
import { invalidateMyStrategiesCache, setCachedMyStrategies } from "@/lib/my-strategies-cache";

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

describe("MyStrategiesView", () => {
  beforeEach(() => invalidateMyStrategiesCache());

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

  it("내 전략 카드의 공개 토글을 누르면 공개 전환 API를 호출하고 공개로 표시한다", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === "/api/dashboard/strategy-list") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            strategies: [
              {
                id: "strategy-1", name: "급등주 전략", description: null, type: "모멘텀", universe: "KOSPI",
                aiScore: null, avgReturnPct: 0, accountCount: 0, isPublic: false, createdAt: "2026-06-29T00:00:00.000Z",
              },
            ],
          }),
        });
      }
      if (url === "/api/strategy/strategy-1" && init?.method === "PATCH") {
        return Promise.resolve({ ok: true, json: async () => ({ id: "strategy-1", isPublic: true }) });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MyStrategiesView />);

    const toggle = await screen.findByRole("button", { name: "비공개" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await act(async () => {
      await user.click(toggle);
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/strategy/strategy-1", expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ isPublic: true }),
      }));
      expect(screen.getByRole("button", { name: "공개" })).toHaveAttribute("aria-pressed", "true");
    });
  });

  it("캐시가 있으면 로딩 없이 바로 목록을 그리고, 뒤에서 받은 최신 목록으로 교체한다", async () => {
    const item = (id: string, name: string) => ({
      id, name, description: null, type: "모멘텀", universe: "KOSPI", aiScore: null,
      avgReturnPct: 0, accountCount: 0, isPublic: false, createdAt: "2026-06-29T00:00:00.000Z",
    });
    setCachedMyStrategies([item("old", "캐시된 전략")]);
    let resolveFetch: (value: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise((resolve) => { resolveFetch = resolve; })));

    render(<MyStrategiesView />);

    // 서버 응답 전에도 캐시된 카드가 보이고 로딩 표시는 없다.
    expect(screen.getByText("캐시된 전략")).toBeInTheDocument();
    expect(screen.queryByTestId("strategy-my-loading")).not.toBeInTheDocument();

    await act(async () => {
      resolveFetch({ ok: true, json: async () => ({ strategies: [item("new", "최신 전략")] }) });
    });

    expect(await screen.findByText("최신 전략")).toBeInTheDocument();
    expect(screen.queryByText("캐시된 전략")).not.toBeInTheDocument();
  });

  it("캐시로 그린 뒤 새로고침이 실패해도 목록을 비우지 않는다", async () => {
    setCachedMyStrategies([{
      id: "old", name: "캐시된 전략", description: null, type: "모멘텀", universe: "KOSPI", aiScore: null,
      avgReturnPct: 0, accountCount: 0, isPublic: false, createdAt: "2026-06-29T00:00:00.000Z",
    }]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }));

    render(<MyStrategiesView />);

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getByText("캐시된 전략")).toBeInTheDocument();
    expect(screen.queryByText("전략 목록을 불러올 수 없습니다")).not.toBeInTheDocument();
  });

  it("삭제 요청 중에는 카드에 진행 표시(스피너·'삭제 중...')를 보이고 끝나면 카드가 사라진다", async () => {
    const user = userEvent.setup();
    let resolveDelete: (value: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (url === "/api/dashboard/strategy-list") {
        return Promise.resolve({ ok: true, json: async () => ({ strategies: [{
          id: "strategy-1", name: "급등주 전략", description: null, type: "모멘텀", universe: "KOSPI",
          aiScore: null, avgReturnPct: 0, accountCount: 0, isPublic: false, createdAt: "2026-06-29T00:00:00.000Z",
        }] }) });
      }
      if (init?.method === "DELETE") return new Promise((resolve) => { resolveDelete = resolve; });
      return Promise.resolve({ ok: false, json: async () => ({}) });
    }));

    render(<MyStrategiesView />);
    const deleteButton = await screen.findByRole("button", { name: "급등주 전략 전략 삭제" });
    await act(async () => {
      await user.click(deleteButton);
    });

    expect(screen.getByText("삭제 중...")).toBeInTheDocument();
    expect(screen.getByTestId("strategy-deleting")).toHaveAttribute("aria-busy", "true");

    await act(async () => {
      resolveDelete({ ok: true, json: async () => ({ ok: true }) });
    });
    await waitFor(() => expect(screen.queryByText("급등주 전략")).not.toBeInTheDocument());
  });
});
