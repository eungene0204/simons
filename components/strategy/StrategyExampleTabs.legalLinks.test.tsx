import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StrategyExampleTabs } from "./StrategyExampleTabs";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

// 지역(useRegion)은 경로에서 파생된다 — 테스트별로 브라우저 경로를 바꿔 지역을 시뮬레이션한다.
const pathnameRef = { current: "/" };
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  usePathname: () => pathnameRef.current,
}));

beforeEach(() => {
  pathnameRef.current = "/";
});

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
    // 사업자 정보는 두 줄 — 대표까지 첫 줄, 주소·연락처는 다음 줄
    expect(
      within(usageNotice).getByText(
        /^상호명 : 널스페이스\s+사업자등록번호 : 898-50-00737\s+통신판매업신고번호 : 2026-서울서대문-0758\s+대표 : 이응준$/
      )
    ).toBeInTheDocument();
    expect(
      within(usageNotice).getByText(
        /^주소 : 서울특별시 서대문구 이화여대7길 37, 3층 S88호\s+이메일 :/,
        { exact: false }
      )
    ).toBeInTheDocument();
    expect(
      within(usageNotice).getByRole("link", { name: "nullspace.support@gmail.com" })
    ).toHaveAttribute("href", "mailto:nullspace.support@gmail.com");
  });

  it("글로벌(/us) 푸터에는 연락처(이메일)만 남기고 사업자 정보를 표시하지 않는다", () => {
    pathnameRef.current = "/us";
    render(<StrategyExampleTabs onSelectExample={vi.fn()} />);

    const usageNotice = screen.getByRole("contentinfo", { name: "전략연구소 이용 안내" });
    expect(
      within(usageNotice).getByRole("link", { name: "nullspace.support@gmail.com" })
    ).toHaveAttribute("href", "mailto:nullspace.support@gmail.com");

    const noticeText = usageNotice.textContent ?? "";
    expect(noticeText).not.toContain("Company:"); // 상호
    expect(noticeText).not.toContain("CEO:"); // 대표
    expect(noticeText).not.toContain("898-50-00737"); // 사업자등록번호
    expect(noticeText).not.toContain("2026-Seoul Seodaemun-0758"); // 통신판매업신고번호
    expect(noticeText).not.toContain("2026-서울서대문-0758");
    expect(noticeText).not.toMatch(/Address:|주소 :/); // 주소
  });
});
