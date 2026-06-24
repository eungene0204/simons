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

function mockAuthenticatedAssetSummary(totalProfitLoss: number) {
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

    if (url === "/api/user/assets") {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          availableCash: 4_280_797,
          activeAccountValue: 5_000_000,
          totalAssets: 9_280_797,
          totalProfitLoss,
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

async function openAssetModal(totalProfitLoss: number) {
  mockAuthenticatedAssetSummary(totalProfitLoss);

  renderWithQueryClient(<TopNavigation />);

  fireEvent.click(
    await screen.findByRole("button", { name: "홍길동 사용자 메뉴" })
  );
  fireEvent.click(screen.getByRole("button", { name: "자산" }));

  return screen.findByRole("dialog", { name: "자산" });
}

describe("TopNavigation asset modal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    isSupabaseConfiguredMock.mockReturnValue(true);
    getSessionMock.mockResolvedValue({ data: { session: null } });
    signOutMock.mockResolvedValue(undefined);
    signInWithOAuthMock.mockResolvedValue({ error: null });
  });

  it("hides the Asset Wallet eyebrow and renders available cash in white", async () => {
    await openAssetModal(0);

    expect(screen.queryByText(/asset wallet/i)).not.toBeInTheDocument();
    expect(screen.getByText("사용 가능 자산")).toHaveClass("text-white");
    expect(screen.getByText("4,280,797원")).toHaveClass("text-white");
  });

  it("renders positive total profit/loss in red with a leading plus sign", async () => {
    await openAssetModal(719_203);

    expect(screen.getByText("+719,203원")).toHaveClass("text-[var(--main-red)]");
  });

  it("renders negative total profit/loss in blue", async () => {
    await openAssetModal(-719_203);

    expect(screen.getByText("-719,203원")).toHaveClass("text-[var(--main-blue)]");
  });

  it("renders zero total profit/loss in white without a leading plus sign", async () => {
    await openAssetModal(0);

    expect(screen.getByText("0원")).toHaveClass("text-white");
  });
});
