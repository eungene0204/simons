// [회귀] 2026-08-23 사용자 지시 — '현재까지 이해한 전략입니다' 카드가 대화에 두 번
// 보였다. 빌더 턴마다 새 assistant 메시지가 붙고 각자 요약을 그렸기 때문이다.
// 이 카드는 진행 상태 하나를 잇는 카드이므로(FR-STR-019w ⑤) 가장 아래 것만 그린다.
import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StrategyLabPage from "./page";

const push = vi.fn();
const fetchMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }), usePathname: () => "/analytics/chat",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/components/layout/DashboardLayout", () => ({ default: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/strategy/StrategyExampleTabs", () => ({ StrategyExampleTabs: () => <div>예시 전략</div> }));
vi.mock("@/components/strategy/StrategyWaveBackground", () => ({ StrategyWaveBackground: () => <div>배경</div> }));
vi.mock("@supabase/supabase-js", () => ({ createClient: () => ({ auth: { signInWithOAuth: vi.fn(), getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } }) }));

const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { "Content-Type": "application/json" } });
const NOTICE = "어떤 전략이 더 좋은지 판단하거나 추천해 드리지는 않지만, 관심 있는 아이디어를 함께 전략으로 만들어 과거 데이터로 백테스트해 볼 수 있어요.";

let stepCall = 0;
function mockRoutes() {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/model/status") return Promise.resolve(json({ status: "ready", error: null }));
    if (url === "/api/user") return Promise.resolve(json({ user: { name: "T", email: "t@e.com" } }));
    if (url === "/api/query/classify") return Promise.resolve(json({ intent: "STRATEGY_PICK", suggested_reply: NOTICE }));
    if (url === "/api/strategy/builder/step") {
      stepCall += 1;
      if (stepCall === 1) return Promise.resolve(json({ state: {}, reply: "먼저 어떤 시장·종목을 대상으로 할지 정해볼까요?", suggestions: ["코스피", "코스닥"], status: "collecting", seed_recognized: false }));
      return Promise.resolve(json({ state: { universe: "KOSPI" }, reply: "매수 조건을 정해볼까요?", suggestions: ["RSI", "이동평균"], status: "collecting", seed_recognized: false }));
    }
    return Promise.resolve(json({}));
  });
}

describe("전략 요약 카드는 대화에 쌓이지 않는다 — 최신 하나만", () => {
  beforeEach(() => {
    vi.clearAllMocks(); stepCall = 0;
    window.localStorage.clear(); window.sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => { cb(0); return 1; });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", vi.fn());
    mockRoutes();
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("빌더 턴이 이어져도 요약 카드는 최신 한 장만 남는다", async () => {
    render(<StrategyLabPage />);
    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "어떤 전략이 제일 좋아?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    await screen.findByText(/먼저 어떤 시장/, undefined, { timeout: 5000 });
    expect(screen.getAllByTestId("builder-strategy-summary")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "코스피" }));
    await screen.findByText(/매수 조건을 정해볼까요/, undefined, { timeout: 5000 });

    // 턴마다 새 assistant 메시지가 붙지만 카드는 한 장이다 — 남은 한 장은 최신 상태다.
    const cards = screen.getAllByTestId("builder-strategy-summary");
    expect(cards).toHaveLength(1);
    expect(cards[0]).toHaveTextContent("KOSPI");
    // 열린 추천 안내는 카드가 아니라 본문이라 첫 턴 자리에 그대로 남는다.
    expect(screen.getByText(/추천해 드리지는 않지만/)).toBeInTheDocument();
  });
});
