import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DashboardLayout from "./DashboardLayout";

const usePathname = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => usePathname(),
}));

describe("DashboardLayout", () => {
  beforeEach(() => {
    usePathname.mockReturnValue("/dashboard");
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      }
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("applies viewport-filling min-height to the page content wrapper", () => {
    const { container } = render(
      <DashboardLayout userName="tester">
        <div data-testid="page-root">
          <div>content</div>
        </div>
      </DashboardLayout>
    );

    expect(screen.getByText("content")).toBeInTheDocument();

    const wrapper = container.querySelector(
      ".relative.min-h-\\[calc\\(100vh-var\\(--top-menu-bar-height\\,76px\\)\\)\\]"
    );

    expect(wrapper).not.toBeNull();
    expect(wrapper?.className).toContain("[&>*]:min-h-[inherit]");
    expect(wrapper?.className).toContain("[&>*>*>:last-child]:flex-1");
  });
});
