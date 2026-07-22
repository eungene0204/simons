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
    expect(
      within(usageNotice).getByText(
        /상호명 : 널스페이스\s+사업자등록번호 : 898-50-00737\s+통신판매업신고번호 : 2026-서울서대문-0758\s+대표 : 이응준\s+주소 : 서울특별시 서대문구 이화여대7길 37, 3층 S88호\s+이메일 : nullspace\.support@gmail\.com/
      )
    ).toBeInTheDocument();
  });
});
