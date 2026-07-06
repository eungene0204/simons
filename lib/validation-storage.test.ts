import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buildWalkForwardSummary,
  buildMonteCarloSummary,
  saveValidation,
  listSavedValidations,
  getSavedValidation,
  deleteSavedValidation,
} from "./validation-storage";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(response: { ok: boolean; status?: number; json?: unknown }) {
  const fn = vi.fn().mockResolvedValue({
    ok: response.ok,
    status: response.status ?? (response.ok ? 200 : 500),
    json: async () => response.json,
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("buildWalkForwardSummary", () => {
  it("핵심 지표를 요약으로 뽑는다", () => {
    const summary = buildWalkForwardSummary({
      walk_forward_efficiency: 0.678,
      wfe_valid: true,
      n_splits: 7,
      aggregate: { avg_oos_cagr: 0.0075 },
    });
    expect(summary).toEqual({ wfe: 0.678, wfeValid: true, nSplits: 7, avgOosCagr: 0.0075 });
  });

  it("wfe_valid=false면 해석 불가로 표시할 수 있게 false를 보존한다", () => {
    const summary = buildWalkForwardSummary({ wfe_valid: false, n_splits: 5 });
    expect(summary.wfeValid).toBe(false);
    expect(summary.wfe).toBeNull();
  });
});

describe("buildMonteCarloSummary", () => {
  it("분포 핵심값을 요약으로 뽑는다", () => {
    const summary = buildMonteCarloSummary({
      nIterations: 1000,
      mode: "returns",
      cagr: { median: 0.12, p05: -0.03 },
      mdd: { p95: 0.28 },
    });
    expect(summary).toEqual({
      iterations: 1000,
      mode: "returns",
      medianCagr: 0.12,
      p05Cagr: -0.03,
      p95Mdd: 0.28,
    });
  });
});

describe("saveValidation", () => {
  it("POST /api/validation로 저장하고 id를 반환한다", async () => {
    const fetchMock = mockFetch({ ok: true, json: { id: "abc", createdAt: 1 } });
    const res = await saveValidation({
      modelType: "walkForward",
      strategyName: "테스트 전략",
      settings: { n_splits: 7 },
      result: { foo: "bar" },
    });
    expect(res.id).toBe("abc");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/validation");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body).modelType).toBe("walkForward");
  });

  it("실패 응답이면 예외를 던진다", async () => {
    mockFetch({ ok: false, status: 500 });
    await expect(
      saveValidation({ modelType: "monteCarlo", strategyName: "x", settings: {}, result: {} })
    ).rejects.toThrow(/저장 실패/);
  });
});

describe("listSavedValidations", () => {
  it("modelType 필터를 쿼리로 넘긴다", async () => {
    const fetchMock = mockFetch({ ok: true, json: [] });
    await listSavedValidations("monteCarlo");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/validation?modelType=monteCarlo");
  });

  it("필터가 없으면 쿼리 없이 호출한다", async () => {
    const fetchMock = mockFetch({ ok: true, json: [] });
    await listSavedValidations();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/validation");
  });
});

describe("getSavedValidation / deleteSavedValidation", () => {
  it("단건 조회는 /api/validation/[id]를 부른다", async () => {
    const fetchMock = mockFetch({ ok: true, json: { id: "abc", result: {} } });
    await getSavedValidation("abc");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/validation/abc");
  });

  it("삭제는 DELETE로 id를 넘긴다", async () => {
    const fetchMock = mockFetch({ ok: true, json: { success: true } });
    await deleteSavedValidation("a b");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/validation?id=a%20b");
    expect(init.method).toBe("DELETE");
  });
});
