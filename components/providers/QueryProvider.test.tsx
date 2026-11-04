import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
let pathname = "/";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace, refresh: vi.fn() }),
}));
vi.mock("@/lib/geo/useRegion", () => ({ useRegionHref: () => (href: string) => href }));

import QueryProvider from "./QueryProvider";

describe("AuthSessionGuard (QueryProvider)", () => {
  beforeEach(() => {
    replace.mockClear();
    global.fetch = vi.fn().mockResolvedValue({ json: async () => ({ user: null }) }) as any;
  });

  it("비로그인이 공개 가상계좌 링크를 열어도 홈으로 보내지 않는다", async () => {
    pathname = "/shared/virtual-account/acc-1";
    render(<QueryProvider>x</QueryProvider>);
    await new Promise((r) => setTimeout(r, 20));
    expect(global.fetch).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it("공개가 아닌 앱 화면은 비로그인이면 홈으로 보낸다", async () => {
    pathname = "/virtual-account/acc-1";
    render(<QueryProvider>x</QueryProvider>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });
});
