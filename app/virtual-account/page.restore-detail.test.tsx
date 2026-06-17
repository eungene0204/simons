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
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  afterEach(() => {
    replaceMock.mockReset();
    window.sessionStorage.clear();
  });

  it("restores the last visited account detail when entering the account route", async () => {
    rememberVirtualAccountDetail("account-123");

    render(<VirtualAccountPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/virtual-account/account-123");
    });
    expect(screen.queryByText("계좌 목록")).not.toBeInTheDocument();
  });

  it("shows the account list when no account detail was visited", async () => {
    render(<VirtualAccountPage />);

    expect(await screen.findByText("계좌 목록")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
