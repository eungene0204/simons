import { describe, expect, it } from "vitest";
import { computeDockScrollDelta } from "./dockScroll";

const base = { navHeight: 60, margin: 16 };

describe("computeDockScrollDelta", () => {
  it("scrolls down just enough that the graph's bottom clears the docked card", () => {
    // graph 100..700, card starts at 500 -> bottom must end at 484: scroll 216
    expect(computeDockScrollDelta({ ...base, graphTop: 300, graphBottom: 700, cardTop: 500 })).toBe(216);
  });

  it("does not scroll when the graph already sits above the card", () => {
    expect(computeDockScrollDelta({ ...base, graphTop: 100, graphBottom: 400, cardTop: 500 })).toBe(0);
  });

  it("never pushes the graph's top under the menu bar when the graph is taller than the room", () => {
    // wants 400 but only 100 .. 76 = 24 of room above before the top hits the menu bar
    expect(computeDockScrollDelta({ ...base, graphTop: 100, graphBottom: 900, cardTop: 500 })).toBe(24);
    // top already at the limit: no scroll at all
    expect(computeDockScrollDelta({ ...base, graphTop: 76, graphBottom: 900, cardTop: 500 })).toBe(0);
  });

  it("scrolls back up when the graph's top is hidden and there is room below it", () => {
    // top at 20 (hidden), bottom 300, card at 500: up to 56 to show the top, room below is 184
    expect(computeDockScrollDelta({ ...base, graphTop: 20, graphBottom: 300, cardTop: 500 })).toBe(-56);
  });

  it("scrolls up only as far as keeps the bottom clear of the card", () => {
    // hidden top by 56, but only 10 of room below the bottom (490 vs 484 limit... 474)
    expect(computeDockScrollDelta({ ...base, graphTop: 20, graphBottom: 474, cardTop: 500 })).toBe(-10);
  });
});
