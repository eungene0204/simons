import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import TrackedSymbolsSkeleton from "@/components/virtual-account/TrackedSymbolsSkeleton";

describe("TrackedSymbolsSkeleton", () => {
  it("추적 종목 로딩 중 shimmer 행을 기본 개수만큼 렌더링해야 함", () => {
    const { container } = render(<TrackedSymbolsSkeleton />);

    expect(screen.getByText("종목")).toBeInTheDocument();
    expect(screen.getByText("현재가")).toBeInTheDocument();
    expect(container.querySelectorAll(".shimmer")).toHaveLength(35);

    const scrollRegion = screen.getByTestId("tracked-symbols-skeleton-scroll");
    expect(scrollRegion).toHaveClass("overflow-x-auto", "lg:overflow-x-visible");
    expect(scrollRegion.firstElementChild).toHaveClass(
      "min-w-[520px]",
      "lg:min-w-0"
    );
  });
});
