// [회귀] 2026-08-10 사용자 지시 — 열린 전략 추천 안내문("추천해 드리지는 않지만…")과
// 빌더의 시드 이해 ack("좋아요. 모멘텀 전략(으)로 이해했어요")는 **둘 중 하나만** 보인다.
// 분류가 구체 설계 요청을 STRATEGY_PICK으로 오판해도, 빌더가 시드를 이해했으면
// (백엔드 seed_recognized=true) 안내문을 생략한다. 진짜 열린 요청(이해 실패)은 종전대로
// 안내문+첫 질문이 나간다.
import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
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

const PICK_NOTICE =
  "어떤 전략이 더 좋은지 판단하거나 추천해 드리지는 않지만, 관심 있는 아이디어를 함께 " +
  "전략으로 만들어 과거 데이터로 백테스트해 볼 수 있어요.";

function mockRoutes({ builderStep }: { builderStep: Record<string, unknown> }) {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
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
      return Promise.resolve(
        createJsonResponse({ intent: "STRATEGY_PICK", suggested_reply: PICK_NOTICE })
      );
    }
    if (url === "/api/strategy/builder/step") {
      return Promise.resolve(createJsonResponse(builderStep));
    }
    return Promise.resolve(createJsonResponse({}));
  });
}

async function submitPrompt(text: string) {
  render(<StrategyLabPage />);
  const textarea = await screen.findByRole("textbox");
  fireEvent.change(textarea, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
}

describe("열린 전략 추천 안내문 — 시드 이해 시 생략(둘 중 하나만)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // 이전 테스트의 대화 세션 스냅샷(localStorage)이 복원되면 칩 표시 상태로 마운트되어
    // 입력창이 나타나지 않는다 — 테스트마다 새 세션으로 시작한다.
    window.localStorage.clear();
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

  it("빌더가 시드를 이해하면(seed_recognized) 안내문 없이 ack+질문만 보인다", async () => {
    mockRoutes({
      builderStep: {
        state: { strategy_type: "momentum" },
        reply: "좋아요. 모멘텀 전략(으)로 이해했어요.\n\n어떤 시장을 대상으로 할까요?",
        suggestions: ["코스피", "코스닥"],
        status: "collecting",
        seed_recognized: true,
      },
    });
    await submitPrompt("상대 모멘텀 효과를 이용한 투자 전략");

    expect(
      await screen.findByText(/어떤 시장을 대상으로 할까요/, undefined, { timeout: 5000 })
    ).toBeInTheDocument();
    expect(screen.getByText(/모멘텀 전략\(으\)로 이해했어요/)).toBeInTheDocument();
    // 이해했으면 열린 추천 안내문은 나가지 않는다 — 둘 중 하나만.
    expect(screen.queryByText(/추천해 드리지는 않지만/)).not.toBeInTheDocument();
    // [회귀 2026-08-11] 안내 보류 경로가 분류 자리표시자를 소비하지 않아 '분석 중...'
    // 버블이 로딩 상태로 영원히 남았다 — 답이 나간 뒤 스피너가 없어야 한다.
    expect(screen.queryByText("분석 중...")).not.toBeInTheDocument();
  });

  it("시드 이해가 없으면(진짜 열린 요청) 안내문과 첫 질문이 함께 나간다", async () => {
    mockRoutes({
      builderStep: {
        state: {},
        reply: "어떤 시장을 대상으로 할까요?",
        suggestions: ["코스피", "코스닥"],
        status: "collecting",
        seed_recognized: false,
      },
    });
    await submitPrompt("어떤 전략이 제일 좋아?");

    expect(
      await screen.findByText(/어떤 시장을 대상으로 할까요/, undefined, { timeout: 5000 })
    ).toBeInTheDocument();
    expect(screen.getByText(/추천해 드리지는 않지만/)).toBeInTheDocument();
    // [회귀 2026-08-11] 위와 동일 — 고아 '분석 중...' 스피너 금지.
    expect(screen.queryByText("분석 중...")).not.toBeInTheDocument();
  });
});
