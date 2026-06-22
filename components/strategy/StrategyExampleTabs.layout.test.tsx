import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StrategyExampleTabs } from "./StrategyExampleTabs";

describe("StrategyExampleTabs layout", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders only the active tab content when switching to my strategies", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ strategies: [] }),
    }));
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      bottom: 600,
      height: 600,
      left: 0,
      right: 1200,
      top: 0,
      width: 1200,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    render(<StrategyExampleTabs onSelectExample={vi.fn()} />);

    expect(screen.getByTestId("strategy-examples-content")).toBeInTheDocument();
    expect(screen.queryByTestId("strategy-my-content")).not.toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "내 전략" }));
    });

    expect(screen.queryByTestId("strategy-examples-content")).not.toBeInTheDocument();
    expect(screen.getByTestId("strategy-my-content")).toBeInTheDocument();
    expect(screen.getByTestId("strategy-tab-content")).toHaveStyle({ height: "600px" });
    expect(await screen.findByText("아직 저장된 전략이 없습니다")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo", { name: "전략연구소 이용 안내" })).toBeInTheDocument();
  });
});
