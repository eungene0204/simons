import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsModal from "./SettingsModal";

const pushMock = vi.fn();
const fetchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.stubGlobal("fetch", fetchMock);

function mockPlanFetch({
  planId = "FREE",
  name = "Free",
  subscription = null,
  orders = [],
}: {
  planId?: string;
  name?: string;
  subscription?: {
    planId: string;
    nextBillingAt: string | null;
    canceled: boolean;
  } | null;
  orders?: {
    id: string;
    planId: string;
    amount: number;
    status: string;
    date: string;
  }[];
} = {}) {
  fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/user/plan") {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          plan: { planId, name, planEndDate: null },
          subscription,
          accounts: { used: 3, limit: 10 },
          strategies: { used: 12, limit: 50, unlimited: false },
          backtests: { used: 7, limit: 100 },
        }),
      });
    }
    if (url === "/api/payment/orders") {
      return Promise.resolve({ ok: true, json: async () => ({ orders }) });
    }
    if (url === "/api/payment/billing/cancel" && init?.method === "POST") {
      return Promise.resolve({ ok: true, json: async () => ({ ok: true }) });
    }
    if (url === "/api/user/account" && init?.method === "DELETE") {
      return Promise.resolve({ ok: true, json: async () => ({ ok: true }) });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
}

describe("SettingsModal", () => {
  const onClose = vi.fn();
  const onLogout = vi.fn();
  const onAccountDeleted = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  function renderModal(userEmail: string | null = "hong@example.com") {
    return render(
      <SettingsModal
        userEmail={userEmail}
        onClose={onClose}
        onLogout={onLogout}
        onAccountDeleted={onAccountDeleted}
      />
    );
  }

  it("계정/결제/사용량 탭을 표시하고 기본으로 계정 탭을 연다", async () => {
    mockPlanFetch();
    renderModal();

    expect(
      await screen.findByRole("button", { name: "계정 삭제" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "결제" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "사용량" })).toBeInTheDocument();
    expect(screen.getByText("hong@example.com")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "설정" })).toHaveClass(
      "p-2",
      "lg:px-4",
      "lg:py-0"
    );
    expect(screen.getByTestId("settings-modal-panel")).toHaveClass(
      "h-[calc(100dvh-1rem)]",
      "flex-col",
      "lg:h-[min(720px,85vh)]",
      "lg:flex-row"
    );
    expect(screen.getByTestId("settings-modal-sidebar")).toHaveClass(
      "w-full",
      "border-b",
      "lg:w-56",
      "lg:border-b-0",
      "lg:border-r"
    );
    expect(screen.getByTestId("settings-modal-tabs")).toHaveClass(
      "flex",
      "overflow-x-auto",
      "lg:block",
      "lg:overflow-visible"
    );
    expect(screen.getByTestId("settings-modal-content")).toHaveClass(
      "px-4",
      "py-6",
      "lg:px-10",
      "lg:py-10"
    );
  });

  it("사이드바 검색으로 메뉴를 필터링한다", async () => {
    mockPlanFetch();
    renderModal();

    await screen.findByRole("button", { name: "계정 삭제" });
    fireEvent.change(screen.getByLabelText("설정 검색"), {
      target: { value: "결제" },
    });
    expect(screen.getByRole("button", { name: "결제" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "사용량" })
    ).not.toBeInTheDocument();
  });

  it("로그아웃 행의 버튼은 onLogout을 호출한다", async () => {
    mockPlanFetch();
    renderModal();

    fireEvent.click(await screen.findByRole("button", { name: "로그아웃" }));
    expect(onLogout).toHaveBeenCalled();
  });

  it("구독이 없으면 계정 삭제가 가능하고, 삭제 성공 시 onAccountDeleted를 호출한다", async () => {
    mockPlanFetch();
    renderModal();

    const deleteButton = await screen.findByRole("button", {
      name: "계정 삭제",
    });
    expect(deleteButton).toBeEnabled();

    fireEvent.click(deleteButton);
    await waitFor(() => expect(onAccountDeleted).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/user/account",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("활성 자동갱신 구독이 있으면 계정 삭제 버튼을 비활성화하고 안내를 표시한다", async () => {
    mockPlanFetch({
      planId: "PRO",
      name: "Pro",
      subscription: {
        planId: "PRO",
        nextBillingAt: "2026-08-01T00:00:00.000Z",
        canceled: false,
      },
    });
    renderModal();

    const deleteButton = await screen.findByRole("button", {
      name: "계정 삭제",
    });
    expect(deleteButton).toBeDisabled();
    expect(
      screen.getByText("계정을 삭제하려면 먼저 요금제 구독을 취소해 주세요.")
    ).toBeInTheDocument();

    fireEvent.click(deleteButton);
    expect(onAccountDeleted).not.toHaveBeenCalled();
  });

  it("결제 탭에서 자동갱신 구독을 취소하면 만료 안내로 바뀐다", async () => {
    mockPlanFetch({
      planId: "PRO",
      name: "Pro",
      subscription: {
        planId: "PRO",
        nextBillingAt: "2026-08-01T00:00:00.000Z",
        canceled: false,
      },
    });
    renderModal();

    fireEvent.click(await screen.findByRole("button", { name: "결제" }));
    expect(
      screen.getByText(/구독이 .*에 자동으로 갱신됩니다\./)
    ).toBeInTheDocument();
    expect(screen.getByText("Pro 요금제")).toBeInTheDocument();
    expect(screen.getByText("월간")).toBeInTheDocument();
    expect(screen.getByTestId("settings-billing-header")).toHaveClass(
      "flex-col",
      "items-stretch",
      "lg:flex-row",
      "lg:items-start",
      "lg:justify-between"
    );
    expect(screen.getByRole("button", { name: "요금제 조정" })).toHaveClass(
      "w-full",
      "lg:w-auto"
    );

    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    await waitFor(() =>
      expect(
        screen.getByText(/구독이 .*에 만료됩니다\./)
      ).toBeInTheDocument()
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/payment/billing/cancel",
      expect.objectContaining({ method: "POST" })
    );
    // 해지 예약 후에는 취소 섹션이 사라진다
    expect(screen.queryByRole("button", { name: "취소" })).not.toBeInTheDocument();
  });

  it("결제 탭에 청구서 목록을 표시한다", async () => {
    mockPlanFetch({
      planId: "PRO",
      name: "Pro",
      subscription: {
        planId: "PRO",
        nextBillingAt: "2026-08-01T00:00:00.000Z",
        canceled: false,
      },
      orders: [
        {
          id: "o2",
          planId: "PRO",
          amount: 25_000,
          status: "DONE",
          date: "2026-07-01T00:00:00.000Z",
        },
        {
          id: "o1",
          planId: "PRO",
          amount: 25_000,
          status: "FAILED",
          date: "2026-06-01T00:00:00.000Z",
        },
      ],
    });
    renderModal();

    fireEvent.click(await screen.findByRole("button", { name: "결제" }));
    expect(screen.getByText("청구서")).toBeInTheDocument();
    expect(screen.getAllByText("₩25,000")).toHaveLength(2);
    expect(screen.getByText("Paid")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("결제 내역이 없으면 빈 안내를 표시한다", async () => {
    mockPlanFetch();
    renderModal();

    fireEvent.click(await screen.findByRole("button", { name: "결제" }));
    expect(screen.getByText("결제 내역이 없습니다.")).toBeInTheDocument();
  });

  it("무료 요금제는 결제 탭에 취소 섹션 없이 안내만 표시한다", async () => {
    mockPlanFetch();
    renderModal();

    fireEvent.click(await screen.findByRole("button", { name: "결제" }));
    expect(screen.getByText("무료 요금제를 사용 중입니다.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "취소" })).not.toBeInTheDocument();
  });

  it("구독 없는 유료 플랜(관리자 변경 등)은 무료 요금제로 표기하지 않는다", async () => {
    mockPlanFetch({ planId: "PREMIUM", name: "Premium", subscription: null });
    renderModal();

    fireEvent.click(await screen.findByRole("button", { name: "결제" }));
    expect(screen.getByText("Premium 요금제")).toBeInTheDocument();
    expect(
      screen.getByText("자동갱신 구독 없이 이용 중입니다.")
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "취소" })).not.toBeInTheDocument();
  });

  it("요금제 조정 버튼은 요금제 페이지로 이동한다", async () => {
    mockPlanFetch();
    renderModal();

    fireEvent.click(await screen.findByRole("button", { name: "결제" }));
    fireEvent.click(screen.getByRole("button", { name: "요금제 조정" }));
    expect(onClose).toHaveBeenCalled();
    expect(pushMock).toHaveBeenCalledWith("/pricing");
  });

  it("사용량 탭은 계좌/전략/백테스트 사용량 바를 표시한다", async () => {
    mockPlanFetch();
    renderModal();

    fireEvent.click(await screen.findByRole("button", { name: "사용량" }));
    expect(screen.getByText("3 / 10")).toBeInTheDocument();
    expect(screen.getByText("12 / 50")).toBeInTheDocument();
    expect(screen.getByText("7 / 100")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", { name: "백테스트 횟수" })
    ).toHaveAttribute("aria-valuenow", "7");
  });
});
