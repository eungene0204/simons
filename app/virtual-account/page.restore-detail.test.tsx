import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VirtualAccountPage from "@/app/virtual-account/page";
import { rememberVirtualAccountDetail } from "@/components/virtual-account/virtualAccountDetailMemory";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
  }),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => (
    <div data-testid="dashboard-layout">{children}</div>
  ),
}));

vi.mock("@/components/virtual-account/VirtualAccountOverview", () => ({
  default: () => <div>계좌 목록</div>,
}));

describe("VirtualAccountPage detail restore", () => {
  const originalGetEntriesByType = window.performance.getEntriesByType.bind(
    window.performance
  );

  beforeEach(() => {
    window.sessionStorage.clear();
    vi
      .spyOn(window.performance, "getEntriesByType")
      .mockImplementation(originalGetEntriesByType);
  });

  afterEach(() => {
    replaceMock.mockReset();
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("restores the last visited account detail when entering the account route", async () => {
    rememberVirtualAccountDetail("account-123");
    vi.spyOn(window.performance, "getEntriesByType").mockReturnValue([
      {
        type: "navigate",
      } as PerformanceNavigationTiming,
    ]);

    render(<VirtualAccountPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/virtual-account/account-123");
    });
    expect(
      screen.getByRole("status", { name: "가상계좌 불러오는 중" })
    ).toBeInTheDocument();
    expect(screen.queryByText("계좌 페이지로 이동 중입니다...")).not.toBeInTheDocument();
    expect(screen.queryByText("계좌 목록")).not.toBeInTheDocument();
  });

  it("shows the account list when no account detail was visited", async () => {
    render(<VirtualAccountPage />);

    expect(await screen.findByText("계좌 목록")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("keeps the account list visible when the list page is reloaded", async () => {
    rememberVirtualAccountDetail("account-123");
    vi.spyOn(window.performance, "getEntriesByType").mockReturnValue([
      {
        type: "reload",
      } as PerformanceNavigationTiming,
    ]);

    render(<VirtualAccountPage />);

    expect(await screen.findByText("계좌 목록")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("shows the account list when returning with browser back-forward navigation", async () => {
    rememberVirtualAccountDetail("account-123");
    vi.spyOn(window.performance, "getEntriesByType").mockReturnValue([
      {
        type: "back_forward",
      } as PerformanceNavigationTiming,
    ]);

    render(<VirtualAccountPage />);

    expect(await screen.findByText("계좌 목록")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
