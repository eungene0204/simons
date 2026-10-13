import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { GUIDE_ARTICLES } from "@/lib/guide/articles";
import { GuideArticlePage } from "./GuideArticlePage";
import { GuideIndexPage } from "./GuideIndexPage";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("GuideIndexPage", () => {
  it("renders the guide title as h1 and links every article", () => {
    render(<GuideIndexPage />);
    expect(screen.getByRole("heading", { level: 1, name: "백테스트 가이드" })).toBeInTheDocument();
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    for (const article of GUIDE_ARTICLES) {
      expect(hrefs).toContain(`/guide/${article.slug}`);
      expect(screen.getByRole("heading", { level: 2, name: article.title })).toBeInTheDocument();
    }
    expect(screen.getByTestId("guide-structured-data").textContent).toContain("CollectionPage");
  });
});

describe("GuideArticlePage", () => {
  const article = GUIDE_ARTICLES[0];

  it("renders title, summary, a table of contents that anchors to each section, and the disclaimer", () => {
    render(<GuideArticlePage article={article} />);

    expect(screen.getByRole("heading", { level: 1, name: article.title })).toBeInTheDocument();
    expect(screen.getByText(article.summary)).toBeInTheDocument();

    const toc = screen.getByRole("navigation", { name: "목차" });
    const links = within(toc).getAllByRole("link");
    expect(links).toHaveLength(article.sections.length);
    links.forEach((link, index) => {
      expect(link).toHaveAttribute("href", `#section-${index + 1}`);
      expect(document.getElementById(`section-${index + 1}`)).not.toBeNull();
    });

    expect(screen.getByText(/미래 수익은 보장되지 않습니다/)).toBeInTheDocument();
  });

  it("links related articles and embeds Article JSON-LD", () => {
    render(<GuideArticlePage article={article} />);

    const related = screen.getByRole("navigation", { name: "함께 읽을 글" });
    expect(within(related).getAllByRole("link")).toHaveLength(article.related.length);

    const json = screen.getByTestId("guide-structured-data").textContent ?? "";
    expect(json).toContain('"@type":"Article"');
    expect(json).toContain(article.title);
  });

  it("links back to the guide index and to the app", () => {
    render(<GuideArticlePage article={article} />);
    expect(screen.getByRole("link", { name: "백테스트 가이드" })).toHaveAttribute("href", "/guide");
    expect(screen.getByRole("link", { name: "전략 백테스트하기" })).toHaveAttribute("href", "/");
  });
});
