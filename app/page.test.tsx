import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import HomePage from "./page";

vi.mock("./analytics/page", () => ({
  default: () => <div>전략연구소 메인 화면</div>,
}));

describe("HomePage", () => {
  it("renders the strategy lab main page at the root path", () => {
    render(<HomePage />);

    expect(screen.getByText("전략연구소 메인 화면")).toBeInTheDocument();
  });
});
