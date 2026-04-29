import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PromptBacktestExperimentPage from "./page";

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const generatedPrompts = [
  {
    id: "prompt_001",
    text: "KOSPI200에서 RSI 30 이하 전략을 테스트해줘.",
    category: "technical_mean_reversion",
    complexity: "intermediate",
    risk_profile: "moderate",
    expected_blocks: ["rsi", "take_profit"],
  },
  {
    id: "prompt_002",
    text: "KOSPI에서 PBR 1 이하 전략을 테스트해줘.",
    category: "value_fundamental",
    complexity: "advanced",
    risk_profile: "conservative",
    expected_blocks: ["pbr", "per"],
  },
];

const experimentDetail = {
  id: "prompt_exp_test",
  status: "completed",
  totalPrompts: 3,
  completedCount: 2,
  cacheHitCount: 1,
  failedCount: 1,
  skippedCount: 0,
  resultFilePath: "data/advisor-learning/strategy_prompt_experiment_result.json",
  summaryFilePath: "data/advisor-learning/strategy_prompt_experiment_summary.json",
  datasetFilePath: "data/advisor-learning/strategy_advisor_learning_dataset.jsonl",
  rulesFilePath: "data/advisor-learning/strategy_advisor_rules.json",
  patternsFilePath: "data/advisor-learning/strategy_advisor_patterns.csv",
  candidates: [
    {
      prompt_id: "prompt_001",
      prompt: "RSI 반등 전략",
      category: "technical_mean_reversion",
      complexity: "intermediate",
      risk_profile: "moderate",
      expected_blocks: ["rsi", "take_profit"],
      extracted_blocks: ["rsi", "take_profit"],
      strategy_id: "hash_rsi",
      status: "computed",
      metrics: {
        cagr: 8,
        total_return: 25,
        sharpe: 1.1,
        max_drawdown: -12,
        profit_factor: 1.4,
        trades: 34,
      },
      quality_score: 0.62,
    },
    {
      prompt_id: "prompt_002",
      prompt: "52주 신고가 거래량 전략",
      category: "breakout_volume",
      complexity: "advanced",
      risk_profile: "aggressive",
      expected_blocks: ["breakout_52w", "volume_spike"],
      extracted_blocks: ["breakout_52w", "volume_spike"],
      strategy_id: "hash_breakout",
      status: "cache_hit",
      metrics: {
        cagr: 19,
        total_return: 61,
        sharpe: 1.5,
        max_drawdown: -18,
        profit_factor: 1.9,
        trades: 44,
      },
      quality_score: 0.74,
    },
    {
      prompt_id: "prompt_003",
      prompt: "너무 애매한 실패 전략",
      category: "ambiguous_beginner_prompts",
      complexity: "beginner",
      risk_profile: "moderate",
      expected_blocks: ["rsi"],
      extracted_blocks: ["rsi"],
      strategy_id: null,
      status: "failed",
      error_type: "parse_error",
      error_message: "조건을 파싱하지 못했습니다.",
      metrics: null,
      quality_score: null,
    },
  ],
};

const analysisPayload = {
  best_single_indicators: {
    rsi: {
      count: 2,
      median_cagr: 8,
      median_sharpe: 1.1,
      median_mdd: -12,
      median_profit_factor: 1.4,
      median_trades: 34,
      median_quality_score: 0.62,
      confidence: "medium",
    },
  },
  best_indicator_combinations: {
    "breakout_52w+volume_spike": {
      combination_count: 1,
      median_cagr: 19,
      median_sharpe: 1.5,
      median_mdd: -18,
      median_profit_factor: 1.9,
      median_trades: 44,
      median_quality_score: 0.74,
      confidence: "low",
    },
  },
  best_parameter_ranges: {
    "stop_loss_pct:5-10": {
      count: 12,
      median_cagr: 10,
      median_sharpe: 1.2,
      median_mdd: -10,
      median_profit_factor: 1.5,
      median_trades: 40,
      median_quality_score: 0.66,
      confidence: "medium",
    },
  },
  parser_failure_patterns: {
    parse_error: {
      count: 1,
      parser_improvement_suggestion: "지원 지표 표현을 더 명확히 수집하세요.",
    },
  },
  weak_patterns: [
    {
      pattern: "missing_exit_rule",
      coach_message: "청산 조건이 없어 MDD가 커질 가능성이 있습니다.",
    },
  ],
  high_risk_patterns: [],
};

describe("PromptBacktestExperimentPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const body = init?.body ? JSON.parse(String(init.body)) : {};

      if (url === "/api/strategy/prompt-experiments" && body.action === "generate") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ totalPrompts: 300, prompts: generatedPrompts }),
        });
      }

      if (url === "/api/strategy/prompt-experiments" && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ experimentId: "prompt_exp_test", status: "queued" }),
        });
      }

      if (url === "/api/strategy/prompt-experiments?id=prompt_exp_test") {
        return Promise.resolve({
          ok: true,
          json: async () => experimentDetail,
        });
      }

      if (url === "/api/strategy/prompt-experiments?id=prompt_exp_test&analysis=true") {
        return Promise.resolve({
          ok: true,
          json: async () => analysisPayload,
        });
      }

      return Promise.reject(new Error(`Unexpected fetch ${url}`));
    });
  });

  it("renders controls, progress, sorting, tabs, failures, insights, and export links", async () => {
    render(<PromptBacktestExperimentPage />);

    expect(screen.getByRole("button", { name: /300개 전략 프롬프트 생성/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /배치 실행 시작/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /실행 취소/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /300개 전략 프롬프트 생성/ }));
    await screen.findByText("300개 전략 프롬프트 생성");
    await waitFor(() => expect(screen.getByText("Configured total: 300")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /배치 실행 시작/ }));
    await waitFor(() => expect(screen.getByText("100%")).toBeInTheDocument());
    expect(screen.getByText("JSON export")).toHaveAttribute(
      "href",
      "/api/strategy/prompt-experiments?id=prompt_exp_test&export=json"
    );
    expect(screen.getByText("CSV export")).toHaveAttribute(
      "href",
      "/api/strategy/prompt-experiments?id=prompt_exp_test&export=csv"
    );

    fireEvent.change(screen.getByLabelText("sort"), { target: { value: "cagr" } });
    const pageText = document.body.textContent ?? "";
    expect(pageText.indexOf("52주 신고가 거래량 전략")).toBeLessThan(pageText.indexOf("RSI 반등 전략"));

    fireEvent.click(screen.getByRole("button", { name: "실패 프롬프트 분석" }));
    expect(screen.getAllByText("parse_error").length).toBeGreaterThan(0);
    expect(screen.getByText("너무 애매한 실패 전략")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "지표별 성과 분석" }));
    expect(screen.getAllByText("rsi").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "조합별 성과 분석" }));
    expect(screen.getByText("breakout_52w+volume_spike")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "파라미터별 성과 분석" }));
    expect(screen.getByText("stop_loss_pct:5-10")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "코치 개선 인사이트" }));
    expect(screen.getByText("strategy_experiment_learning")).toBeInTheDocument();
    expect(screen.getByText("data/advisor-learning/strategy_prompt_experiment_summary.json")).toBeInTheDocument();
  });
});
