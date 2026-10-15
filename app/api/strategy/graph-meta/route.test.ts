// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// Public graph metadata proxy: passthrough, 502 on backend failure, and it must never
// reach the admin ontology endpoint.

const fetchBackend = vi.fn();
vi.mock("@/lib/server/backend", () => ({
  fetchBackend: (...a) => fetchBackend(...a),
}));

import { GET } from "./route";

const META = { version: "abc", indicators: {}, bindings: {}, classes: [], concepts: [] };

beforeEach(() => vi.clearAllMocks());

describe("GET /api/strategy/graph-meta", () => {
  it("passes the backend metadata through", async () => {
    fetchBackend.mockResolvedValue({ ok: true, json: async () => META });
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(META);
    expect(fetchBackend).toHaveBeenCalledTimes(1);
    expect(fetchBackend.mock.calls[0][0]).toBe("/strategy/graph-meta");
  });

  it("never calls the admin ontology endpoint", async () => {
    fetchBackend.mockResolvedValue({ ok: true, json: async () => META });
    await GET();
    for (const call of fetchBackend.mock.calls) {
      expect(String(call[0])).not.toContain("ontology");
    }
  });

  it("maps a backend error status to 502", async () => {
    fetchBackend.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    const res = await GET();
    expect(res.status).toBe(502);
  });

  it("maps an unreachable backend to 502", async () => {
    fetchBackend.mockRejectedValue(new Error("down"));
    const res = await GET();
    expect(res.status).toBe(502);
  });
});
