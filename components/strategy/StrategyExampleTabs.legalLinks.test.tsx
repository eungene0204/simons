import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { StrategyExampleTabs } from "./StrategyExampleTabs";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("StrategyExampleTabs legal links", () => {
  it("renders terms and privacy policy links in the usage notice", () => {
    render(<StrategyExampleTabs onSelectExample={vi.fn()} />);

    const usageNotice = screen.getByRole("contentinfo", { name: "전략연구소 이용 안내" });
    expect(within(usageNotice).getByRole("link", { name: "이용약관" })).toHaveAttribute(
      "href",
      "/?legal=terms"
    );
    expect(within(usageNotice).getByRole("link", { name: "개인정보처리방침" })).toHaveAttribute(
      "href",
      "/?legal=privacy"
    );
  });
});
