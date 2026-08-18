// @ts-nocheck
/**
 * 리밸런싱 기간별 결과 비교 탭(FR-BT-064) — 백테스트 결과 페이지 '월별 수익률' 옆 세 번째 탭.
 *
 * - 실행 전에는 6주기 재실행 안내 + 실행 버튼만 보인다(자동 실행 금지 — 백테스트 6회 비용).
 * - SSE progress → 진행 문구, result → 비교표(엔진 수치) + AI 서술 + 안내 문구.
 * - 현재 설정이 6주기 밖(예: 리밸런싱 없음)이면 참고 행으로 덧붙는다.
 * - LLM 서술 실패(analysis_degraded)면 표는 남기고 안내만 띄운다.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import RebalanceComparisonSection, {
  orderComparisonRows,
} from "@/components/strategy/backtest/RebalanceComparisonSection";
import { buildCurrentSettingMetrics } from "@/components/strategy/backtest/rebalanceComparison";

const ROWS = [
  { period: "daily", cagr: 8, mdd: -25, sharpe_ratio: 0.8, profit_factor: 1.2, trade_count: 600, turnover: 900 },
  { period: "weekly", cagr: 12, mdd: -22, sharpe_ratio: 1.0, profit_factor: 1.4, trade_count: 300, turnover: 400 },
  { period: "monthly", cagr: 15, mdd: -20, sharpe_ratio: 1.3, profit_factor: 1.6, trade_count: 120, turnover: 200 },
  { period: "quarterly", cagr: 14, mdd: -19, sharpe_ratio: 1.25, profit_factor: 1.5, trade_count: 40, turnover: 80 },
  { period: "semiannual", cagr: 13.5, mdd: -18, sharpe_ratio: 1.2, profit_factor: null, trade_count: 20, turnover: 40 },
  { period: "yearly", cagr: 11, mdd: -17, sharpe_ratio: 1.0, profit_factor: 1.3, trade_count: 10, turnover: 20 },
];

const ANALYSIS = {
  summary: { recommended_rebalance_period: "monthly", confidence_score: 72, strategy_character: "장기 팩터 성격", stability_rating: "B" },
  evaluations: { monthly: "샤프 최고·인접 주기 유지", daily: "거래 과다" },
  analysis: {
    performance_analysis: "성과 서술",
    risk_analysis: "리스크 서술",
    transaction_cost_analysis: "비용 서술",
    overfitting_analysis: "과최적화 서술",
  },
  recommendation: { recommended_period: "monthly", reason: "인접 주기에서도 유지", warning: "기간이 짧다" },
};

function sse(events: unknown[]): Response {
  const body = events.map((e) => `data: ${typeof e === "string" ? e : JSON.stringify(e)}\n\n`).join("");
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

const CURRENT = buildCurrentSettingMetrics({ cagr: 9.5, maxDrawdown: -21, sharpe: 0.9, profitFactor: 1.1, trades: 77, turnoverRate: 150 });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("orderComparisonRows", () => {
  it("6주기를 짧은 → 긴 순으로 늘어놓고 현재 설정이 그 안에 있으면 표시만 한다", () => {
    const shuffled = [ROWS[3], ROWS[0], ROWS[5], ROWS[1], ROWS[4], ROWS[2]];
    const rows = orderComparisonRows(shuffled, "monthly", CURRENT);
    expect(rows.map((r) => r.period)).toEqual(["daily", "weekly", "monthly", "quarterly", "semiannual", "yearly"]);
    expect(rows.find((r) => r.period === "monthly")?.isCurrent).toBe(true);
    expect(rows.some((r) => r.isReference)).toBe(false);
  });

  it("현재 설정이 6주기 밖(리밸런싱 없음)이면 메인 결과 지표로 참고 행을 덧붙인다", () => {
    const rows = orderComparisonRows(ROWS, "none", CURRENT);
    expect(rows).toHaveLength(7);
    const ref = rows[6];
    expect(ref.period).toBe("none");
    expect(ref.isReference).toBe(true);
    expect(ref.cagr).toBe(9.5);
    expect(ref.trade_count).toBe(77);
  });
});

describe("buildCurrentSettingMetrics", () => {
  it("손익비 null(손실 0건)은 null로 두고 비수치는 null로 정리한다", () => {
    expect(buildCurrentSettingMetrics({ cagr: 1.23456, profitFactor: null, trades: NaN })).toEqual({
      cagr: 1.2346, mdd: null, sharpe_ratio: null, profit_factor: null, trade_count: null, turnover: null,
    });
  });
});

describe("RebalanceComparisonSection", () => {
  it("전략 설정이 없으면 실행 불가 안내만 보인다", () => {
    render(<RebalanceComparisonSection backtestDsl={null} currentMetrics={CURRENT} />);
    expect(screen.getByText(/백테스트 요청.*저장되어 있지 않아/)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("실행 버튼 → 진행 문구 → 비교표·AI 서술·현재 설정 참고 행을 그린다", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
      sse([
        { type: "progress", stage: "backtest", period: "monthly", index: 3, total: 6 },
        { type: "progress", stage: "analysis" },
        {
          type: "result",
          data: {
            status: "ok",
            current_period: "none",
            backtest_period: { start: "2020-01-02", end: "2024-12-30" },
            rebalance_results: ROWS,
            analysis: ANALYSIS,
            analysis_degraded: false,
          },
        },
        "[DONE]",
      ])
    );

    render(
      <RebalanceComparisonSection
        backtestDsl={{ symbols: ["005930"], risk: { max_positions: 10, rebalancing_period: "none" } }}
        strategyName="테스트 전략"
        universeName="KOSPI200"
        currentMetrics={CURRENT}
      />
    );

    // 자동 실행 없음 — 안내 + 버튼
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /리밸런싱 기간별 비교 실행/ }));

    await waitFor(() => expect(screen.getByTestId("rebalance-comparison-table")).toBeTruthy());

    // 요청 본문: 엔진 요청 + 전략명/유니버스 + 현재 설정 지표
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.base_strategy.risk.max_positions).toBe(10);
    expect(body.strategy_name).toBe("테스트 전략");
    expect(body.investment_universe).toBe("KOSPI200");
    expect(body.current.cagr).toBe(9.5);

    // 6주기 행 + 현재 설정(리밸런싱 없음) 참고 행
    for (const period of ["daily", "weekly", "monthly", "quarterly", "semiannual", "yearly", "none"]) {
      expect(screen.getByTestId(`rebalance-row-${period}`)).toBeTruthy();
    }
    const monthlyRow = screen.getByTestId("rebalance-row-monthly");
    expect(monthlyRow.textContent).toContain("+15.00%");
    expect(monthlyRow.textContent).toContain("적합");
    expect(monthlyRow.textContent).toContain("샤프 최고·인접 주기 유지");
    const noneRow = screen.getByTestId("rebalance-row-none");
    expect(noneRow.textContent).toContain("현재 설정");
    expect(noneRow.textContent).toContain("+9.50%");
    // 손익비 null(손실 0건)은 ∞ 표기
    expect(screen.getByTestId("rebalance-row-semiannual").textContent).toContain("∞");

    // 요약 배지 + 4개 서술 + 판단 근거 + 안내
    expect(screen.getByText("장기 팩터 성격")).toBeTruthy();
    expect(screen.getByText("72/100")).toBeTruthy();
    expect(screen.getByText("성과 서술")).toBeTruthy();
    expect(screen.getByText("과최적화 서술")).toBeTruthy();
    expect(screen.getByText("인접 주기에서도 유지")).toBeTruthy();
    expect(screen.getByText(/투자 조언이 아닙니다/)).toBeTruthy();
    expect(screen.getByText(/2020-01-02 ~ 2024-12-30/)).toBeTruthy();
  });

  it("AI 서술이 실패(analysis_degraded)해도 수치 표는 남기고 안내를 띄운다", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      sse([
        { type: "result", data: { status: "ok", current_period: "monthly", rebalance_results: ROWS, analysis: null, analysis_degraded: true } },
        "[DONE]",
      ])
    );
    render(<RebalanceComparisonSection backtestDsl={{ risk: { max_positions: 5 } }} currentMetrics={CURRENT} />);
    fireEvent.click(screen.getByRole("button", { name: /리밸런싱 기간별 비교 실행/ }));
    await waitFor(() => expect(screen.getByTestId("rebalance-comparison-table")).toBeTruthy());
    expect(screen.getByRole("status").textContent).toContain("AI 서술을 생성하지 못해");
    expect(screen.getAllByTestId(/rebalance-row-/)).toHaveLength(6);
    expect(screen.getByTestId("rebalance-row-monthly").textContent).toContain("현재 설정");
  });

  it("보유 상한이 없는 전략도 6주기 표를 그대로 보여주고 안내(notices)만 덧붙인다", async () => {
    // 2026-08-18 사용자 지시: 리밸런싱 설정이 없어도 그냥 계산해 보여줄 것.
    vi.spyOn(global, "fetch").mockResolvedValue(
      sse([
        {
          type: "result",
          data: {
            status: "ok", current_period: "none", rebalance_results: ROWS, analysis: null, analysis_degraded: true,
            notices: ["이 전략은 최대 보유 종목 수·비율 선정이 없어 리밸런싱 주기가 결과에 영향을 주지 않습니다 — 6주기 결과가 모두 같게 나올 수 있어요."],
          },
        },
        "[DONE]",
      ])
    );
    render(<RebalanceComparisonSection backtestDsl={{ risk: {} }} currentMetrics={CURRENT} />);
    fireEvent.click(screen.getByRole("button", { name: /리밸런싱 기간별 비교 실행/ }));
    await waitFor(() => expect(screen.getByTestId("rebalance-comparison-table")).toBeTruthy());
    expect(screen.getByRole("note").textContent).toContain("영향을 주지 않습니다");
    expect(screen.getAllByTestId(/rebalance-row-/)).toHaveLength(7); // 6주기 + 현재 설정(없음) 참고 행
  });

  it("저장된 전략 DSL에 symbols가 없으면 빈 배열로 채워 보낸다(백엔드 스키마 필수 필드)", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
      sse([{ type: "result", data: { status: "ok", current_period: "monthly", rebalance_results: ROWS, analysis: null, analysis_degraded: true } }, "[DONE]"])
    );
    render(<RebalanceComparisonSection backtestDsl={{ universe_id: "kospi200", entry: {}, exit: {}, risk: { max_positions: 5 } }} currentMetrics={CURRENT} />);
    fireEvent.click(screen.getByRole("button", { name: /리밸런싱 기간별 비교 실행/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).base_strategy.symbols).toEqual([]);
  });

  it("SSE error 이벤트는 오류 문구 + 다시 실행 버튼으로 표시한다", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      sse([{ type: "error", message: "리밸런싱 기간별 비교가 제한 시간(3600초)을 초과해 중단되었습니다." }, "[DONE]"])
    );
    render(<RebalanceComparisonSection backtestDsl={{ risk: { max_positions: 5 } }} currentMetrics={CURRENT} />);
    fireEvent.click(screen.getByRole("button", { name: /리밸런싱 기간별 비교 실행/ }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("제한 시간"));
    expect(screen.getByRole("button", { name: /다시 실행/ })).toBeTruthy();
  });
});
