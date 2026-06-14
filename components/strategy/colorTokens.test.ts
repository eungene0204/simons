import { describe, expect, it } from "vitest";
import { colorTokens } from "./colorTokens";

describe("colorTokens", () => {
  it("stores captured UI colors in one place", () => {
    expect(colorTokens).toEqual({
      title_main: "#B4B4B4",
      title_color: "#B4B4B4",
      main_white: "#FAFAFA",
    });
  });
});
