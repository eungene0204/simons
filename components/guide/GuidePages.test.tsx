import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { GUIDE_ARTICLES } from "@/lib/guide/articles";
import { SEED_NOTES as NOTES, buildNotesCollection } from "@/lib/notes/notes";
import { METHODOLOGY_ARTICLE, METHODOLOGY_COLLECTION } from "@/lib/methodology/methodology";

const NOTES_COLLECTION = buildNotesCollection(NOTES);
import * as AdSlotModule from "@/components/ads/AdSlot";
import { AD_SLOTS } from "@/lib/ads/adsense";
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

    expect(screen.getAllByText(/미래 수익은 보장되지 않습니다/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "자주 묻는 질문" })).toBeInTheDocument();
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

describe("GuideArticlePage with the research-notes collection", () => {
  const note = NOTES[0];

  it("renders result tables, links back to /notes, and points related reading at the guide", () => {
    render(<GuideArticlePage article={note} collection={NOTES_COLLECTION} />);
    const tables = screen.getAllByRole("table");
    expect(tables.length).toBe(note.sections.filter((section) => section.table).length);
    expect(within(tables[0]).getAllByRole("row")).toHaveLength(1 + note.sections.find((s) => s.table)!.table!.rows.length);
    expect(screen.getByRole("link", { name: "연구노트" })).toHaveAttribute("href", "/notes");
    const hrefs = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/guide/backtest-trading-costs");
    expect(screen.getByTestId("guide-structured-data").textContent).toContain(`/notes/${note.slug}`);
  });
});

describe("GuideArticlePage reproduction and methodology links", () => {
  const note = NOTES.find((item) => item.slug.startsWith("myth-"))!;

  it("links the methodology page from notes", () => {
    render(<GuideArticlePage article={note} collection={NOTES_COLLECTION} />);
    expect(screen.getByRole("link", { name: "백테스트 방법론" })).toHaveAttribute("href", "/methodology");
  });

  it("turns the call to action into an open-this-strategy link when a prompt is given", () => {
    render(<GuideArticlePage article={note} collection={NOTES_COLLECTION} openHref="/?prompt=x" />);
    expect(screen.getByRole("link", { name: "이 전략 그대로 열기" })).toHaveAttribute("href", "/?prompt=x");
    expect(screen.queryByRole("link", { name: "전략 백테스트하기" })).toBeNull();
  });

  it("renders the top-level methodology page without a collection crumb or methodology self-link", () => {
    render(<GuideArticlePage article={METHODOLOGY_ARTICLE} collection={METHODOLOGY_COLLECTION} />);
    const crumbs = within(screen.getByRole("navigation", { name: "경로" })).getAllByRole("link");
    expect(crumbs.map((link) => link.getAttribute("href"))).toEqual(["/"]);
    expect(screen.queryByRole("link", { name: "백테스트 방법론" })).toBeNull();
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });
});

describe("GuideArticlePage ads", () => {
  const adSlots = () =>
    screen.queryAllByRole("complementary", { name: "광고" }).map((slot) => slot.querySelector("ins")?.getAttribute("data-ad-slot"));

  it("places the side, mid-article and end ad units on a guide article and requests a fill for each", () => {
    window.adsbygoogle = [];
    const article = GUIDE_ARTICLES.find((item) => item.sections.length > 2)!;
    render(<GuideArticlePage article={article} />);
    expect(adSlots()).toEqual([AD_SLOTS.sideLeft, AD_SLOTS.sideRight, AD_SLOTS.articleMid, AD_SLOTS.articleEnd]);
    expect(window.adsbygoogle).toHaveLength(4);
  });

  it("pins the side ads to a fixed 160x600 size instead of the responsive format", () => {
    render(<GuideArticlePage article={GUIDE_ARTICLES[0]} />);
    const side = screen
      .getAllByRole("complementary", { name: "광고" })
      .map((slot) => slot.querySelector("ins")!)
      .find((ins) => ins.getAttribute("data-ad-slot") === AD_SLOTS.sideLeft)!;
    expect(side.style.width).toBe("160px");
    expect(side.style.height).toBe("600px");
    expect(side.hasAttribute("data-ad-format")).toBe(false);
  });

  it("keeps the end ad away from the open-this-strategy button on research notes", () => {
    const note = NOTES.find((item) => item.slug.startsWith("myth-"))!;
    render(<GuideArticlePage article={note} collection={NOTES_COLLECTION} openHref="/?prompt=x" />);
    expect(adSlots()).toContain(AD_SLOTS.articleEnd);
    const related = screen.getByRole("navigation", { name: "함께 읽을 글" });
    const endAd = screen.getAllByRole("complementary", { name: "광고" }).at(-1)!;
    expect(related.compareDocumentPosition(endAd) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("exports only the component from the client ad module so server pages get real slot numbers", () => {
    // "use client" 모듈의 상수를 서버 컴포넌트가 import하면 값이 아니라 클라이언트 참조가 와서 글 페이지가 500이 났다(2026-11-06).
    expect(Object.keys(AdSlotModule)).toEqual(["AdSlot"]);
  });

  it("shows no ads on the methodology page", () => {
    render(<GuideArticlePage article={METHODOLOGY_ARTICLE} collection={METHODOLOGY_COLLECTION} />);
    expect(adSlots()).toEqual([]);
  });
});
