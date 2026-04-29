import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StrategyAdvisorPanel } from "@/components/strategy/StrategyAdvisorPanel";

const fetchMock = vi.fn();

describe("StrategyAdvisorPanel", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("백엔드가 내려준 조언 문구를 그대로 보여준다", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        strategy_score: 72,
        risk_score: 48,
        overfit_risk: "low",
        advice: [
          {
            severity: "low",
            title: "과최적화 위험 낮음",
            body: "필터 조건 0개로 적정합니다. 전략 구조가 특정 과거 구간에 과도하게 맞춰졌을 가능성은 낮습니다. 단, 이는 과최적화 측면만의 평가이며 아래의 리스크 관리·청산 조건 개선과는 별개입니다.",
          },
          {
            severity: "medium",
            title: "손절 기준 없음",
            body: "하락 구간에서 손실이 빠르게 커질 수 있습니다.",
          },
        ],
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
        }}
      />
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/advisor/review",
        expect.objectContaining({ method: "POST" })
      );
    });

    expect(screen.getByText("과최적화 위험 낮음")).toBeInTheDocument();
    expect(screen.getByText(/전략 구조가 특정 과거 구간에 과도하게 맞춰졌을 가능성은 낮습니다/)).toBeInTheDocument();
    expect(screen.getByText("손절 기준 없음")).toBeInTheDocument();
  });

  it("구체 근거가 있는 저위험 과최적화 문구는 유지한다", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        strategy_score: 79,
        risk_score: 40,
        overfit_risk: "low",
        advice: [
          {
            severity: "low",
            title: "과최적화 위험 낮음",
            body: "거래 횟수 63회로 통계적 신뢰도가 충분합니다, CAGR 18%로 비현실적인 고수익 패턴이 없습니다. 전략 구조가 특정 과거 구간에 과도하게 맞춰졌을 가능성은 낮습니다.",
          },
        ],
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
        }}
      />
    );

    expect(await screen.findByText("과최적화 위험 낮음")).toBeInTheDocument();
    expect(screen.getByText(/거래 횟수 63회로 통계적 신뢰도가 충분합니다/)).toBeInTheDocument();
  });
});
