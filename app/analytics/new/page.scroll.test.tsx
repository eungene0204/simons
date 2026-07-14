import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

const push = vi.fn();
const fetchMock = vi.fn();
const scrollToMock = vi.fn();

const parsedStrategy = {
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

const backtestRequest = {
  symbols: ["005930", "000660"],
  universe_id: "kospi",
  entry: { conditions: [{ id: "per" }] },
  exit: { conditions: [] },
  risk: {
    max_positions: 5,
    init_cash: 10000000,
  },
  period: "5y",
  options: {
    fee_rate: 0.015,
    slippage_rate: 0.05,
  },
};

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

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function createJsonResponse(body: unknown, headers?: Record<string, string>) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      ...(headers ?? {}),
    },
  });
}

function createParseStreamResponse() {
  const encoder = new TextEncoder();
  const payload = [
    `data: ${JSON.stringify({ type: "parsed_final", parsed: parsedStrategy })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: backtestRequest, symbol_count: 2 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 }
  );
}

function createParseStreamResponseWithClarification() {
  const encoder = new TextEncoder();
  const clarificationQuestion =
    "말씀하신 조건을 숫자로 구체화해 주세요. 어느 정도를 기준으로 할까요?\n\n" +
    "• 영업이익률 몇 % 이상으로 설정할까요?";
  const payload = [
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed: parsedStrategy,
      clarification_question: clarificationQuestion,
      clarification_suggestions: ["영업이익률 10% 이상", "영업이익률 15% 이상"],
    })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: backtestRequest, symbol_count: 2 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 }
  );
}

describe("StrategyLabPage scroll behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    // 모킹된 DashboardLayout에는 <main>이 없어 스크롤은 window 폴백 경로를 탄다.
    // 메시지 끝이 입력창에 가리는 상황(delta > 0)을 만들기 위해 bottom을 크게 잡는다.
    window.HTMLElement.prototype.getBoundingClientRect = () =>
      ({ bottom: 10000, top: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    vi.stubGlobal("scrollTo", scrollToMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("백엔드의 영업이익률 명확화 질문을 기존 진입 조건과 관계없이 그대로 표시한다", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponseWithClarification());
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: { value: "영업이익률이 높은 조건도 넣어줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(/영업이익률 몇 % 이상으로 설정할까요/)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "영업이익률 10% 이상" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "영업이익률 15% 이상" })).toBeInTheDocument();
    const textarea = screen.getByRole("textbox");
    textarea.blur();
    fireEvent.click(screen.getByRole("button", { name: "직접 입력" }));
    await waitFor(() => expect(textarea).toHaveFocus());
    expect(
      fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/coach")
    ).toBe(false);
  });

  it("scrolls to the bottom when a follow-up coach reply updates the existing assistant message", async () => {
    const followUpResponse = createDeferred<Response>();

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }

      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponse());
      }

      if (url === "/api/strategy/coach") {
        const body = JSON.parse(String(init?.body ?? "{}")) as { action?: string };

        if (body.action === "follow_up") {
          return followUpResponse.promise;
        }

        return Promise.resolve(createJsonResponse(
          { message: "첫 번째 코치 응답입니다." },
          { "X-Coach-Session-Id": "coach-session-1" }
        ));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "PER 10 이하 전략 만들어줘" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 전략 검증은 의도된 최소 지연(~2.4s) 후 응답을 노출하므로 타임아웃을 넉넉히 둔다.
    expect(
      await screen.findByText("첫 번째 코치 응답입니다.", undefined, { timeout: 5000 })
    ).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "어떻게 개선할까?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(await screen.findByText("검증 중...")).toBeInTheDocument();
    scrollToMock.mockClear();

    followUpResponse.resolve(
      createJsonResponse({ message: "후속 코치 응답입니다. 손절 기준을 더 명확히 해보세요." })
    );

    expect(
      await screen.findByText("후속 코치 응답입니다. 손절 기준을 더 명확히 해보세요.", undefined, {
        timeout: 5000,
      })
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(scrollToMock).toHaveBeenCalled();
    });
  });

  it("asks for a percentage instead of reparsing when take profit is requested without a value", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }

      if (url === "/api/strategy/parse/stream") {
        return Promise.resolve(createParseStreamResponse());
      }

      if (url === "/api/strategy/coach") {
        return Promise.resolve(createJsonResponse(
          { message: "첫 번째 코치 응답입니다." },
          { "X-Coach-Session-Id": "coach-session-1" }
        ));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "PER 10 이하 전략 만들어줘" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("첫 번째 코치 응답입니다.", undefined, { timeout: 5000 })
    ).toBeInTheDocument();
    const summaryCountBeforeFollowUp = screen.getAllByText("전략 요약").length;

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "익절을 추가해 볼까?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(
        "익절 기준은 매수가 대비 수익률로 설정합니다. 예시 값은 5%, 10%, 15%입니다. 적용할 익절 기준을 몇 %로 할까요?"
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "익절 5%" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "익절 10%" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "익절 15%" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(screen.getAllByText("전략 요약")).toHaveLength(summaryCountBeforeFollowUp);
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/parse/stream")).toHaveLength(1);
  });

  it("answers a short-term versus long-term comparison without starting the strategy builder", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "단기 전략 장기 전략 뭐가 좋을까?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText(/연구할 보유기간과 거래 빈도 가정이 다릅니다/)
    ).toBeInTheDocument();
    expect(screen.getByText(/수수료·슬리피지와 신호 변화의 영향/)).toBeInTheDocument();
    expect(screen.queryByText("어떤 시장을 대상으로 할까요?")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/builder/step")).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
  });

  it("asks for a long holding period before continuing with the remaining builder questions", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }

      if (url === "/api/strategy/builder/step") {
        const body = JSON.parse(String(init?.body ?? "{}")) as {
          seed?: string;
          state?: { hold_period_days?: number; risk_done?: boolean };
        };
        expect(body.seed).toBe("장기전략으로 만들어 볼까?");
        expect(body.state).toMatchObject({ hold_period_days: 504, risk_done: true });

        return Promise.resolve(createJsonResponse({
          state: {
            hold_period_days: 504,
            risk_done: true,
          },
          reply: "504거래일 보유 조건을 반영했습니다. 어떤 시장을 대상으로 할까요?",
          suggestions: ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체"],
        }));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "장기전략으로 만들어 볼까?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("바이 앤 홀드 전략으로 이해했어요. 얼마나 오래 보유할까요?")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "252거래일 (1년)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "504거래일 (2년)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "756거래일 (3년)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1,260거래일 (5년)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/builder/step")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "504거래일 (2년)" }));

    expect(
      await screen.findByText("504거래일 보유 조건을 반영했습니다. 어떤 시장을 대상으로 할까요?")
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/builder/step")).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/query/classify")).toHaveLength(1);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
  });

  it("asks for a short holding period before continuing with the remaining builder questions", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }

      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({
          user: {
            name: "Tester",
            email: "tester@example.com",
          },
        }));
      }

      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }

      if (url === "/api/strategy/builder/step") {
        const body = JSON.parse(String(init?.body ?? "{}")) as {
          seed?: string;
          state?: { hold_period_days?: number; risk_done?: boolean };
        };
        expect(body.seed).toBe("단기 투자 전략을 만들어보자");
        expect(body.state).toMatchObject({ hold_period_days: 10, risk_done: true });

        return Promise.resolve(createJsonResponse({
          state: {
            hold_period_days: 10,
            risk_done: true,
          },
          reply: "10거래일 보유 조건을 반영했습니다. 어떤 시장을 대상으로 할까요?",
          suggestions: ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체"],
        }));
      }

      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "단기 투자 전략을 만들어보자" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(
      await screen.findByText("단기 매매 전략으로 이해했어요. 얼마나 오래 보유할까요?")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1거래일 (당일)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5거래일 (1주)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "10거래일 (2주)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "20거래일 (약 1개월)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "60거래일 (약 3개월)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "직접 입력" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/builder/step")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "10거래일 (2주)" }));

    expect(
      await screen.findByText("10거래일 보유 조건을 반영했습니다. 어떤 시장을 대상으로 할까요?")
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/builder/step")).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/query/classify")).toHaveLength(1);
    expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/strategy/parse/stream")).toBe(false);
  });
});
