// 되묻기 카드의 '돌아가기'는 칩으로 답한 턴에만 붙어 있었다 — 자유 서술로 답하거나 처음
// 전략을 적어 넣어 파스를 거친 턴의 카드에는 되돌릴 상태가 남지 않아 버튼이 없었다
// (2026-09-04 사용자 지적: 리밸런싱 방식 질문 카드). 파스 턴도 파스 **전** 상태를 남기고
// 같은 자리·같은 버튼으로 되돌린다.
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

const parsedWithoutExit = {
  description: "PER 저평가 전략",
  universe: ["KOSPI"],
  fundamental_filters: [{ metric: "per", operator: "<=", value: 10 }],
  entry_signals: [],
  exit_signals: [],
  max_positions: 5,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  trailing_stop_pct: null,
  backtest_period: "5y",
  initial_capital: 10000000,
};

const parsedWithExit = {
  ...parsedWithoutExit,
  exit_signals: [{ indicator: "rsi", signal_type: "sell", threshold: 70 }],
};

const backtestRequest = {
  symbols: ["005930", "000660"],
  universe_id: "kospi",
  entry: { conditions: [{ id: "per" }] },
  exit: { conditions: [] },
  risk: { max_positions: 5, init_cash: 10000000 },
  period: "5y",
  options: { fee_rate: 0.015, slippage_rate: 0.05 },
};

function sseResultResponse(data: Record<string, unknown>) {
  const parsedFinal = JSON.stringify({ type: "parsed_final", ...data });
  const dslReady = JSON.stringify({
    type: "dsl_ready",
    backtest_request: backtestRequest,
    symbol_count: 2,
  });
  return new Response(
    `data: ${parsedFinal}\n\ndata: ${dslReady}\n\ndata: [DONE]\n\n`,
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

function parseBodies() {
  return fetchMock.mock.calls
    .filter(([input]) => String(input) === "/api/strategy/parse/stream")
    .map((call) => JSON.parse((call[1] as RequestInit).body as string));
}

const UNIVERSE_QUESTION = "먼저 어떤 시장·종목을 대상으로 할지 정해볼까요?";
const EXIT_QUESTION = "이제 언제 매도할지 정해볼까요?";
const FIRST_PROMPT = "PER 10 이하 종목을 매수";
const FREE_ANSWER = "RSI 70 이상이면 매도";

describe("파스 턴 뒤 되묻기 카드의 '돌아가기'", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
        return Promise.resolve(createJsonResponse({
          intent: "STRATEGY_ADVICE",
          symbols: [],
          workflow_effect: "UPDATE",
          workflow_status: "ACTIVE",
          clarify_target: null,
        }));
      }
      if (url === "/api/strategy/parse/stream") {
        const body = JSON.parse((init?.body as string) ?? "{}");
        // 되묻기 답(pending_question 에코)이면 매도 조건이 채워진 전략을 돌려준다.
        return Promise.resolve(
          body.pending_question
            ? sseResultResponse({ parsed: parsedWithExit, explicit_fields: ["universe"] })
            : sseResultResponse({ parsed: parsedWithoutExit, explicit_fields: [] }),
        );
      }
      if (url === "/api/strategy/builder/step" || url === "/api/strategy/compile") {
        throw new Error(`이 시나리오에서 호출되면 안 되는 경로: ${url}`);
      }
      return Promise.resolve(createJsonResponse({}));
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function sendFirstPrompt() {
    render(<StrategyLabPage />);
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: FIRST_PROMPT } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    expect(await screen.findByText(UNIVERSE_QUESTION)).toBeInTheDocument();
  }

  it("처음 적어 넣은 전략의 첫 질문에서 돌아가면 대화가 비고 원문이 입력창에 돌아온다", async () => {
    await sendFirstPrompt();

    fireEvent.click(screen.getByRole("button", { name: "돌아가기" }));

    await waitFor(() => {
      expect(screen.queryByText(UNIVERSE_QUESTION)).not.toBeInTheDocument();
    });
    expect(screen.queryByText(FIRST_PROMPT, { selector: "p, div, span" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue(FIRST_PROMPT);
  });

  it("자유 서술로 답한 뒤의 질문에서 돌아가면 직전 질문 카드로 되돌아가고, 다음 답은 그 질문의 답으로 나간다", async () => {
    await sendFirstPrompt();

    // 유니버스는 칩으로, 매도 조건은 자유 서술로 답한다.
    fireEvent.click(screen.getByRole("button", { name: "코스피" }));
    expect(await screen.findByText(EXIT_QUESTION)).toBeInTheDocument();
    // 매도 조건 목록은 정본에서 알아보므로 입력창이 칩 위에 이미 열려 있다.
    fireEvent.change(screen.getByPlaceholderText("원하는 매도 조건을 직접 적어 주세요"), {
      target: { value: FREE_ANSWER },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    // 파스 뒤 다음 질문(최대 보유) 카드에도 '돌아가기'가 있다.
    expect(await screen.findByRole("button", { name: "최대 5종목" })).toBeInTheDocument();
    expect(screen.queryByText(EXIT_QUESTION)).not.toBeInTheDocument();
    expect(parseBodies().at(-1).pending_question).toBe(EXIT_QUESTION);

    fireEvent.click(screen.getByRole("button", { name: "돌아가기" }));

    // 매도 조건 질문 카드가 다시 '지금 답할 질문'이고, 자유 답변 버블은 지워진다.
    expect(await screen.findByText(EXIT_QUESTION)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "데드크로스(5일/20일) 발생 시 매도" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "최대 5종목" })).not.toBeInTheDocument();
    expect(screen.queryByText(FREE_ANSWER)).not.toBeInTheDocument();

    // 되돌린 뒤의 자유 답변은 지워진 질문이 아니라 매도 조건 질문의 답으로 나간다.
    fireEvent.change(screen.getByPlaceholderText("원하는 매도 조건을 직접 적어 주세요"), {
      target: { value: "20일 보유 후 청산" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));
    await waitFor(() => {
      expect(parseBodies().at(-1).prompt).toBe("20일 보유 후 청산");
    });
    expect(parseBodies().at(-1).pending_question).toBe(EXIT_QUESTION);
    expect(parseBodies().at(-1).previous_parsed.exit_signals).toEqual([]);
  });
});
