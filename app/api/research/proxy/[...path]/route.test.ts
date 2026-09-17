// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 리서치 프록시 회귀 테스트 — 비로그인 요청을 userId=1로 대체하던 폴백 제거(2026-09-03 감사).
// 세션 인정은 getCurrentUser(정지·이용 기한 판정 포함, 2026-09-17)에 맡긴다.
const { getCurrentUser } = vi.hoisted(() => ({ getCurrentUser: vi.fn() }));

vi.mock("@/lib/get-user", () => ({ getCurrentUser }));

const { GET, POST } = await import("./route");

function makeRequest(path: string) {
  return {
    nextUrl: new URL(`http://localhost${path}`),
    text: async () => "{}",
  } as any;
}

describe("/api/research/proxy", () => {
  const backendFetch = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", backendFetch);
    backendFetch.mockResolvedValue(
      new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } })
    );
  });

  it("세션이 없으면 401이고 백엔드를 호출하지 않는다(userId=1 대체 없음, 정지·기한 만료 포함)", async () => {
    getCurrentUser.mockResolvedValue(null);

    const res = await GET(makeRequest("/api/research/proxy/runs"), { params: Promise.resolve({ path: ["runs"] }) });
    const post = await POST(makeRequest("/api/research/proxy/runs"), { params: Promise.resolve({ path: ["runs"] }) });

    expect(res.status).toBe(401);
    expect(post.status).toBe(401);
    expect(backendFetch).not.toHaveBeenCalled();
  });

  it("로그인 사용자는 본인 userId를 X-User-Id로 넘긴다", async () => {
    getCurrentUser.mockResolvedValue({ id: 42 });

    const res = await GET(makeRequest("/api/research/proxy/runs"), { params: Promise.resolve({ path: ["runs"] }) });

    expect(res.status).toBe(200);
    expect(backendFetch.mock.calls[0][1].headers["X-User-Id"]).toBe("42");
  });
});
