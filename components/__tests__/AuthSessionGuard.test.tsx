import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import QueryProvider from "@/components/providers/QueryProvider";

// 회귀 가드: 전역 세션 가드(AuthSessionGuard)는 비로그인 방문자를 홈으로 되돌린다.
// 인증 화면이 공개 경로 목록에서 빠지면 그 화면에 머물 수가 없다 — 2026-09-14 사고:
// 새로 만든 /guest(테스터 입장)가 목록에 없어 폼을 보기도 전에 튕겼다.

const { pathnameMock } = vi.hoisted(() => ({ pathnameMock: { current: "/" } }));
const replaceMock = vi.fn();
const refreshMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameMock.current,
  useRouter: () => ({ replace: replaceMock, refresh: refreshMock }),
}));

function renderAt(pathname: string) {
  pathnameMock.current = pathname;
  return render(
    <QueryProvider>
      <div>content</div>
    </QueryProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // 비로그인 세션 — /api/user가 사용자를 돌려주지 않는다.
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ json: async () => ({ user: null }) })
  );
});

describe("AuthSessionGuard 공개 경로", () => {
  it.each(["/guest", "/us/guest", "/login", "/register", "/"])(
    "%s 는 비로그인이어도 머문다(세션 조회조차 하지 않는다)",
    async (pathname) => {
      renderAt(pathname);
      await waitFor(() => expect(fetch).not.toHaveBeenCalled());
      expect(replaceMock).not.toHaveBeenCalled();
    }
  );

  it("보호 경로는 비로그인일 때 홈으로 되돌린다", async () => {
    renderAt("/dashboard");
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/"));
  });
});
