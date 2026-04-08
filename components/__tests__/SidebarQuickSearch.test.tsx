import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Sidebar from "@/components/layout/Sidebar";

const pushMock = vi.fn();
const openVirtualAccountMock = vi.fn();
const fetchMock = vi.fn();

vi.mock("next/image", () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img {...props} alt={props.alt || ""} />
  ),
}));

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
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({
    push: pushMock,
  }),
}));

vi.mock("@/contexts/DrawerContext", () => ({
  useDrawer: () => ({
    drawerType: null,
    isWatchlistOpen: false,
    openWatchlist: vi.fn(),
    isVirtualAccountOpen: false,
    openVirtualAccount: openVirtualAccountMock,
  }),
}));

vi.stubGlobal("fetch", fetchMock);

describe("Sidebar quick search", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.startsWith("/api/quick-search")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            stocks: [
              {
                symbol: "005930",
                name: "삼성전자",
                type: "KOSPI",
                region: "KR",
                currency: "KRW",
              },
            ],
            strategies: [
              {
                id: "strategy-1",
                name: "삼성 모멘텀 전략",
                description: "삼성전자 중심 전략",
                strategyType: "모멘텀",
                universe: "KOSPI",
              },
            ],
            virtualAccounts: [
              {
                id: "account-1",
                name: "삼성 테스트 계좌",
                strategyName: "삼성 모멘텀 전략",
                tradingMode: "auto",
              },
            ],
          }),
        });
      }

      return Promise.resolve({
        ok: false,
        json: async () => ({}),
      });
    });
  });

  it("슬래시 퀵서치에서 종목, 전략, 가상계좌를 검색하고 이동할 수 있다", async () => {
    render(<Sidebar />);

    fireEvent.keyDown(window, { key: "/" });

    const input = await screen.findByPlaceholderText(
      "종목명, 전략명, 가상계좌명을 입력하세요"
    );
    fireEvent.change(input, { target: { value: "삼성" } });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/quick-search?q=%EC%82%BC%EC%84%B1");
    });

    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("삼성 모멘텀 전략")).toBeInTheDocument();
    expect(screen.getByText("삼성 테스트 계좌")).toBeInTheDocument();

    fireEvent.click(screen.getByText("삼성 테스트 계좌"));

    expect(pushMock).toHaveBeenCalledWith("/virtual-account/account-1");
  });

  it("몇 글자만 입력해도 바로 추천 결과를 보여준다", async () => {
    render(<Sidebar />);

    fireEvent.keyDown(window, { key: "/" });

    const input = await screen.findByPlaceholderText(
      "종목명, 전략명, 가상계좌명을 입력하세요"
    );
    fireEvent.change(input, { target: { value: "삼" } });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/quick-search?q=%EC%82%BC");
    });

    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("삼성 모멘텀 전략")).toBeInTheDocument();
    expect(screen.getByText("삼성 테스트 계좌")).toBeInTheDocument();
  });
});
