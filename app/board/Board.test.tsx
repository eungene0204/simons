import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Board from "./Board";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); history.replaceState(null, "", "/board"); });
it("renders an empty public list without requiring authentication", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ posts: [], count: 0 }) }));
  render(<Board />);
  expect(await screen.findByText("아직 게시글이 없습니다.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "글쓰기" })).toBeTruthy();
});
it("renders potentially dangerous content only as text", async () => {
  history.replaceState(null, "", "/board?id=one");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ post: { id: "one", title: "제목", body: '<img src=x onerror="alert(1)">', nickname: "익명", category: "자유", createdAt: new Date().toISOString() }, comments: [], count: 0 }) }));
  const { container } = render(<Board />);
  await waitFor(() => expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeTruthy());
  expect(container.querySelector("img")).toBeNull();
});
