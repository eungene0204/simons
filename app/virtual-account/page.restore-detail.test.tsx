import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VirtualAccountPage from "@/app/virtual-account/page";
import { rememberVirtualAccountDetail } from "@/components/virtual-account/virtualAccountDetailMemory";

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => (
    <div data-testid="dashboard-layout">{children}</div>
  ),
}));

vi.mock("@/components/virtual-account/VirtualAccountOverview", () => ({
  default: () => <div>계좌 목록</div>,
}));

describe("VirtualAccountPage account list entry", () => {
  afterEach(() => {
    window.sessionStorage.clear();
  });

  it("shows the account list even when a previously visited detail remains", async () => {
    rememberVirtualAccountDetail("account-123");

    render(<VirtualAccountPage />);

    expect(await screen.findByText("계좌 목록")).toBeInTheDocument();
  });

  it("shows the account list when no account detail was visited", async () => {
    render(<VirtualAccountPage />);

    expect(await screen.findByText("계좌 목록")).toBeInTheDocument();
  });
});
