// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchBackendMock = vi.fn();
vi.mock("@/lib/server/backend", () => ({
  fetchBackend: (...args: unknown[]) => fetchBackendMock(...args),
}));

const { POST } = await import("@/app/api/stock/analyze/route");

function makeReq(body: unknown) {
  return new Request("http://localhost/api/stock/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/stock/analyze", () => {
  beforeEach(() => vi.clearAllMocks());

  it("백엔드 분석 결과를 그대로 전달한다", async () => {
    const result = { symbol: "005930", name: "삼성전자", recommendation: "NEUTRAL" };
    fetchBackendMock.mockResolvedValue({ ok: true, json: async () => result });

    const res = await POST(makeReq({ symbol: "005930" }));
    const data = await res.json();

    expect(fetchBackendMock).toHaveBeenCalledWith("/stock/analyze", expect.objectContaining({ method: "POST" }));
    expect(data.recommendation).toBe("NEUTRAL");
  });

  it("백엔드 오류 상태코드를 전파한다", async () => {
    fetchBackendMock.mockResolvedValue({
      ok: false,
      status: 422,
      statusText: "Unprocessable",
      json: async () => ({ detail: "분석할 종목을 찾을 수 없습니다." }),
    });

    const res = await POST(makeReq({ query: "음 글쎄" }));
    expect(res.status).toBe(422);
    const data = await res.json();
    expect(data.detail).toContain("종목");
  });

  it("잘못된 JSON은 400을 반환한다", async () => {
    const badReq = new Request("http://localhost/api/stock/analyze", { method: "POST", body: "not-json" });
    const res = await POST(badReq);
    expect(res.status).toBe(400);
  });
});
