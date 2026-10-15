import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GRAPH_META_URL, loadGraphMeta, resetGraphMetaForTests } from "./meta";

const META = { version: "v1", indicators: {}, bindings: {}, classes: [], concepts: [] };
const fetchMock = vi.fn();

beforeEach(() => {
  resetGraphMetaForTests();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("loadGraphMeta", () => {
  it("fetches only the public metadata endpoint and shares one request", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => META });
    const [a, b] = await Promise.all([loadGraphMeta(), loadGraphMeta()]);
    expect(a).toEqual(META);
    expect(b).toBe(a);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(GRAPH_META_URL);
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("admin");
  });

  it("does not cache a failure, so a retry hits only the metadata endpoint again", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 502, json: async () => ({}) });
    await expect(loadGraphMeta()).rejects.toThrow("graph-meta 502");
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => META });
    await expect(loadGraphMeta()).resolves.toEqual(META);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const call of fetchMock.mock.calls) expect(call[0]).toBe(GRAPH_META_URL);
  });

  it("rejects a malformed body", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ nope: 1 }) });
    await expect(loadGraphMeta()).rejects.toThrow("malformed");
  });
});
