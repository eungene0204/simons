/**
 * 우측 대화 로그 — 지나간 대화를 목록으로 보여주고, 누르면 그 대화를 되살리고, 지울 수 있다.
 *  - 목록은 채팅 화면에서만, 지금 지역(KR/US)의 대화만 보인다.
 *  - 진행 중인 대화는 저장될 때 로그에도 같이 남는다.
 */
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";
import { STRATEGY_CHAT_STATE_KEY } from "@/components/strategy/strategyTemplateSession";
import { readChatLog, upsertChatLogEntry } from "./chatLog";

const push = vi.fn();
const fetchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/analytics/chat",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/strategy/StrategyExampleTabs", () => ({
  StrategyExampleTabs: () => <div>예시 전략</div>,
}));

vi.mock("@/components/strategy/StrategyWaveBackground", () => ({
  StrategyWaveBackground: () => <div>배경</div>,
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      signInWithOAuth: vi.fn(),
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  }),
}));

function createJsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function snapshot(id: string, question: string, answer: string) {
  return {
    messages: [
      { role: "user", content: question },
      { role: "assistant", infoText: answer },
    ],
    stage: "ready",
    qaSessionId: id,
  };
}

function seedLog() {
  upsertChatLogEntry(localStorage, { id: "a", region: "kr", snapshot: snapshot("a", "지난 대화 A", "A 답변"), now: 1 });
  upsertChatLogEntry(localStorage, { id: "b", region: "kr", snapshot: snapshot("b", "지난 대화 B", "B 답변"), now: 2 });
  upsertChatLogEntry(localStorage, { id: "u", region: "us", snapshot: snapshot("u", "US chat", "US answer"), now: 3 });
}

function seedCurrentChat() {
  sessionStorage.setItem(
    STRATEGY_CHAT_STATE_KEY,
    JSON.stringify(snapshot("cur", "현재 대화", "현재 답변")),
  );
}

describe("우측 대화 로그", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: null }));
      }
      return Promise.resolve(createJsonResponse({}));
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("채팅 화면에서 지금 지역의 지난 대화만 보이고, 진행 중인 대화도 로그에 남는다", async () => {
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);

    expect(await screen.findByText("현재 답변")).toBeInTheDocument();
    const panel = screen.getByTestId("chat-log-panel");
    const list = within(panel).getByTestId("chat-log-list");
    expect(within(list).getByRole("button", { name: "지난 대화 A" })).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "지난 대화 B" })).toBeInTheDocument();
    expect(within(list).queryByText("US chat")).not.toBeInTheDocument();

    // 복원된 현재 대화는 저장 효과를 거쳐 로그 맨 위에 올라온다.
    await waitFor(() => {
      expect(within(list).getByRole("button", { name: "현재 대화" })).toHaveAttribute(
        "aria-current",
        "true",
      );
    });
    expect(readChatLog(localStorage).map((e) => e.id)).toEqual(["cur", "u", "b", "a"]);
  });

  it("대화 로그가 비어 있으면 패널을 그리지 않는다", async () => {
    seedCurrentChat();
    render(<StrategyLabPage />);
    expect(await screen.findByText("현재 답변")).toBeInTheDocument();
    // 현재 대화가 저장되면 그 한 건으로 패널이 생긴다 — 그 전에는 없다.
    await waitFor(() => expect(screen.getByTestId("chat-log-panel")).toBeInTheDocument());
    localStorage.clear();
  });

  it("지난 대화를 누르면 그 대화가 화면에 되살아나고 세션 저장도 그 대화로 바뀐다", async () => {
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);
    expect(await screen.findByText("현재 답변")).toBeInTheDocument();

    const list = within(screen.getByTestId("chat-log-panel")).getByTestId("chat-log-list");
    fireEvent.click(within(list).getByRole("button", { name: "지난 대화 A" }));

    expect(await screen.findByText("A 답변")).toBeInTheDocument();
    expect(screen.queryByText("현재 답변")).not.toBeInTheDocument();
    await waitFor(() => {
      const saved = JSON.parse(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY) ?? "{}");
      expect(saved.qaSessionId).toBe("a");
    });
    expect(within(list).getByRole("button", { name: "지난 대화 A" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    // 열어 보기만 한 대화는 순서가 바뀌지 않는다.
    expect(readChatLog(localStorage).map((e) => e.id)).toEqual(["cur", "u", "b", "a"]);
  });

  it("지난 대화를 지우면 목록과 저장소에서 빠진다", async () => {
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);
    expect(await screen.findByText("현재 답변")).toBeInTheDocument();

    const list = within(screen.getByTestId("chat-log-panel")).getByTestId("chat-log-list");
    fireEvent.click(within(list).getByRole("button", { name: "지난 대화 B 대화 삭제" }));

    await waitFor(() => {
      expect(within(list).queryByRole("button", { name: "지난 대화 B" })).not.toBeInTheDocument();
    });
    expect(readChatLog(localStorage).map((e) => e.id)).not.toContain("b");
    // 현재 대화는 그대로다.
    expect(screen.getByText("현재 답변")).toBeInTheDocument();
  });

  it("보고 있는 대화를 지우면 화면도 비운다", async () => {
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);
    expect(await screen.findByText("현재 답변")).toBeInTheDocument();
    const list = within(screen.getByTestId("chat-log-panel")).getByTestId("chat-log-list");
    const deleteCurrent = await within(list).findByRole("button", { name: "현재 대화 대화 삭제" });

    fireEvent.click(deleteCurrent);

    await waitFor(() => expect(screen.queryByText("현재 답변")).not.toBeInTheDocument());
    expect(readChatLog(localStorage).map((e) => e.id)).not.toContain("cur");
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBeNull();
  });
});
