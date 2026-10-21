import { describe, expect, it, vi } from "vitest";
import type { ResearchNote } from "@prisma/client";

import { SEED_NOTES } from "./notes";
import { noteToCreateInput, rowToNote } from "./noteRow";

describe("noteRow mapping", () => {
  it("round-trips every seed note through the DB row shape without losing a field", () => {
    SEED_NOTES.forEach((note, index) => {
      const input = noteToCreateInput(note, index);
      const row = { ...input, id: "x", status: "PUBLISHED", faq: input.faq ?? null, createdAt: new Date(), updatedAt: new Date() };
      expect(rowToNote(row as unknown as ResearchNote)).toEqual(note);
    });
  });
});
