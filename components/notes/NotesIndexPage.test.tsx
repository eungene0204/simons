import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NOTES } from "@/lib/notes/notes";
import { NotesIndexPage } from "./NotesIndexPage";

describe("NotesIndexPage", () => {
  it("shows the title, every note linked under /notes, and the disclaimer", () => {
    render(<NotesIndexPage />);
    expect(screen.getByRole("heading", { level: 1, name: "연구노트" })).toBeInTheDocument();
    for (const note of NOTES) {
      expect(screen.getByRole("link", { name: new RegExp(note.title.slice(0, 12)) })).toHaveAttribute(
        "href",
        `/notes/${note.slug}`,
      );
    }
    expect(screen.getByText(/미래 수익은 보장되지 않습니다/)).toBeInTheDocument();
  });
});
