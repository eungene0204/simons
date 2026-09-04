import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

const fetchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
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

// 백엔드 정본(engine/strategy_slots.py ENTRY)의 매수 조건 질문·칩.
const ENTRY_QUESTION = "다음으로 어떤 조건에서 매수할지 정해볼까요?";
const ENTRY_CHIPS = [
  "골든크로스(5일/20일) 발생 시 매수",
  "RSI 30 이하에서 매수",
  "MACD 골든크로스 매수",
  "볼린저밴드 하단 터치 시 매수",
  "20일 고점 돌파 시 매수",
  "거래량 급증 시 매수",
  "최근 3개월 수익률 상위 매수",
  "PER 10 이하",
  "ROE 15% 이상",
];

// 매수 조건 칩 목록은 성격이 다른 칩(시점 신호·랭킹·필터)이 평평하게 섞여 있었고, 자유
// 입력은 열 번째 칩으로 목록 끝에 묻혀 있었다(2026-09-04). 묶음 소제목으로 갈라 보이고
// 입력창을 칩 위에 처음부터 열어 둔다 — 칩 문구·값·순번은 그대로다(칩=값 결속 계약).
describe("매수 조건 선택지 묶음", () => {
  const builderRequests: Array<{ state: Record<string, unknown>; input: string }> = [];

  beforeEach(() => {
    vi.clearAllMocks();
    builderRequests.length = 0;
    window.sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", vi.fn());

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_PICK", symbols: [] }));
      }
      if (url === "/api/strategy/builder/step") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        builderRequests.push({ state: body.state ?? {}, input: body.input ?? "" });
        if (body.input === "코스피" || body.state?.universe) {
          return Promise.resolve(
            createJsonResponse({
              state: { universe: "KOSPI" },
              reply: ENTRY_QUESTION,
              suggestions: ENTRY_CHIPS,
            }),
          );
        }
        return Promise.resolve(
          createJsonResponse({
            state: {},
            reply: "어떤 시장을 대상으로 할까요?",
            suggestions: ["코스피", "코스닥", "코스피200"],
          }),
        );
      }
      return Promise.resolve(createJsonResponse({}));
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function reachEntryQuestion() {
    render(<StrategyLabPage />);
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "어떤 전략이 좋아?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    fireEvent.click(await screen.findByRole("button", { name: "코스피" }));
    expect(await screen.findByText(ENTRY_QUESTION)).toBeInTheDocument();
  }

  it("칩을 세 묶음의 소제목 아래 보이고 순번은 묶음을 가로질러 이어진다", async () => {
    await reachEntryQuestion();

    expect(screen.getByText("선택 예시")).toBeInTheDocument();
    expect(screen.getByText("매수 시점 신호")).toBeInTheDocument();
    expect(screen.getByText("순위로 담기")).toBeInTheDocument();
    expect(screen.getByText("종목 필터")).toBeInTheDocument();

    // 칩 문자열은 그대로다(접근성 이름 = 칩 문자열 = 백엔드 답변 프로토콜).
    for (const chip of ENTRY_CHIPS) {
      expect(screen.getByRole("button", { name: chip })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "골든크로스(5일/20일) 발생 시 매수" }).textContent)
      .toBe("1골든크로스(5일/20일) 발생 시 매수");
    expect(screen.getByRole("button", { name: "최근 3개월 수익률 상위 매수" }).textContent)
      .toBe("7최근 3개월 수익률 상위 매수");
    expect(screen.getByRole("button", { name: "ROE 15% 이상" }).textContent).toBe("9ROE 15% 이상");
  });

  it("'직접 입력' 칩 대신 입력창을 칩 위에 열어 두고, 적은 답은 같은 경로로 보낸다", async () => {
    await reachEntryQuestion();

    expect(screen.queryByRole("button", { name: "직접 입력" })).not.toBeInTheDocument();
    const freeInput = screen.getByPlaceholderText("원하는 매수 조건을 직접 적어 주세요");
    // 입력창이 목록보다 먼저 온다.
    expect(
      freeInput.compareDocumentPosition(screen.getByText("매수 시점 신호")) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // 조합(필터+신호)은 칩 하나로 못 고르므로 입력창으로 가는 길을 알린다.
    expect(screen.getByText(/종목 필터와 매수 시점 신호는 함께 쓸 수 있어요/)).toBeInTheDocument();

    fireEvent.change(freeInput, { target: { value: "PER 10 이하이면서 골든크로스가 나면 매수" } });
    fireEvent.keyDown(freeInput, { key: "Enter" });

    await waitFor(() => {
      expect(builderRequests.at(-1)).toEqual({
        state: { universe: "KOSPI" },
        input: "PER 10 이하이면서 골든크로스가 나면 매수",
      });
    });
  });

  it("칩을 누르면 평평한 목록과 똑같이 그 칩 문자열이 답으로 나간다", async () => {
    await reachEntryQuestion();

    fireEvent.click(screen.getByRole("button", { name: "PER 10 이하" }));

    await waitFor(() => {
      expect(builderRequests.at(-1)).toEqual({ state: { universe: "KOSPI" }, input: "PER 10 이하" });
    });
  });
});
