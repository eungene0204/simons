import { beforeEach, describe, expect, it, vi } from "vitest";

const mockExecPromise = vi.fn();
const mockPromisify = vi.fn(() => mockExecPromise);

vi.mock("util", () => ({
  default: { promisify: mockPromisify },
  promisify: mockPromisify,
}));

vi.mock("child_process", () => ({
  default: { exec: vi.fn() },
  exec: vi.fn(),
}));

function makeRequest(body: object): Request {
  return new Request("http://localhost/api/backtest/explain", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/backtest/explain", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("MPS 런타임 오류 시 CPU fallback으로 재시도한다", async () => {
    mockExecPromise
      .mockRejectedValueOnce({
        stderr:
          "MPSNDArray.mm:831: failed assertion `Error: NDArray dimension length > INT_MAX'",
        message: "Command failed",
      })
      .mockResolvedValueOnce({
        stdout: JSON.stringify({
          status: "success",
          symbol: "005930",
          date: "2024-12-19",
          attention_map: [],
          shap_matrix: [],
          feature_importance_directional: [],
          feature_importance_absolute: [],
          features: [],
        }),
        stderr: "",
      });

    const { POST } = await import("@/app/api/backtest/explain/route");
    const res = await POST(makeRequest({ symbol: "005930", date: "2024-12-19" }));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.status).toBe("success");
    expect(mockExecPromise).toHaveBeenCalledTimes(2);

    const firstCall = mockExecPromise.mock.calls[0];
    const secondCall = mockExecPromise.mock.calls[1];
    expect(firstCall[1].env.XAI_FORCE_CPU).toBe("0");
    expect(secondCall[1].env.XAI_FORCE_CPU).toBe("1");
  });
});
