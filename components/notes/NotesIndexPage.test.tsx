import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SEED_NOTES as NOTES } from "@/lib/notes/notes";
import { NotesIndexPage } from "./NotesIndexPage";

describe("NotesIndexPage", () => {
  it("shows the title, every note linked under /notes, and the disclaimer", () => {
    render(<NotesIndexPage notes={NOTES} />);
    expect(screen.getByRole("heading", { level: 1, name: "연구노트" })).toBeInTheDocument();
    // 링크는 한 번만 모은다(노트마다 역할 조회를 돌리면 느리다). 시장만 다른 기록(KOSPI·KOSDAQ)은
    // 제목 앞부분이 같아 제목 전체로 찾는다.
    const links = screen.getAllByRole("link");
    for (const note of NOTES) {
      const link = links.find((el) => el.textContent?.includes(note.title));
      expect(link, note.slug).toHaveAttribute("href", `/notes/${note.slug}`);
    }
    expect(screen.getByText(/널스탁은 투자자문업자 또는 투자일임업자가 아니며/)).toBeInTheDocument();
  });

  it("publishes a CollectionPage list of every note (2026-11-04 — the list page had no JSON-LD)", () => {
    render(<NotesIndexPage notes={NOTES} />);
    const graph = JSON.parse(screen.getByTestId("notes-structured-data").innerHTML)["@graph"];
    expect(graph[0]).toMatchObject({ "@type": "CollectionPage", name: "연구노트" });
    expect(graph[0].mainEntity.itemListElement.map((item: { url: string }) => item.url)).toEqual(
      NOTES.map((note) => `https://www.nullstock.im/notes/${note.slug}`),
    );
  });

  it("shows the preparing notice when the DB has no notes", () => {
    render(<NotesIndexPage notes={[]} />);
    expect(screen.getByText("연구노트를 준비하고 있습니다.")).toBeInTheDocument();
    expect(screen.queryByTestId("notes-structured-data")).toBeNull();
  });
});
