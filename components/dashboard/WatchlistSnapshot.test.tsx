import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WatchlistSnapshot from "./WatchlistSnapshot";

describe("WatchlistSnapshot", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses two mobile columns and restores the six-column desktop grid", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        {
          symbol: "005930",
          name: "삼성전자",
          price: 72_000,
          changePercent: 1.25,
        },
      ],
    }));

    render(<WatchlistSnapshot />);

    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-snapshot-header")).toHaveClass(
      "px-3",
      "sm:px-4",
      "lg:px-5"
    );
    expect(screen.getByTestId("watchlist-snapshot-grid")).toHaveClass(
      "grid-cols-2",
      "sm:grid-cols-3",
      "lg:grid-cols-6"
    );
    expect(screen.getByTestId("watchlist-snapshot-cell")).toHaveClass(
      "p-2",
      "sm:p-3"
    );
  });
});
