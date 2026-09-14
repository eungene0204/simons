/**
 * 왼쪽 대화 로그 — 계정별 서버 저장(`/api/strategy-chat-log`)을 목록으로 보여주고, 누르면 그 대화를
 * 서버에서 받아 되살리고, 지울 수 있다.
 *  - 목록은 채팅 화면에서만, 지금 지역(KR/US)의 대화만 보인다.
 *  - 진행 중인 대화는 갱신이 멎은 뒤 한 번 서버에 저장되고 목록 맨 위에 올라온다.
 *  - 저장된 대화는 계정의 것만 보인다(2026-09-14 게스트 계정 사고).
 */
import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";
import { STRATEGY_CHAT_STATE_KEY } from "@/components/strategy/strategyTemplateSession";
import { STRATEGY_CHAT_OWNER_KEY } from "@/components/strategy/strategyChatStorage";
import { deriveChatLogTitle, type ChatLogEntry, type ChatLogSnapshot } from "./chatLog";
import { __resetLanguageForTests, setLanguage } from "@/lib/i18n";

const push = vi.fn();
const fetchMock = vi.fn();
// 저장 settle(1.5초)을 기다리는 대기 상한.
const SAVE_WAIT = { timeout: 4000 };

// 로그인 사용자 — 서버 저장소는 사용자 id별로 나뉜다. null = 비로그인.
let currentUser: { id: number; name: string } | null = { id: 1, name: "Tester" };

// 서버(DB)를 흉내 내는 사용자별 저장소 — 라우트와 같은 규칙(사용자로 묶기, 최근 사용 순).
type StoredEntry = { entry: ChatLogEntry; snapshot: ChatLogSnapshot };
const store = new Map<number, Map<string, StoredEntry>>();
const userStore = (userId: number) => {
  if (!store.has(userId)) store.set(userId, new Map());
  return store.get(userId)!;
};
const listOf = (userId: number) =>
  [...userStore(userId).values()].map((s) => s.entry).sort((a, b) => b.updatedAt - a.updatedAt);
const putCalls: string[] = [];

// 지역은 브라우저 경로에서 파생된다(`/us/...` = US) — 케이스마다 바꿔 끼운다.
let pathname = "/analytics/chat";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => pathname,
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

function createJsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function snapshot(id: string, question: string, answer: string): ChatLogSnapshot {
  return {
    messages: [
      { role: "user", content: question },
      { role: "assistant", infoText: answer } as ChatLogSnapshot["messages"][number],
    ],
    stage: "ready",
    qaSessionId: id,
  };
}

function seedEntry(userId: number, id: string, region: "kr" | "us", snap: ChatLogSnapshot, now: number) {
  userStore(userId).set(id, {
    snapshot: snap,
    entry: {
      id,
      region,
      title: deriveChatLogTitle(snap.messages),
      messageCount: snap.messages.length,
      createdAt: now,
      updatedAt: now,
    },
  });
}

function seedLog(userId = 1) {
  seedEntry(userId, "a", "kr", snapshot("a", "지난 대화 A", "A 답변"), 1);
  seedEntry(userId, "b", "kr", snapshot("b", "지난 대화 B", "B 답변"), 2);
  seedEntry(userId, "u", "us", snapshot("u", "US chat", "US answer"), 3);
}

function seedCurrentChat(owner = "1") {
  sessionStorage.setItem(STRATEGY_CHAT_OWNER_KEY, owner);
  sessionStorage.setItem(
    STRATEGY_CHAT_STATE_KEY,
    JSON.stringify(snapshot("cur", "현재 대화", "현재 답변")),
  );
}

async function handleChatLogApi(url: string, init?: RequestInit): Promise<Response | null> {
  const match = url.match(/^\/api\/strategy-chat-log(?:\/([^/]+))?$/);
  if (!match) return null;
  if (!currentUser) return createJsonResponse({ error: "Unauthorized" }, 401);
  const users = userStore(currentUser.id);
  const id = match[1] ? decodeURIComponent(match[1]) : null;
  const method = init?.method ?? "GET";
  if (!id) return createJsonResponse({ entries: listOf(currentUser.id) });
  if (method === "GET") {
    const found = users.get(id);
    return found ? createJsonResponse({ snapshot: found.snapshot }) : createJsonResponse({ error: "Not found" }, 404);
  }
  if (method === "PUT") {
    putCalls.push(id);
    const body = JSON.parse(String(init?.body)) as { region: "kr" | "us"; snapshot: ChatLogSnapshot };
    const prev = users.get(id);
    const messageCount = body.snapshot.messages.length;
    const advanced = !prev || prev.entry.messageCount !== messageCount;
    const now = Date.now();
    users.set(id, {
      snapshot: body.snapshot,
      entry: {
        id,
        region: body.region,
        title: deriveChatLogTitle(body.snapshot.messages),
        messageCount,
        createdAt: prev?.entry.createdAt ?? now,
        updatedAt: advanced ? now : prev.entry.updatedAt,
      },
    });
    return createJsonResponse({ entries: listOf(currentUser.id) });
  }
  if (method === "DELETE") {
    users.delete(id);
    return createJsonResponse({ entries: listOf(currentUser.id) });
  }
  return createJsonResponse({ error: "Method" }, 405);
}

describe("왼쪽 대화 로그", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    pathname = "/analytics/chat";
    currentUser = { id: 1, name: "Tester" };
    store.clear();
    putCalls.length = 0;
    sessionStorage.clear();
    localStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/model/status") return createJsonResponse({ status: "ready", error: null });
      if (url === "/api/user") return createJsonResponse({ user: currentUser });
      return (await handleChatLogApi(url, init)) ?? createJsonResponse({});
    });
  });

  afterEach(() => {
    // 언마운트가 남은 저장분을 keepalive로 보내므로, fetch 목이 살아 있을 때 먼저 내린다.
    cleanup();
    vi.unstubAllGlobals();
    __resetLanguageForTests();
  });

  it("채팅 화면에서 지금 지역의 지난 대화만 보이고, 진행 중인 대화도 서버 로그에 남는다", async () => {
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);

    expect(await screen.findByText("현재 답변")).toBeInTheDocument();
    const panel = await screen.findByTestId("chat-log-panel");
    const list = within(panel).getByTestId("chat-log-list");
    expect(within(list).getByRole("button", { name: "지난 대화 A" })).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "지난 대화 B" })).toBeInTheDocument();
    expect(within(list).queryByText("US chat")).not.toBeInTheDocument();

    // 복원된 현재 대화는 갱신이 멎은 뒤 서버에 저장돼 로그 맨 위에 올라온다.
    await waitFor(() => {
      expect(within(list).getByRole("button", { name: "현재 대화" })).toHaveAttribute("aria-current", "true");
    }, SAVE_WAIT);
    expect(listOf(1).map((e) => e.id)).toEqual(["cur", "u", "b", "a"]);
    // 스트리밍 갱신마다 쓰지 않는다 — 복원 한 번에 저장 한 번.
    expect(putCalls).toEqual(["cur"]);
  });

  it("접기 아이콘을 누르면 왼쪽 패널이 손잡이로 접히고, 다시 누르면 펼쳐진다", async () => {
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);
    expect(await screen.findByText("현재 답변")).toBeInTheDocument();
    await screen.findByTestId("chat-log-panel");

    fireEvent.click(screen.getByTestId("chat-log-rail-collapse"));
    expect(screen.queryByTestId("chat-log-panel")).not.toBeInTheDocument();

    const handle = screen.getByTestId("chat-log-rail-trigger");
    fireEvent.click(handle);
    expect(screen.getByTestId("chat-log-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("chat-log-rail-trigger")).not.toBeInTheDocument();
  });

  // 2026-09-14 사고: 게스트 계정으로 들어갔더니 같은 브라우저에서 먼저 쓰던 계정의 대화 기록이
  // 그대로 보였다. 목록은 서버가 세션 사용자로 묶어 주고, 브라우저에 남은 스냅샷은 주인이
  // 다르면 지운다.
  it("다른 계정의 대화 로그는 보이지 않고, 브라우저에 남은 그 계정의 스냅샷은 지워진다", async () => {
    seedLog(1);
    seedCurrentChat("1");
    currentUser = { id: 2, name: "Guest" };
    render(<StrategyLabPage />);

    await waitFor(() => expect(sessionStorage.getItem(STRATEGY_CHAT_OWNER_KEY)).toBe("2"));
    expect(screen.queryByText("현재 답변")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chat-log-panel")).not.toBeInTheDocument();
    expect(screen.queryByText("지난 대화 A")).not.toBeInTheDocument();
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBeNull();
    // 서버의 1번 사용자 기록은 그대로다 — 2번에게 안 보일 뿐 지우지 않는다.
    expect(listOf(1)).toHaveLength(3);
  });

  it("비로그인 방문자는 목록을 요청하지 않고 남아 있는 스냅샷을 지운다", async () => {
    seedCurrentChat("1");
    currentUser = null;
    render(<StrategyLabPage />);

    await waitFor(() => expect(sessionStorage.getItem(STRATEGY_CHAT_OWNER_KEY)).toBeNull());
    expect(screen.queryByText("현재 답변")).not.toBeInTheDocument();
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBeNull();
    expect(fetchMock.mock.calls.some(([u]) => String(u).startsWith("/api/strategy-chat-log"))).toBe(false);
  });

  it("주인 표식 없이 저장된(수정 전) 스냅샷은 로그인 계정에게도 복원하지 않는다", async () => {
    seedCurrentChat("1");
    sessionStorage.removeItem(STRATEGY_CHAT_OWNER_KEY);
    render(<StrategyLabPage />);

    await waitFor(() => expect(sessionStorage.getItem(STRATEGY_CHAT_OWNER_KEY)).toBe("1"));
    expect(screen.queryByText("현재 답변")).not.toBeInTheDocument();
  });

  it("대화 로그가 비어 있으면 패널을 그리지 않는다", async () => {
    seedCurrentChat();
    render(<StrategyLabPage />);
    expect(await screen.findByText("현재 답변")).toBeInTheDocument();
    expect(screen.queryByTestId("chat-log-panel")).not.toBeInTheDocument();
    // 현재 대화가 저장되면 그 한 건으로 패널이 생긴다 — 그 전에는 없다.
    await waitFor(() => expect(screen.getByTestId("chat-log-panel")).toBeInTheDocument(), SAVE_WAIT);
  });

  it("지난 대화를 누르면 서버에서 받은 스냅샷이 화면에 되살아나고 세션 저장도 그 대화로 바뀐다", async () => {
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);
    expect(await screen.findByText("현재 답변")).toBeInTheDocument();

    const list = within(await screen.findByTestId("chat-log-panel")).getByTestId("chat-log-list");
    fireEvent.click(within(list).getByRole("button", { name: "지난 대화 A" }));

    expect(await screen.findByText("A 답변")).toBeInTheDocument();
    expect(screen.queryByText("현재 답변")).not.toBeInTheDocument();
    await waitFor(() => {
      const saved = JSON.parse(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY) ?? "{}");
      expect(saved.qaSessionId).toBe("a");
    });
    await waitFor(() => {
      expect(within(list).getByRole("button", { name: "지난 대화 A" })).toHaveAttribute("aria-current", "true");
    }, SAVE_WAIT);
    // 열기 전에 현재 대화의 남은 저장분을 먼저 보낸다 — 현재 대화를 잃지 않는다.
    expect(putCalls[0]).toBe("cur");
    // 열어 보기만 한 대화(메시지 수 그대로)는 순서가 바뀌지 않는다.
    await waitFor(() => expect(putCalls).toContain("a"), SAVE_WAIT);
    expect(listOf(1).map((e) => e.id)).toEqual(["cur", "u", "b", "a"]);
  });

  it("지난 대화를 지우면 목록과 서버에서 빠진다", async () => {
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);
    expect(await screen.findByText("현재 답변")).toBeInTheDocument();

    const list = within(await screen.findByTestId("chat-log-panel")).getByTestId("chat-log-list");
    fireEvent.click(within(list).getByRole("button", { name: "지난 대화 B 대화 삭제" }));

    await waitFor(() => {
      expect(within(list).queryByRole("button", { name: "지난 대화 B" })).not.toBeInTheDocument();
    });
    await waitFor(() => expect(listOf(1).map((e) => e.id)).not.toContain("b"));
    // 현재 대화는 그대로다.
    expect(screen.getByText("현재 답변")).toBeInTheDocument();
  });

  it("보고 있는 대화를 지우면 화면도 비우고, 보내지 않은 저장분도 버려 되살아나지 않는다", async () => {
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);
    expect(await screen.findByText("현재 답변")).toBeInTheDocument();
    const list = within(await screen.findByTestId("chat-log-panel")).getByTestId("chat-log-list");
    const deleteCurrent = await within(list).findByRole("button", { name: "현재 대화 대화 삭제" }, SAVE_WAIT);

    fireEvent.click(deleteCurrent);

    await waitFor(() => expect(screen.queryByText("현재 답변")).not.toBeInTheDocument());
    await waitFor(() => expect(listOf(1).map((e) => e.id)).not.toContain("cur"));
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 1700));
    expect(listOf(1).map((e) => e.id)).not.toContain("cur");
  });

  // /us는 미들웨어 rewrite로 같은 라우트를 쓴다 — 대화 로그도 같은 컴포넌트가 그리되,
  // 지역이 섞이면 안 된다(US 화면에 한국 대화가 뜨면 격리 계약 위반). 라벨은 영어 사전.
  it("/us에서는 US 대화만 보이고 라벨이 영어로 나온다", async () => {
    pathname = "/us/analytics/chat";
    // 표시 언어는 실제로는 브라우저 경로에서 파생되는데(getLanguage), jsdom의
    // window.location은 "/"라 경로 mock만으로는 en으로 넘어가지 않는다 — 다른 영어 화면
    // 테스트와 같은 방식으로 명시 지정한다(LanguageProvider가 하는 일과 같다).
    setLanguage("en");
    seedLog();
    seedCurrentChat();
    render(<StrategyLabPage />);

    expect(await screen.findByText("현재 답변")).toBeInTheDocument();
    const list = within(await screen.findByTestId("chat-log-panel")).getByTestId("chat-log-list");
    expect(within(list).getByRole("button", { name: "US chat" })).toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: "지난 대화 A" })).not.toBeInTheDocument();
    expect(within(list).queryByRole("button", { name: "지난 대화 B" })).not.toBeInTheDocument();

    // 패널 제목·삭제 버튼 라벨이 en.ts 사전을 탄다.
    expect(screen.getByRole("complementary", { name: "Chat history" })).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Delete chat: US chat" })).toBeInTheDocument();

    // 지금 진행 중인 대화는 US 지역으로 기록돼 이 화면에 남는다.
    await waitFor(() => {
      expect(listOf(1).find((e) => e.id === "cur")?.region).toBe("us");
    }, SAVE_WAIT);
    expect(within(list).getByRole("button", { name: "현재 대화" })).toHaveAttribute("aria-current", "true");
  });
});
