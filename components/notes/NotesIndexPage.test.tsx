import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AD_SLOTS } from "@/lib/ads/adsense";
import { NOTES_PAGE_SIZE, SEED_NOTES as NOTES } from "@/lib/notes/notes";
import { NotesIndexPage } from "./NotesIndexPage";

describe("NotesIndexPage", () => {
  it("shows the title, the first page of notes linked under /notes, and the disclaimer", () => {
    render(<NotesIndexPage notes={NOTES} />);
    expect(screen.getByRole("heading", { level: 1, name: "퀀트 연구노트" })).toBeInTheDocument();
    // 링크는 한 번만 모은다(노트마다 역할 조회를 돌리면 느리다). 시장만 다른 기록(KOSPI·KOSDAQ)은
    // 제목 앞부분이 같아 제목 전체로 찾는다.
    const links = screen.getAllByRole("link");
    for (const note of NOTES.slice(0, NOTES_PAGE_SIZE)) {
      const link = links.find((el) => el.textContent?.includes(note.title));
      expect(link, note.slug).toHaveAttribute("href", `/notes/${note.slug}`);
    }
    expect(links.find((el) => el.textContent?.includes(NOTES[NOTES_PAGE_SIZE].title))).toBeUndefined();
    expect(screen.getByText(/널스탁은 투자자문업자 또는 투자일임업자가 아니며/)).toBeInTheDocument();
  });

  it("publishes a CollectionPage list of the notes on the current page (2026-11-04 — the list page had no JSON-LD)", () => {
    render(<NotesIndexPage notes={NOTES} page={2} />);
    const graph = JSON.parse(screen.getByTestId("notes-structured-data").innerHTML)["@graph"];
    expect(graph[0]).toMatchObject({ "@type": "CollectionPage", name: "퀀트 연구노트" });
    expect(graph[0].mainEntity.itemListElement.map((item: { url: string }) => item.url)).toEqual(
      NOTES.slice(NOTES_PAGE_SIZE, NOTES_PAGE_SIZE * 2).map((note) => `https://www.nullstock.im/notes/${note.slug}`),
    );
  });

  // 2026-11-07 — 목록이 한 쪽에 100편 넘게 쌓여 10편씩 쪽을 나누고 검색을 붙였다.
  it("splits the list into pages of ten with prev/next and page links", () => {
    const totalPages = Math.ceil(NOTES.length / NOTES_PAGE_SIZE);
    render(<NotesIndexPage notes={NOTES} page={2} />);
    const nav = screen.getByRole("navigation", { name: "퀀트 연구노트 쪽" });
    expect(nav.querySelector("[aria-current=page]")?.textContent).toBe("2");
    expect(screen.getByRole("link", { name: "이전" })).toHaveAttribute("href", "/notes");
    expect(screen.getByRole("link", { name: "다음" })).toHaveAttribute("href", "/notes?page=3");
    expect(screen.getByRole("link", { name: String(totalPages) })).toHaveAttribute("href", `/notes?page=${totalPages}`);
  });

  it("filters by the search words and keeps the query in page links", () => {
    const matches = NOTES.filter((note) => `${note.title} ${note.description} ${note.summary}`.includes("뉴스 전략"));
    expect(matches.length).toBeGreaterThan(NOTES_PAGE_SIZE);
    render(<NotesIndexPage notes={NOTES} query="뉴스 전략" />);
    expect(screen.getByText(new RegExp(`검색 결과 ${matches.length}편`))).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "퀀트 연구노트 검색" })).toHaveValue("뉴스 전략");
    expect(screen.getByRole("link", { name: "다음" })).toHaveAttribute(
      "href",
      `/notes?q=${encodeURIComponent("뉴스 전략").replace(/%20/g, "+")}&page=2`,
    );
  });

  it("says so when no note matches the search", () => {
    render(<NotesIndexPage notes={NOTES} query="존재하지않는검색어" />);
    expect(screen.getByText("검색어가 들어간 노트가 없습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "퀀트 연구노트 쪽" })).toBeNull();
  });

  it("shows the preparing notice when the DB has no notes", () => {
    render(<NotesIndexPage notes={[]} />);
    expect(screen.getByText("퀀트 연구노트를 준비하고 있습니다.")).toBeInTheDocument();
    expect(screen.queryByTestId("notes-structured-data")).toBeNull();
  });

  it("places side and below-list ads when notes exist, and none on the empty page", () => {
    const { unmount } = render(<NotesIndexPage notes={NOTES} />);
    const slots = () =>
      screen.queryAllByRole("complementary", { name: "광고" }).map((el) => el.querySelector("ins")?.getAttribute("data-ad-slot"));
    expect(slots()).toEqual([AD_SLOTS.sideLeft, AD_SLOTS.sideRight, AD_SLOTS.articleEnd]);
    unmount();
    render(<NotesIndexPage notes={[]} />);
    expect(slots()).toEqual([]);
  });
});
