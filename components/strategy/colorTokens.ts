export const colorTokens = {
  title_main: "#B4B4B4",
  title_color: "#B4B4B4",
  main_white: "#FAFAFA",
} as const;

export type ColorTokenName = keyof typeof colorTokens;
