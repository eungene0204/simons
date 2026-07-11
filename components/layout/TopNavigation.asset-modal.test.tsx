import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import TopNavigation from "./TopNavigation";

const pushMock = vi.fn();
const replaceMock = vi.fn();
const fetchMock = vi.fn();
const getSessionMock = vi.fn();
const signOutMock = vi.fn();
const signInWithOAuthMock = vi.fn();
const isSupabaseConfiguredMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    onClick,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} onClick={onClick} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    refresh: vi.fn(),
  }),
}));

vi.mock("@/lib/firebase", () => ({
  getSupabaseBrowserClient: () => ({
    auth: {
      getSession: getSessionMock,
      signOut: signOutMock,
      signInWithOAuth: signInWithOAuthMock,
    },
  }),
  isSupabaseConfigured: () => isSupabaseConfiguredMock(),
}));

vi.mock("./QuickSearchModal", () => ({
  default: ({
    isOpen,
    onClose,
  }: {
    isOpen: boolean;
    onClose: () => void;
  }) => (isOpen ? <button onClick={onClose}>close search</button> : null),
}));

vi.stubGlobal("fetch", fetchMock);

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

function mockAuthenticatedPlanUsage({
  strategies = { used: 12, limit: 50, unlimited: false },
  planStartDate = null,
  planEndDate = null,
}: {
  strategies?: { used: number; limit: number | null; unlimited: boolean };
  planStartDate?: string | null;
  planEndDate?: string | null;
} = {}) {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);

    if (url === "/api/user") {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          user: {
            name: "홍길동",
            email: "hong@example.com",
            avatarUrl: null,
          },
        }),
      });
    }

    if (url === "/api/user/plan") {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          plan: {
            planId: "PRO",
            name: "Pro",
            initialInvestmentAmount: 50_000_000,
            planStartDate,
            planEndDate,
          },
          accounts: { used: 3, limit: 10 },
          strategies,
          backtests: { used: 7, limit: 100 },
        }),
      });
    }

    if (url === "/api/stock/popular") {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          stocks: [],
          updatedAt: "09:00:00",
        }),
      });
    }

    return Promise.resolve({
      ok: true,
      json: async () => ({}),
    });
  });
}

async function openPlanModal() {
  renderWithQueryClient(<TopNavigation />);

  fireEvent.click(
    await screen.findByRole("button", { name: "홍길동 사용자 메뉴" })
  );
  fireEvent.click(screen.getByRole("button", { name: "내 플랜" }));

  return screen.findByRole("dialog", { name: "내 플랜" });
}

describe("TopNavigation plan modal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    isSupabaseConfiguredMock.mockReturnValue(true);
    getSessionMock.mockResolvedValue({ data: { session: null } });
    signOutMock.mockResolvedValue(undefined);
    signInWithOAuthMock.mockResolvedValue({ error: null });
  });

  it("현재 플랜과 계좌당 초기 투자금을 표시한다", async () => {
    mockAuthenticatedPlanUsage();
    await openPlanModal();

    expect(await screen.findByText("Pro")).toHaveClass("text-gray-300");
    expect(screen.getByText("내 플랜")).toHaveClass("text-gray-400");
    expect(screen.getByText("플랜 시작 날짜")).toBeInTheDocument();
    expect(screen.getByText("플랜 종료 날짜")).toBeInTheDocument();
    expect(screen.getAllByText("미등록")).toHaveLength(2);
    expect(screen.getByText("계좌당 초기 모의 투자금")).toBeInTheDocument();
    expect(screen.getByText("50,000,000원")).toHaveClass("text-gray-300");
  });

  it("계좌/전략/백테스트 사용량을 표시한다", async () => {
    mockAuthenticatedPlanUsage();
    await openPlanModal();

    expect(await screen.findByText("사용 중인 계좌")).toBeInTheDocument();
    expect(screen.getByText("3 / 10")).toBeInTheDocument();
    expect(screen.getByText("12 / 50")).toBeInTheDocument();
    expect(screen.getByText("7 / 100")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "사용 중인 계좌" })).toHaveAttribute(
      "aria-valuenow",
      "30"
    );
    expect(screen.getByRole("progressbar", { name: "저장 가능 전략" })).toHaveAttribute(
      "aria-valuenow",
      "24"
    );
    expect(screen.getByRole("progressbar", { name: "백테스트 횟수" })).toHaveAttribute(
      "aria-valuenow",
      "7"
    );
  });

  it("무제한 사용량은 bar graph를 비워서 표시한다", async () => {
    mockAuthenticatedPlanUsage({
      strategies: { used: 12, limit: null, unlimited: true },
    });
    await openPlanModal();

    expect(await screen.findByText("12 / 무제한")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "저장 가능 전략" })).toHaveAttribute(
      "aria-valuenow",
      "0"
    );
  });

  it("백테스트 횟수 아래에 리셋까지 남은 일수를 표시한다", async () => {
    // 주기 종료가 3일 뒤 → "Reset in 3 days"
    mockAuthenticatedPlanUsage({
      planEndDate: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(),
    });
    await openPlanModal();

    expect(await screen.findByText("Reset in 3 days")).toBeInTheDocument();
  });

  it("리셋까지 24시간 이하면 시간 단위(h)로 표시한다", async () => {
    mockAuthenticatedPlanUsage({
      planEndDate: new Date(Date.now() + 5 * 60 * 60 * 1000).toISOString(),
    });
    await openPlanModal();

    expect(await screen.findByText("Reset in 5h")).toBeInTheDocument();
  });

  it("주기 종료일이 없으면 리셋 표시를 렌더링하지 않는다", async () => {
    mockAuthenticatedPlanUsage();
    await openPlanModal();

    await screen.findByText("백테스트 횟수");
    expect(screen.queryByText(/Reset in/)).not.toBeInTheDocument();
  });

  it("프로필 메뉴의 설정을 누르면 설정 모달이 열린다", async () => {
    mockAuthenticatedPlanUsage();
    renderWithQueryClient(<TopNavigation />);

    fireEvent.click(
      await screen.findByRole("button", { name: "홍길동 사용자 메뉴" })
    );
    fireEvent.click(screen.getByRole("button", { name: "설정" }));

    const dialog = await screen.findByRole("dialog", { name: "설정" });
    expect(dialog).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "계정 삭제" })
    ).toBeInTheDocument();
  });

  it("자산 관련 표현을 사용하지 않는다", async () => {
    mockAuthenticatedPlanUsage();
    await openPlanModal();

    await screen.findByText("Pro");
    expect(screen.queryByText(/총 자산/)).not.toBeInTheDocument();
    expect(screen.queryByText(/사용 가능 자산/)).not.toBeInTheDocument();
  });
});
