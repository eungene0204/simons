import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/lib/geo/useRegion", () => ({ useRegionHref: () => (href: string) => href }));

import StrategyShareView from "./StrategyShareView";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => body }));
}

describe("StrategyShareView", () => {
  it("공개 전략 카드에 공개 계좌 수익률과 계좌 링크를 보여준다", async () => {
    stubFetch({
      strategies: [
        {
          key: "s0", name: "RSI 반등", description: "RSI 30 이하 매수",
          avgReturnPct: 12.345, updatedAt: "2026-10-20T00:00:00Z",
          accounts: [{ id: "a1", name: "계좌1", currency: "KRW", status: "ACTIVE", returnPct: 12.345, createdAt: "2026-10-01T00:00:00Z" }],
        },
        {
          key: "s1", name: "계좌 없는 전략", description: null,
          avgReturnPct: null, updatedAt: "2026-10-20T00:00:00Z", accounts: [],
        },
      ],
    });

    render(<StrategyShareView />);

    await waitFor(() => expect(screen.getAllByTestId("shared-strategy-card")).toHaveLength(2));
    expect(screen.getAllByText("+12.35%").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /계좌1/ })).toHaveAttribute("href", "/shared/virtual-account/a1");
    expect(screen.getByText("공개된 운용 계좌가 없습니다")).toBeInTheDocument();
    expect(screen.getByText(/과거 수익률은 미래 수익을 보장하지 않습니다/)).toBeInTheDocument();
  });

  it("공개 전략이 없으면 빈 화면 안내를 보여준다", async () => {
    stubFetch({ strategies: [] });
    render(<StrategyShareView />);
    expect(await screen.findByText("아직 공개된 전략이 없습니다")).toBeInTheDocument();
  });
});
