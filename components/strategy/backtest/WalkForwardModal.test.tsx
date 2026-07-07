// @ts-nocheck
import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import WalkForwardModal from "./WalkForwardModal";

function buildDates(length: number) {
  return Array.from({ length }, (_, index) => {
    const date = new Date(Date.UTC(2024, 0, 1 + index));
    return date.toISOString().slice(0, 10);
  });
}

const baseStrategy = {
  entry: {
    conditions: [
      { id: "pbr_filter", type: "filter", params: { value: 1 } },
    ],
  },
  risk: {
    stop_loss_pct: 10,
    take_profit_pct: 20,
  },
};

describe("WalkForwardModal", () => {
  it("백테스트 기간 슬라이더를 기존 요청 설정으로 변환한다", async () => {
    const onRun = vi.fn().mockResolvedValue({
      status: "ok",
      n_splits: 5,
      anchor: false,
      target_metric: "cagr",
      windows: [],
      aggregate: {},
      combined_equity: [],
      combined_dates: [],
      walk_forward_efficiency: 0,
    });

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={onRun}
          backtestDates={buildDates(240)}
          baseStrategy={baseStrategy}
          optimizationTargets={[
            { id: "summary-0", label: "PBR" },
            { id: "summary-1", label: "손절라인" },
            { id: "summary-2", label: "익절라인" },
          ]}
        />
      );
    });

    act(() => {
      fireEvent.change(screen.getByLabelText("학습기간"), { target: { value: "84" } });
      fireEvent.change(screen.getByLabelText("검증기간"), { target: { value: "28" } });
    });

    expect(screen.getByText("예상 구간 수")).toBeInTheDocument();
    expect(screen.queryByText("현재 설정")).not.toBeInTheDocument();
    expect(screen.queryByText("최적화 목표 지표")).not.toBeInTheDocument();
    expect(screen.queryByText("첫 구간 미리보기")).not.toBeInTheDocument();
    expect(screen.getByTestId("walk-forward-panel")).not.toHaveClass("h-full", "flex");
    expect(screen.getAllByText("2024.01.01 - 2024.03.24").length).toBeGreaterThan(0);
    expect(screen.getAllByText("최적화 대상 파라미터")[0]).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /베이지안 최적화 유망한 후보를 우선 탐색하며/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /베이지안 최적화 유망한 후보를 우선 탐색하며/ })).toHaveClass("bg-white/[0.03]");
    expect(screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })).toHaveAttribute("aria-pressed", "false");
    expect(
      screen
        .getByRole("button", { name: /베이지안 최적화 유망한 후보를 우선 탐색하며/ })
        .compareDocumentPosition(screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      screen.getAllByText("최적화 대상 파라미터")[0].compareDocumentPosition(screen.getAllByText("베이지안 최적화 시도 횟수")[0]) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "PBR" })).toHaveClass("min-h-[86px]");
    expect(screen.getByRole("button", { name: "PBR" })).toHaveTextContent("PBR");
    expect(within(screen.getByRole("button", { name: "PBR" })).getByTestId("walk-forward-target-range-PBR")).toHaveTextContent("0.8~1.2");
    expect(screen.getByRole("button", { name: "PBR" })).not.toHaveTextContent("0.25");
    expect(screen.getByRole("button", { name: "PBR" })).not.toHaveTextContent(/step/i);
    expect(screen.getByText("손절라인")).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "손절라인" })).getByTestId("walk-forward-target-range-손절라인")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "손절라인" })).not.toHaveTextContent("2.5%p");
    expect(screen.getByRole("button", { name: "손절라인" })).not.toHaveTextContent(/step/i);
    expect(within(screen.getByRole("button", { name: "익절라인" })).getByTestId("walk-forward-target-range-익절라인")).toHaveTextContent("5%p~60%p");
    expect(screen.getByRole("button", { name: "익절라인" })).not.toHaveTextContent(/step/i);
    expect(screen.queryByText("CAGR")).not.toBeInTheDocument();
    expect(screen.getByLabelText("베이지안 최적화 시도 횟수 도움말")).toBeInTheDocument();
    expect(screen.getByText(/파라미터 조합을 몇 번 탐색할지/)).toBeInTheDocument();
    expect(screen.getByLabelText("IS 창 방식 도움말")).toBeInTheDocument();
    expect(screen.getByText(/IS\(In-Sample\)는 파라미터를 맞추는 학습 구간/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "30회" })).toHaveClass("rounded-md");
    expect(screen.getByRole("button", { name: "롤링" })).toHaveClass("rounded-md");
    const timeline = screen.getByTestId("walk-forward-period-timeline");
    expect(within(timeline).getAllByText("학습기간").length).toBeGreaterThan(0);
    expect(within(timeline).getAllByText("검증기간").length).toBeGreaterThan(0);
    expect(screen.getByTestId("walk-forward-timeline-train")).toHaveStyle({ width: "35%" });
    expect(screen.getByTestId("walk-forward-timeline-train")).toHaveClass("text-white");
    expect(screen.getByTestId("walk-forward-timeline-train")).toHaveClass("border", "border-white/[0.18]");
    expect(screen.getByTestId("walk-forward-timeline-train")).not.toHaveClass("bg-[#3f78b5]");
    expect(screen.getByTestId("walk-forward-timeline-validation")).toHaveClass("text-white");
    expect(screen.getByTestId("walk-forward-timeline-validation")).toHaveClass("border", "border-white/[0.18]");
    expect(screen.getByTestId("walk-forward-timeline-validation")).toHaveClass("bg-white/[0.08]");
    expect(screen.getByTestId("walk-forward-timeline-validation")).not.toHaveClass("bg-[#c84b36]");
    expect(screen.getByTestId("walk-forward-timeline-validation")).toHaveStyle({
      width: "11.666666666666666%",
    });
    expect(screen.queryByTestId("walk-forward-timeline-train-dates")).not.toBeInTheDocument();
    expect(screen.queryByTestId("walk-forward-timeline-validation-dates")).not.toBeInTheDocument();
    expect(screen.getByTestId("walk-forward-timeline-axis-train-dates")).toHaveTextContent(
      "2024.01.01 - 2024.03.24"
    );
    expect(screen.getByTestId("walk-forward-timeline-axis-train-dates")).not.toHaveTextContent("학습기간");
    expect(screen.getByTestId("walk-forward-timeline-axis-train-dates")).toHaveClass("text-gray-500");
    expect(screen.getByTestId("walk-forward-timeline-axis-train-dates")).toHaveStyle({
      left: "17.364016736401673%",
    });
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).toHaveTextContent(
      "2024.03.25 - 2024.04.21"
    );
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).not.toHaveTextContent("검증기간");
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).toHaveClass("text-gray-500");
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).toHaveStyle({
      left: "40.79497907949791%",
    });
    expect(screen.queryByTestId("walk-forward-timeline-axis-train-range")).not.toBeInTheDocument();
    expect(screen.queryByTestId("walk-forward-timeline-axis-validation-range")).not.toBeInTheDocument();
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).toHaveClass("top-0");
    expect(within(timeline).queryByText("2024.08.27")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "PBR" }));
    const pbrStepDialog = screen.getByRole("dialog", { name: "PBR 값 설정" });
    expect(pbrStepDialog).toBeInTheDocument();
    expect(pbrStepDialog.firstElementChild).toHaveClass("rounded-xl");
    expect(within(pbrStepDialog).getByRole("button", { name: "기본값" })).toHaveClass("rounded-md");
    expect(within(pbrStepDialog).getByRole("button", { name: "닫기" })).toHaveClass("rounded-md");
    expect(within(pbrStepDialog).getByRole("button", { name: "저장" })).toHaveClass("rounded-md");
    // 기본값은 실제로 적용되는 자동 생성 범위(PBR=1 주변 0.8~1.2)를 그대로 보여준다.
    expect(screen.getByLabelText("PBR 하한값")).toHaveAttribute("type", "number");
    expect(screen.getByLabelText("PBR 하한값")).toHaveValue(0.8);
    expect(screen.getByLabelText("PBR 상한값")).toHaveAttribute("type", "number");
    expect(screen.getByLabelText("PBR 상한값")).toHaveValue(1.2);
    expect(within(pbrStepDialog).getAllByText("예: 0.8, 1, 1.2")).toHaveLength(2);
    expect(screen.getByLabelText("PBR step 값")).not.toHaveAttribute("type", "range");
    expect(within(screen.getByLabelText("PBR step 값")).getAllByRole("button")).toHaveLength(3);
    expect(within(screen.getByLabelText("PBR step 값")).getByRole("button", { name: "0.1" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("PBR step 값")).getByRole("button", { name: "0.25" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByLabelText("PBR step 값")).getByRole("button", { name: "0.5" })).toBeInTheDocument();
    expect(screen.getByLabelText("PBR 하한값")).toHaveDisplayValue("0.8");
    expect(screen.getByLabelText("PBR 상한값")).toHaveDisplayValue("1.2");
    expect(within(pbrStepDialog).getAllByText("0.25").length).toBeGreaterThanOrEqual(2);
    expect(within(pbrStepDialog).queryByText(/Optuna/)).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("PBR 상한값"));
    expect(screen.getByLabelText("PBR 상한값")).toHaveDisplayValue("");
    await user.type(screen.getByLabelText("PBR 상한값"), "10");
    expect(screen.getByLabelText("PBR 상한값")).toHaveDisplayValue("10");
    fireEvent.change(screen.getByLabelText("PBR 하한값"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("PBR 상한값"), { target: { value: "1" } });
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(screen.getByText("하한값은 상한값보다 클 수 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "PBR 값 설정" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("PBR 하한값"), { target: { value: "0.9" } });
    fireEvent.change(screen.getByLabelText("PBR 상한값"), { target: { value: "1.5" } });
    expect(within(pbrStepDialog).getAllByText("0.25").length).toBeGreaterThanOrEqual(2);
    await user.click(within(screen.getByLabelText("PBR step 값")).getByRole("button", { name: "0.5" }));
    expect(within(pbrStepDialog).getAllByText("0.5").length).toBeGreaterThanOrEqual(2);
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(screen.queryByRole("dialog", { name: "PBR 값 설정" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PBR" })).toHaveTextContent("PBR");
    expect(screen.getByRole("button", { name: "PBR" })).not.toHaveTextContent("0.5");
    expect(screen.getByRole("button", { name: "PBR" })).not.toHaveTextContent(/step/i);
    await user.click(screen.getByRole("button", { name: "손절라인" }));
    const stopLossStepDialog = screen.getByRole("dialog", { name: "손절라인 값 설정" });
    expect(screen.getByLabelText("손절라인 하한값")).toHaveAttribute("type", "number");
    expect(screen.getByLabelText("손절라인 상한값")).toHaveAttribute("type", "number");
    expect(within(stopLossStepDialog).getAllByText("%p")).toHaveLength(2);
    expect(within(screen.getByLabelText("손절라인 step 값")).getAllByRole("button")).toHaveLength(3);
    expect(within(screen.getByLabelText("손절라인 step 값")).getByRole("button", { name: "1%p" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("손절라인 step 값")).getByRole("button", { name: "2.5%p" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByLabelText("손절라인 step 값")).getByRole("button", { name: "5%p" })).toBeInTheDocument();
    await user.click(within(stopLossStepDialog).getByRole("button", { name: "닫기" }));
    await user.click(screen.getByRole("button", { name: "익절라인" }));
    const takeProfitStepDialog = screen.getByRole("dialog", { name: "익절라인 값 설정" });
    expect(within(screen.getByLabelText("익절라인 step 값")).getAllByRole("button")).toHaveLength(3);
    expect(within(screen.getByLabelText("익절라인 step 값")).getByRole("button", { name: "2.5%p" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("익절라인 step 값")).getByRole("button", { name: "5%p" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByLabelText("익절라인 step 값")).getByRole("button", { name: "10%p" })).toBeInTheDocument();
    await user.click(within(takeProfitStepDialog).getByRole("button", { name: "닫기" }));

    await user.click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));

    await waitFor(() => {
      expect(onRun).toHaveBeenCalledWith(
        {
          n_splits: 5,
          train_pct: 0.75,
          anchor: false,
          target_metric: "cagr",
          n_trials: 30,
          method: "bayesian",
          is_bars: 84,
          oos_bars: 28,
          // 디스크립터 모드: 설정 키는 라벨이 아니라 실제 탐색 경로(path)
          parameter_steps: {
            "entry.conditions.0.params.value": 0.5,
            "risk.stop_loss_pct": 2.5,
            "risk.take_profit_pct": 5,
          },
          parameter_ranges: {
            "entry.conditions.0.params.value": {
              min: 0.9,
              max: 1.5,
              step: 0.5,
            },
          },
        },
        expect.any(AbortSignal),
        expect.any(Function)
      );
    });
    expect(screen.queryByText(/Optuna/)).not.toBeInTheDocument();
  });

  it("첫 창 도중 시도(trial) 진행률을 진행 바와 라벨에 반영한다", async () => {
    // 회귀: 창 내부 최적화가 수 분간 침묵할 때 진행 바가 0%로 멈춰 보이던 문제.
    // 창당 한 번이 아니라 시도마다 진행률을 받아 바가 창 안에서도 전진해야 한다.
    let progressFn: ((event: any) => void) | undefined;
    const onRun = vi.fn().mockImplementation((_settings, _signal, onProgress) => {
      progressFn = onProgress;
      return new Promise(() => {}); // 실행 유지 → 모달이 열린 채로 남는다
    });

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={onRun}
          backtestDates={buildDates(240)}
          baseStrategy={baseStrategy}
          optimizationTargets={[{ id: "summary-0", label: "PBR" }]}
        />
      );
    });

    await userEvent.setup().click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));
    await waitFor(() => expect(progressFn).toBeDefined());

    act(() => {
      progressFn!({
        stage: "window",
        window: 1,
        total: 5,
        is_period: "2024-01-03 ~ 2024-09-05",
        oos_period: "2024-09-06 ~ 2025-01-10",
        trial: 15,
        trial_total: 30,
        timing: { phase1: 11.95, simulator: 0.26, format: 0.39, total: 12.6, symbols: 976 },
      });
    });

    // (창 0 완료 + 15/30 시도) / 5 창 = 10% — 더 이상 0%가 아니다.
    await waitFor(() => {
      expect(screen.getByText("1/5 구간 · 15/30 시도")).toBeInTheDocument();
    });
    expect(screen.getByRole("progressbar", { name: "워크포워드 분석" })).toHaveAttribute(
      "aria-valuenow",
      "10"
    );
    // 최근 백테스트 단계별 소요 시간이 모달에 표시된다.
    expect(screen.getByText("최근 백테스트")).toBeInTheDocument();
    expect(screen.getByText("11.95s (976종목)")).toBeInTheDocument();
    expect(screen.getByText("12.60s")).toBeInTheDocument();
    // 각 단계 옆 도움말(?) 아이콘과 툴팁 설명.
    expect(screen.getByLabelText("Phase1 도움말")).toBeInTheDocument();
    expect(screen.getByLabelText("Simulator 도움말")).toBeInTheDocument();
    expect(screen.getByLabelText("Format 도움말")).toBeInTheDocument();
    expect(screen.getByText(/어떤 날 사고 팔지 후보를 계산하는 단계/)).toBeInTheDocument();
    expect(screen.getByText(/계산된 신호대로 실제로 사고팔았다고 돌려보는 단계/)).toBeInTheDocument();
    expect(screen.getByText(/돌린 결과를 CAGR·MDD 같은 숫자로 정리하는 단계/)).toBeInTheDocument();
  });

  it("그리드 탐색 선택 시 예상 조합 수를 보여주고 실행 버튼을 활성화한다", async () => {
    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={vi.fn()}
          backtestDates={buildDates(240)}
          baseStrategy={baseStrategy}
          optimizationTargets={[
            { id: "summary-0", label: "PBR" },
            { id: "summary-1", label: "손절라인" },
          ]}
        />
      );
    });

    await userEvent.setup().click(
      screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })
    );

    expect(screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })).toHaveClass("bg-white/[0.03]");
    expect(screen.queryByText("베이지안 최적화 시도 횟수")).not.toBeInTheDocument();
    expect(screen.getByText("그리드 탐색 예상")).toBeInTheDocument();
    expect(screen.getByText(/조합을 확인할 수 있습니다/)).toBeInTheDocument();
    expect(screen.getByText("실행 가능")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "워크포워드 분석 시작" })).toHaveClass("rounded-md");
    expect(screen.getByRole("button", { name: "워크포워드 분석 시작" })).not.toBeDisabled();
  });

  it("그리드 탐색 실행 시 onRun에 method: grid를 전달한다", async () => {
    const onRun = vi.fn().mockResolvedValue({
      status: "ok",
      n_splits: 5,
      anchor: false,
      target_metric: "cagr",
      windows: [],
      aggregate: {},
      combined_equity: [],
      combined_dates: [],
      walk_forward_efficiency: 0,
    });

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={onRun}
          backtestDates={buildDates(240)}
          baseStrategy={baseStrategy}
          optimizationTargets={[]}
        />
      );
    });

    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })
    );
    await user.click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));

    await waitFor(() => {
      expect(onRun).toHaveBeenCalledWith(
        expect.objectContaining({ method: "grid" }),
        expect.any(AbortSignal),
        expect.any(Function)
      );
    });
  });

  it("확장 모드에서는 전체 백테스트 기간 대비 학습 비율을 사용한다", async () => {
    const onRun = vi.fn().mockResolvedValue({
      status: "ok",
      n_splits: 3,
      anchor: true,
      target_metric: "cagr",
      windows: [],
      aggregate: {},
      combined_equity: [],
      combined_dates: [],
      walk_forward_efficiency: 0,
    });

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={onRun}
          backtestDates={buildDates(240)}
        />
      );
    });

    act(() => {
      fireEvent.change(screen.getByLabelText("학습기간"), { target: { value: "120" } });
      fireEvent.change(screen.getByLabelText("검증기간"), { target: { value: "40" } });
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "확장" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));

    await waitFor(() => {
      expect(onRun).toHaveBeenCalledWith(
        {
          n_splits: 3,
          train_pct: 0.5,
          anchor: true,
          target_metric: "cagr",
          n_trials: 30,
          method: "bayesian",
          is_bars: 120,
          oos_bars: 40,
        },
        expect.any(AbortSignal),
        expect.any(Function)
      );
    });
  });

  it("구간별 최적 파라미터를 변수명이 아니라 한글 라벨로 보여준다", async () => {
    const strategyWithMaCrossover = {
      entry: {
        conditions: [
          { id: "ma_crossover", type: "indicator", params: { shortMA: 5, longMA: 20 } },
        ],
      },
      risk: {
        stop_loss_pct: 10,
        max_holding_days: 20,
        max_positions: 8,
      },
    };

    const onRun = vi.fn().mockResolvedValue({
      status: "ok",
      n_splits: 1,
      anchor: false,
      target_metric: "cagr",
      windows: [
        {
          window: 1,
          is_period: "2024-01-01 ~ 2024-06-30",
          oos_period: "2024-07-01 ~ 2024-09-30",
          best_params: {
            "risk.stop_loss_pct": 6.8,
            "risk.max_holding_days": 10,
            "risk.max_positions": 4,
            "entry.conditions.0.params.shortMA": 7,
            "entry.conditions.0.params.longMA": 23,
          },
          is_metrics: { cagr: 10 },
          oos_metrics: { cagr: 5, maxDrawdown: -8, winRate: 0.5 },
          oos_equity: [],
          oos_dates: [],
        },
      ],
      aggregate: {},
      combined_equity: [],
      combined_dates: [],
      walk_forward_efficiency: 0.5,
    });

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={onRun}
          backtestDates={buildDates(240)}
          baseStrategy={strategyWithMaCrossover}
        />
      );
    });

    await userEvent.setup().click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));

    await waitFor(() => {
      expect(screen.getByText("구간별 최적 파라미터")).toBeInTheDocument();
    });

    expect(screen.getByText("손절라인")).toBeInTheDocument();
    expect(screen.getByText("보유기간")).toBeInTheDocument();
    expect(screen.getByText("보유종목수")).toBeInTheDocument();
    expect(screen.getByText("이동평균 단기")).toBeInTheDocument();
    expect(screen.getByText("이동평균 장기")).toBeInTheDocument();

    expect(screen.queryByText("STOP_LOSS_PCT")).not.toBeInTheDocument();
    expect(screen.queryByText("MAX_HOLDING_DAYS")).not.toBeInTheDocument();
    expect(screen.queryByText("MAX_POSITIONS")).not.toBeInTheDocument();
    expect(screen.queryByText("SHORTMA")).not.toBeInTheDocument();
    expect(screen.queryByText("LONGMA")).not.toBeInTheDocument();
  });

  it("이동평균 파라미터는 5/10/20/60/120일선 중에서만 선택하고 step 입력을 없앤다", async () => {
    const strategyWithMaCrossover = {
      entry: {
        conditions: [
          { id: "ma_crossover", type: "indicator", params: { shortMA: 5, longMA: 20 } },
        ],
      },
      risk: {},
    };

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={vi.fn()}
          backtestDates={buildDates(240)}
          baseStrategy={strategyWithMaCrossover}
        />
      );
    });

    // 파라미터 선택 칩 자체가 기본 선택값(전체 5개)을 보여준다 (표시=실행).
    expect(screen.getByTestId("walk-forward-target-range-이동평균 장기")).toHaveTextContent(
      "5일선, 10일선, 20일선, 60일선, 120일선"
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "이동평균 장기" }));

    expect(screen.getByText("이동평균 장기 값 설정")).toBeInTheDocument();
    expect(screen.getByText("탐색할 일선 선택")).toBeInTheDocument();

    // 기본값은 5개 모두 선택된 상태다.
    for (const label of ["5일선", "10일선", "20일선", "60일선", "120일선"]) {
      expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true");
    }
    expect(screen.getByText("선택된 이동평균: 5일선, 10일선, 20일선, 60일선, 120일선")).toBeInTheDocument();

    // 자유 입력 min/max/step UI는 렌더링되지 않는다 — 오직 고정 5개 값 중 선택만 허용한다.
    expect(screen.queryByLabelText("이동평균 장기 하한값")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("이동평균 장기 상한값")).not.toBeInTheDocument();
    expect(screen.queryByText("step 값")).not.toBeInTheDocument();

    // 5일선/10일선을 해제하면 라벨과 배지 선택 상태가 즉시 갱신된다.
    await user.click(screen.getByRole("button", { name: "5일선" }));
    await user.click(screen.getByRole("button", { name: "10일선" }));
    expect(screen.getByRole("button", { name: "5일선" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("선택된 이동평균: 20일선, 60일선, 120일선")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "저장" }));

    // 저장 후 파라미터 칩도 선택된 값만 보여준다.
    expect(screen.getByTestId("walk-forward-target-range-이동평균 장기")).toHaveTextContent(
      "20일선, 60일선, 120일선"
    );
  });

  it("실행 전 기준 백테스트 실측 속도로 예상 소요 시간을 미리 보여준다", async () => {
    // 240일 백테스트, 기본 설정: n_splits=3, 베이지안 30시도 → 총 3×(30+1)=93회.
    // 백테스트 1회 비용은 구간 길이와 거의 무관(고정비 지배)하므로 기준 실측 10s를
    // 그대로 써서 총 930s. 범위(0.7~1.4배) = 11분 ~ 22분.
    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={vi.fn()}
          backtestDates={buildDates(240)}
          baseStrategy={baseStrategy}
          baseBacktestSeconds={10}
          optimizationTargets={[{ id: "summary-0", label: "PBR" }]}
        />
      );
    });

    expect(screen.getAllByText("예상 소요 시간").length).toBeGreaterThan(0);
    expect(screen.getByText("약 11분 ~ 22분 소요될 것으로 예상됩니다.")).toBeInTheDocument();
    expect(screen.getByText("총 93회")).toBeInTheDocument();
    expect(
      screen.getByText(/시간이 오래 걸리는 작업입니다/)
    ).toBeInTheDocument();
  });

  it("실행 중에는 실측 timing으로 남은 시간(라이브 ETA)을 다시 계산해 보여준다", async () => {
    let progressFn: ((event: any) => void) | undefined;
    const onRun = vi.fn().mockImplementation((_settings, _signal, onProgress) => {
      progressFn = onProgress;
      return new Promise(() => {});
    });

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={onRun}
          backtestDates={buildDates(240)}
          baseStrategy={baseStrategy}
          optimizationTargets={[{ id: "summary-0", label: "PBR" }]}
        />
      );
    });

    await userEvent.setup().click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));
    await waitFor(() => expect(progressFn).toBeDefined());

    act(() => {
      progressFn!({
        stage: "window",
        window: 1,
        total: 3,
        trial: 15,
        trial_total: 30,
        timing: { phase1: 12, simulator: 0.3, format: 0.3, total: 12.6, symbols: 900 },
      });
    });

    // 총 93회 · 완료 (1-1)×31+15=15회 · 남은 78회 × 12.6s ≈ 983s → 약 16분.
    await waitFor(() => {
      expect(screen.getByText("예상 남은 시간")).toBeInTheDocument();
    });
    expect(screen.getByText("약 16분")).toBeInTheDocument();
  });

  it("이동평균 값을 전부 해제하고 저장하면 최소 1개 선택 에러를 보여준다", async () => {
    const strategyWithMaCrossover = {
      entry: {
        conditions: [
          { id: "ma_crossover", type: "indicator", params: { shortMA: 5, longMA: 20 } },
        ],
      },
      risk: {},
    };

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={vi.fn()}
          backtestDates={buildDates(240)}
          baseStrategy={strategyWithMaCrossover}
        />
      );
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "이동평균 단기" }));
    for (const label of ["5일선", "10일선", "20일선", "60일선", "120일선"]) {
      await user.click(screen.getByRole("button", { name: label }));
    }
    expect(screen.getByText("선택된 이동평균: 없음")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "저장" }));

    expect(screen.getByText("최소 1개 값을 선택해 주세요.")).toBeInTheDocument();
  });
});
