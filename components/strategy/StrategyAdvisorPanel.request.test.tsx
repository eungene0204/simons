import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StrategyAdvisorPanel } from "./StrategyAdvisorPanel";

const fetchMock = vi.fn();

describe("StrategyAdvisorPanel advisor request", () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("includes candidate backtest evaluation fields in advisor requests", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        strategy_score: 81,
        risk_score: 36,
        overfit_risk: "low",
        advice: [],
        suggested_experiments: [],
        ai_model_recommendation: {
          recommended: false,
          reason: "현재 규칙 기반 전략만으로도 충분합니다.",
        },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    render(
      <StrategyAdvisorPanel
        request={{
          user_prompt: "테스트 전략",
          parsed_strategy: {},
          backtest_result: { cagr: 0.04, mdd: -0.2, sharpe: 0.5 },
          candidate_backtest_result: { cagr: 0.08, mdd: -0.15, sharpe: 0.8 },
          evaluation_context: { oos_available: true },
        }}
      />
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledOnce();
    });

    const [, options] = fetchMock.mock.calls[0] as [string, { body: string }];
    expect(JSON.parse(options.body)).toMatchObject({
      candidate_backtest_result: { cagr: 0.08, mdd: -0.15, sharpe: 0.8 },
      evaluation_context: { oos_available: true },
    });
  });
});
