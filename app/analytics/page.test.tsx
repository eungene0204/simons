import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StrategyLabPage from "./page";

vi.mock("./new/page", () => ({
  default: () => <div>전략 만들기 페이지</div>,
}));

describe("StrategyLabPage", () => {
  it("renders the strategy creation page as the strategy lab main page", () => {
    render(<StrategyLabPage />);

    expect(screen.getByText("전략 만들기 페이지")).toBeInTheDocument();
  });
});
