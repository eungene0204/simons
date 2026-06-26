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

function mockAuthenticatedPlanUsage() {
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
          },
          accounts: { used: 3, limit: 10 },
          strategies: { used: 12, limit: 50, unlimited: false },
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
  mockAuthenticatedPlanUsage();

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
    await openPlanModal();

    expect(await screen.findByText("Pro")).toBeInTheDocument();
    expect(screen.getByText("계좌당 초기 모의 투자금")).toBeInTheDocument();
    expect(screen.getByText("50,000,000원")).toBeInTheDocument();
  });

  it("계좌/전략/백테스트 사용량을 표시한다", async () => {
    await openPlanModal();

    expect(await screen.findByText("사용 중인 계좌")).toBeInTheDocument();
    expect(screen.getByText("3 / 10")).toBeInTheDocument();
    expect(screen.getByText("12 / 50")).toBeInTheDocument();
    expect(screen.getByText("7 / 100")).toBeInTheDocument();
  });

  it("자산 관련 표현을 사용하지 않는다", async () => {
    await openPlanModal();

    await screen.findByText("Pro");
    expect(screen.queryByText(/총 자산/)).not.toBeInTheDocument();
    expect(screen.queryByText(/사용 가능 자산/)).not.toBeInTheDocument();
  });
});
