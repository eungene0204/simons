import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SEED_NOTES as NOTES } from "@/lib/notes/notes";
import { NotesIndexPage } from "./NotesIndexPage";

describe("NotesIndexPage", () => {
  it("shows the title, every note linked under /notes, and the disclaimer", () => {
    render(<NotesIndexPage notes={NOTES} />);
    expect(screen.getByRole("heading", { level: 1, name: "연구노트" })).toBeInTheDocument();
    for (const note of NOTES) {
      expect(screen.getByRole("link", { name: new RegExp(note.title.slice(0, 12).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })).toHaveAttribute(
        "href",
        `/notes/${note.slug}`,
      );
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
