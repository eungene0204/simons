import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MarketSnapshot from "./MarketSnapshot";

const usePathnameMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock(),
}));

describe("MarketSnapshot", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        kospi: { value: 3123.45, change: 12.3, changePercent: 0.4 },
        kosdaq: { value: 987.65, change: -2.1, changePercent: -0.21 },
        nasdaq: { value: 18888.88, change: 10.2, changePercent: 0.05 },
        sp500: { value: 5555.55, change: 6.7, changePercent: 0.12 },
        exchangeRate: { value: 1380.1, change: 2.4, changePercent: 0.17 },
        vix: { value: 16.32, change: -0.8, changePercent: -4.67 },
      }),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not render anything on the dashboard route", () => {
    usePathnameMock.mockReturnValue("/dashboard");

    const { container } = render(<MarketSnapshot />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders the market snapshot outside the dashboard route", async () => {
    usePathnameMock.mockReturnValue("/kospi");

    render(<MarketSnapshot />);

    expect(await screen.findByText("코스피")).toBeInTheDocument();
    expect(screen.getByText("코스닥")).toBeInTheDocument();
    expect(screen.getByText("나스닥")).toBeInTheDocument();
    expect(screen.getByTestId("market-snapshot-grid")).toHaveClass(
      "grid-cols-2",
      "sm:grid-cols-3",
      "lg:grid-cols-6"
    );
    expect(screen.getAllByTestId("market-snapshot-cell")[0]).toHaveClass(
      "p-2",
      "sm:p-3"
    );
  });
});
