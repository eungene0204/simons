/**
 * '대화 종료'가 진행 중인 전략 분석 요청을 끊는다.
 *
 * 사용자가 분석 중('분석 중...' 로딩)에 '대화 종료'를 누르면
 *  - 진행 중인 fetch(분류·파싱·빌더 스텝)의 AbortSignal이 abort되고(프록시가 이를 백엔드로
 *    전파해 서버 쪽 LLM 작업도 멈춘다),
 *  - 끊긴 턴은 뒤처리(오류 버블·"조건을 한 번 더" 안내)를 하지 않아 새 대화가 오염되지 않으며,
 *  - 다음 대화의 요청은 새 토큰(끊기지 않은 signal)으로 나간다.
 */
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

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

// 실제 fetch처럼 동작하는 "응답 없는" 요청 — signal이 abort되면 AbortError로 reject된다.
function pendingUntilAborted(signal: AbortSignal | null | undefined): Promise<Response> {
  return new Promise((_, reject) => {
    if (!signal) return;
    const abort = () => reject(new DOMException("The operation was aborted.", "AbortError"));
    if (signal.aborted) abort();
    else signal.addEventListener("abort", abort, { once: true });
  });
}

async function submitPrompt(text: string) {
  fireEvent.change(await screen.findByRole("textbox"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
}

function clickEndChat() {
  fireEvent.click(screen.getAllByRole("button", { name: "대화 종료" })[0]);
}

describe("'대화 종료'가 진행 중인 분석 요청을 끊는다", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("파싱 중 '대화 종료'를 누르면 파싱 요청을 abort하고 오류 버블 없이 대화를 비운다", async () => {
    const parseSignals: Array<AbortSignal | null | undefined> = [];
    let classifyCallCount = 0;

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        classifyCallCount += 1;
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        parseSignals.push(init?.signal);
        // 백엔드 LLM이 생성 중 — 응답이 오지 않는다.
        return pendingUntilAborted(init?.signal);
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);
    await submitPrompt("PBR 1 이하 종목 10개 1년 보유");

    await waitFor(() => expect(parseSignals).toHaveLength(1));
    expect(parseSignals[0]).toBeInstanceOf(AbortSignal);
    expect(parseSignals[0]!.aborted).toBe(false);

    clickEndChat();

    // 진행 중이던 파싱 요청이 끊긴다 — 프록시가 백엔드 연결을 닫아 서버 작업도 멈춘다.
    expect(parseSignals[0]!.aborted).toBe(true);
    // 끊긴 턴의 뒤처리(오류 버블)가 새 대화에 그려지지 않는다.
    await waitFor(() => expect(screen.queryByText("PBR 1 이하 종목 10개 1년 보유")).not.toBeInTheDocument());
    expect(screen.queryByText("오류 발생")).not.toBeInTheDocument();
    expect(screen.queryByText("The operation was aborted.")).not.toBeInTheDocument();
    expect(push).toHaveBeenCalledWith("/analytics");

    // 다음 대화의 요청은 새 토큰으로 나간다(끊긴 signal을 재사용하지 않는다).
    await submitPrompt("PER 10 이하 종목 5개");
    await waitFor(() => expect(parseSignals).toHaveLength(2));
    expect(parseSignals[1]).not.toBe(parseSignals[0]);
    expect(parseSignals[1]!.aborted).toBe(false);
    expect(classifyCallCount).toBe(2);
    expect(screen.queryByText("오류 발생")).not.toBeInTheDocument();
  });

  it("빌더 스텝 중 '대화 종료'를 누르면 스텝 요청을 abort하고 '조건을 한 번 더' 안내를 그리지 않는다", async () => {
    const stepSignals: Array<AbortSignal | null | undefined> = [];
    let classifyCallCount = 0;

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        classifyCallCount += 1;
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_PICK", symbols: [] }));
      }
      if (url === "/api/strategy/builder/step") {
        stepSignals.push(init?.signal);
        // 시드 해석(검색 그라운딩·LLM) 중 — 응답이 오지 않는다.
        return pendingUntilAborted(init?.signal);
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);
    await submitPrompt("어떤 전략이 좋아?");

    await waitFor(() => expect(stepSignals).toHaveLength(1));
    expect(stepSignals[0]!.aborted).toBe(false);

    clickEndChat();

    expect(stepSignals[0]!.aborted).toBe(true);
    await waitFor(() => expect(screen.queryByText("어떤 전략이 좋아?")).not.toBeInTheDocument());
    // 빌더 호출 실패 폴백("어떤 시장을 대상으로 할까요?"·"조건을 한 번 더…")이 그려지지 않는다.
    expect(screen.queryByText(/어떤 시장을 대상으로 할까요/)).not.toBeInTheDocument();
    expect(screen.queryByText(/조건을 한 번 더 말씀해 주시겠어요/)).not.toBeInTheDocument();
    expect(screen.queryByText("오류 발생")).not.toBeInTheDocument();
    expect(classifyCallCount).toBe(1);
  });
});
