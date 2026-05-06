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

  it("RAG 경험과 개선 후보 평가 결과를 표시한다", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        strategy_score: 81,
        risk_score: 36,
        overfit_risk: "low",
        advice: [],
        strategy_memory_context: {
          confidence: "high",
          data_sufficiency: "sufficient",
          similar_strategy_ids: ["case_rsi_trend"],
          retrieved_cases: [
            {
              case_strategy_id: "case_rsi_trend",
              lesson: "RSI 단독 전략은 장기 추세 필터와 함께 검증해야 합니다.",
              advice_success: true,
            },
          ],
        },
        candidate_strategy: {
          stop_loss_pct: 10,
          _advisor_candidate: {
            requires_backtest: true,
          },
        },
        advice_evaluation: {
          advice_success: true,
          improved_metrics: ["cagr", "sharpe", "mdd"],
          worsened_metrics: ["trade_count"],
          net_effect: "positive",
          reason: "수익 또는 위험 지표와 위험 대비 수익 지표가 함께 개선되었습니다.",
          overfitting_risk: "low",
          oos_validation_required: true,
        },
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

    expect(await screen.findByText("유사 전략 경험")).toBeInTheDocument();
    expect(screen.getByText("신뢰도 높음")).toBeInTheDocument();
    expect(screen.getByText(/RSI 단독 전략은 장기 추세 필터/)).toBeInTheDocument();
    expect(screen.getByText("개선 후보 평가")).toBeInTheDocument();
    expect(screen.getByText("OOS 필요")).toBeInTheDocument();
    expect(screen.getByText("CAGR")).toBeInTheDocument();
    expect(screen.getByText("거래 횟수")).toBeInTheDocument();
  });

  it("백엔드가 내려준 response_sections를 순서대로 표시한다", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        strategy_score: 68,
        risk_score: 52,
        overfit_risk: "medium",
        advice: [],
        response_sections: [
          {
            title: "전략 요약",
            body: "RSI 평균회귀 전략이며 백테스트 결과가 없어 성과는 단정하지 않습니다.",
          },
          {
            title: "현재 전략의 문제점",
            body: "손절과 OOS 검증 조건이 부족합니다.",
          },
          {
            title: "최종 추천",
            body: "후보 전략을 만든 뒤 동일 조건으로 재백테스트하세요.",
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

    expect(await screen.findByText("전략 리뷰")).toBeInTheDocument();
    expect(screen.getByText("전략 요약")).toBeInTheDocument();
    expect(screen.getByText(/성과는 단정하지 않습니다/)).toBeInTheDocument();
    expect(screen.getByText("현재 전략의 문제점")).toBeInTheDocument();
    expect(screen.getByText("최종 추천")).toBeInTheDocument();
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.getByText("02")).toBeInTheDocument();
    expect(screen.getByText("03")).toBeInTheDocument();
  });
});
