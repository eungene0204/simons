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

describe("StrategyLab unknown intent fallback", () => {
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
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends an unclassified request to the LLM response route", async () => {
    const userRequest = "거래 규칙은 있는데 어떻게 표현해야 할지 모르겠어";

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(
          createJsonResponse({ user: { name: "Tester", email: "tester@example.com" } })
        );
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "UNKNOWN" }));
      }
      if (url === "/api/query/general") {
        // 첫 입력이므로 대화 맥락(history)은 빈 배열이다(FR-SA-002c-3).
        expect(JSON.parse(String(init?.body))).toEqual({ query: userRequest, history: [] });
        return Promise.resolve(
          createJsonResponse({ answer: "매수 조건과 청산 조건을 각각 한 문장으로 알려주세요." })
        );
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: userRequest } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("매수 조건과 청산 조건을 각각 한 문장으로 알려주세요.")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/query/general",
        expect.objectContaining({ method: "POST" })
      );
      expect(
        fetchMock.mock.calls.some(([input]) => String(input).includes("/api/strategy/parse"))
      ).toBe(false);
    });
  });

  it("starts a metric research conversation by asking for the market", async () => {
    const userRequest = "샤프지수를 최대화할 수 있는 전략을 만들어줘";

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/strategy/builder/step") {
        expect(JSON.parse(String(init?.body))).toMatchObject({
          state: {},
          input: "",
          seed: expect.stringContaining("과거 데이터 연구 목표: 샤프 지수"),
        });
        return Promise.resolve(createJsonResponse({
          state: {},
          status: "collecting",
          reply: "어떤 시장을 대상으로 할까요?",
          suggestions: ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체"],
        }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: userRequest } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(await screen.findByText(/어떤 시장을 대상으로 할까요/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "코스피" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/query/classify")).toBe(false);
  });

  it("collects a parameter range and runs the selected metric calculation", async () => {
    let resolveOptimization!: (response: Response) => void;
    const optimizationResponse = new Promise<Response>((resolve) => {
      resolveOptimization = resolve;
    });
    const parsed = {
      description: "코스피 RSI 전략",
      universe: ["kospi"],
      fundamental_filters: [],
      entry_signals: [{ indicator: "rsi" }],
      exit_signals: [{ indicator: "rsi" }],
      max_positions: 5,
      hold_period_days: 20,
      rebalancing_period: "monthly",
      stop_loss_pct: 10,
      take_profit_pct: null,
      trailing_stop_pct: null,
      backtest_period: "5y",
      initial_capital: 10000000,
    };
    const backtestRequest = {
      symbols: ["005930"],
      universe_id: "kospi",
      entry: { conditions: [{ type: "indicator", id: "rsi", params: { period: 14, value: 30 } }] },
      exit: { conditions: [{ type: "indicator", id: "rsi", params: { period: 14, value: 70 } }] },
      risk: { position_size_pct: 20, max_positions: 5, stop_loss_pct: 10, init_cash: 10000000 },
      period: "5Y",
      options: {},
    };

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/model/status") return Promise.resolve(createJsonResponse({ status: "ready" }));
      if (url === "/api/user") return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/builder/step") {
        const body = JSON.parse(String(init?.body));
        if (body.input === "") {
          return Promise.resolve(createJsonResponse({
            state: {},
            status: "collecting",
            reply: "어떤 시장을 대상으로 할까요?",
            suggestions: ["코스피"],
          }));
        }
        return Promise.resolve(createJsonResponse({
          state: {},
          status: "confirmed",
          parsed,
          backtest_request: backtestRequest,
          prompt: parsed.description,
        }));
      }
      if (url === "/api/strategy/parse/stream") {
        const body = JSON.parse(String(init?.body));
        expect(body.prompt).toBe("익절 20%");
        const completedParsed = { ...parsed, take_profit_pct: 20 };
        const completedRequest = {
          ...backtestRequest,
          risk: { ...backtestRequest.risk, take_profit_pct: 20 },
        };
        const encoder = new TextEncoder();
        const payload = [
          `data: ${JSON.stringify({
            type: "parsed_final",
            parsed: completedParsed,
            clarification_question: null,
            clarification_suggestions: null,
          })}\n\n`,
          `data: ${JSON.stringify({
            type: "dsl_ready",
            backtest_request: completedRequest,
            symbol_count: 1,
          })}\n\n`,
          "data: [DONE]\n\n",
        ].join("");
        return Promise.resolve(new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode(payload));
              controller.close();
            },
          }),
          { status: 200 },
        ));
      }
      if (url === "http://localhost:8000/optimize") {
        expect(JSON.parse(String(init?.body))).toMatchObject({
          target_metric: "sharpe",
          n_trials: 30,
          ranges: {
            "risk.stop_loss_pct": { type: "number" },
          },
        });
        return optimizationResponse;
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);
    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "샤프지수를 최대화할 수 있는 전략을 만들어줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    fireEvent.click(await screen.findByRole("button", { name: "코스피" }));
    expect(
      await screen.findByText(
        "익절 기준이 빠져 있습니다. 익절 기준을 몇 %로 설정할까요?",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "익절 10%" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "익절 20%" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "익절 30%" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(screen.queryByText(/현재 상태로도 백테스트를 실행할 수 있습니다/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "백테스트 시작하기" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "익절 20%" }));
    fireEvent.click(await screen.findByRole("button", { name: "손절라인" }));
    fireEvent.click(await screen.findByRole("button", { name: /\d+(?:\.\d+)? ~ \d+(?:\.\d+)?/ }));
    fireEvent.click(await screen.findByRole("button", { name: "이 범위로 계산" }));

    expect(await screen.findByRole("progressbar", { name: "파라미터 조합 계산 진행 상황" })).toBeInTheDocument();
    expect(screen.getByText(/30개 조합 계산 중/)).toBeInTheDocument();
    expect(screen.getByText(/경과 \d+초/)).toBeInTheDocument();

    resolveOptimization(createJsonResponse({
      status: "success",
      target_metric: "sharpe",
      total_iterations: 30,
      top_results: [{
        iteration: 3,
        parameters: { "risk.stop_loss_pct": 8 },
        target_value: 1.5,
        metrics: { cagr: 12.3, maxDrawdown: -8.4, sharpe: 1.5 },
      }],
    }));
    expect(await screen.findByText(/샤프 지수 기준으로 30회 계산을 마쳤습니다/)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar", { name: "파라미터 조합 계산 진행 상황" })).not.toBeInTheDocument();
    expect(screen.getByText(/손절라인 8/)).toBeInTheDocument();
    expect(screen.getByText(/샤프 지수 1.50/)).toBeInTheDocument();
  });
});
