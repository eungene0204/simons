// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 2026-10-11 경로 이탈 실측 — 비로그인 요청 '/api/stock/..%2F..%2Fontology%2Fgraph%3F/ohlcv'가
// 디코드된 파라미터('../../ontology/graph?')로 백엔드 /ontology/graph에 닿았다.
vi.mock("@/lib/cache", () => ({ cache: { get: () => null, set: () => {} } }));

const { GET } = await import("./route");
const req = () => ({ nextUrl: new URL("http://localhost/api/stock/x/ohlcv?limit=5") });

describe("GET /api/stock/[symbol]/ohlcv", () => {
  const backendFetch = vi.fn();
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", backendFetch);
    backendFetch.mockResolvedValue(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }));
  });

  it("디코드된 '..'·'/'·'?' 파라미터는 백엔드 경로를 벗어나지 못한다", async () => {
    await GET(req(), { params: { symbol: "../../ontology/graph?" } });
    const url = String(backendFetch.mock.calls[0][0]);
    expect(new URL(url).pathname).toBe("/stock/..%2F..%2Fontology%2Fgraph%3F/ohlcv");

    backendFetch.mockClear();
    const res = await GET(req(), { params: { symbol: ".." } });
    expect(res.status).toBe(400);
    expect(backendFetch).not.toHaveBeenCalled();
  });

  it("정상 종목 코드는 그대로 전달한다", async () => {
    await GET(req(), { params: { symbol: "005930" } });
    expect(String(backendFetch.mock.calls[0][0])).toMatch(/\/stock\/005930\/ohlcv\?limit=5$/);
  });
});
