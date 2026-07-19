import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RunAllTestsModal from "./RunAllTestsModal";

const fetchMock = vi.fn();
const savedRuns: any[] = [];

vi.stubGlobal("fetch", fetchMock);

function buildFinalCandidate(prompt: string, index: number) {
  const isMomentum = prompt.includes("모멘텀");
  const isFailure = prompt.includes("실패");

  if (isFailure) {
    return {
      id: `candidate-${index}`,
      prompt,
      strategyName: "실패 전략",
      strategyId: null,
      status: "failed",
      errorMessage: "파싱 실패",
      metrics: null,
    };
  }

  return {
    id: `candidate-${index}`,
    prompt,
    strategyName: isMomentum ? "모멘텀 전략" : "가치 전략",
    strategyId: isMomentum ? "hash_momentum" : "hash_value",
    status: isMomentum ? "computed" : "cache_hit",
    errorMessage: null,
    metrics: {
      strategy_id: isMomentum ? "hash_momentum" : "hash_value",
      totalReturn: isMomentum ? 42.5 : 31.4,
      cagr: isMomentum ? 18.2 : 12.7,
      buyAndHoldReturn: isMomentum ? 11.1 : 8.1,
      maxDrawdown: isMomentum ? -9.8 : -7.2,
      winRate: isMomentum ? 58 : 54,
      profitFactor: isMomentum ? 1.7 : 1.3,
      sharpe: isMomentum ? 1.4 : 1.1,
      sortino: isMomentum ? 1.6 : 1.2,
      volatility: isMomentum ? 17.2 : 14.4,
      trades: isMomentum ? 24 : 18,
      equity: isMomentum ? [10000000, 14250000] : [10000000, 13140000],
      dates: ["2024-01-01", "2025-01-01"],
      signals: [],
      fromCache: !isMomentum,
    },
  };
}

function updateRunProgress(run: any) {
  if (run.status === "COMPLETED" || run.status === "CANCELED") {
    return;
  }

  run.pollCount = (run.pollCount ?? 0) + 1;

  if (run.canceled) {
    run.status = "CANCELED";
    run.candidates = run.candidates.map((candidate: any) =>
      candidate.status === "waiting" || candidate.status === "running"
        ? {
            ...candidate,
            status: "skipped",
            errorMessage: "사용자 요청으로 스킵됨",
          }
        : candidate
    );
    run.logs = [...run.logs, "사용자 요청으로 남은 배치 실행을 중단했습니다."];
  } else if (run.pollCount === 1) {
    run.status = "QUEUED";
    run.currentStrategyName = null;
  } else if (run.pollCount === 2) {
    run.status = "RUNNING";
    run.currentStrategyName = "모멘텀 전략";
    run.candidates = run.candidates.map((candidate: any, index: number) =>
      index === 0
        ? { ...candidate, status: "running", strategyName: "모멘텀 전략" }
        : candidate
    );
    run.logs = [...run.logs, "1/3 전략 실행 시작"];
  } else {
    run.status = "COMPLETED";
    run.currentStrategyName = null;
    run.candidates = run.prompts.map((prompt: string, index: number) => buildFinalCandidate(prompt, index));
    run.logs = [...run.logs, "모멘텀 전략 완료 (Computed)", "가치 전략 완료 (Cache Hit)", "실패 전략 실패: 파싱 실패", "배치 실행이 완료되었습니다."];
  }

  const successful = run.candidates
    .filter((candidate: any) => candidate.metrics)
    .sort((left: any, right: any) => Number(right.metrics.cagr ?? 0) - Number(left.metrics.cagr ?? 0));

  run.rankingSnapshot = successful.map((candidate: any, index: number) => ({
    rank: index + 1,
    strategyId: candidate.strategyId ?? "unknown",
    name: candidate.strategyName,
    status: candidate.status,
    cagr: Number(candidate.metrics?.cagr ?? 0),
    totalReturn: Number(candidate.metrics?.totalReturn ?? 0),
    sharpe: Number(candidate.metrics?.sharpe ?? 0),
    maxDrawdown: Number(candidate.metrics?.maxDrawdown ?? 0),
    profitFactor: Number(candidate.metrics?.profitFactor ?? 0),
    trades: Number(candidate.metrics?.trades ?? 0),
  }));
  run.completedCount = run.candidates.filter((candidate: any) => candidate.status === "computed" || candidate.status === "cache_hit").length;
  run.failedCount = run.candidates.filter((candidate: any) => candidate.status === "failed").length;
  run.skippedCount = run.candidates.filter((candidate: any) => candidate.status === "skipped").length;
}

describe("RunAllTestsModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    savedRuns.length = 0;

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = JSON.parse((init?.body as string) ?? "{}");

      if (url === "/api/strategy/batch-runs" && method === "GET") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            runs: savedRuns.map((run) => ({
              runId: run.runId,
              createdAt: run.createdAt,
              totalPrompts: run.totalPrompts,
              completedCount: run.completedCount,
              failedCount: run.failedCount,
              skippedCount: run.skippedCount,
              rankingSnapshot: run.rankingSnapshot,
              status: run.status,
            })),
          }),
        });
      }

      if (url === "/api/strategy/batch-runs" && method === "POST" && Array.isArray(body.prompts)) {
        const runId = `batch_run_${savedRuns.length + 1}`;
        savedRuns.unshift({
          runId,
          createdAt: "2026-04-22T10:00:00.000Z",
          totalPrompts: body.prompts.length,
          completedCount: 0,
          failedCount: 0,
          skippedCount: 0,
          rankingSnapshot: [],
          status: "QUEUED",
          currentStrategyName: null,
          prompts: body.prompts,
          pollCount: 0,
          logs: [`총 ${body.prompts.length}개 프롬프트 실행 대기열 등록`],
          candidates: body.prompts.map((prompt: string, index: number) => ({
            id: `candidate-${index}`,
            prompt,
            strategyName: `전략 ${index + 1}`,
            strategyId: null,
            status: "waiting",
            errorMessage: null,
            metrics: null,
          })),
        });

        return Promise.resolve({
          ok: true,
          json: async () => ({
            ok: true,
            runId,
            status: "queued",
          }),
        });
      }

      if (url === "/api/strategy/batch-runs" && method === "POST" && body.action === "cancel") {
        const run = savedRuns.find((item) => item.runId === body.runId);
        if (run) {
          run.canceled = true;
        }

        return Promise.resolve({
          ok: true,
          json: async () => ({
            ok: true,
            runId: body.runId,
            status: "cancel_requested",
          }),
        });
      }

      if (url.startsWith("/api/strategy/batch-runs?runId=") && method === "GET") {
        const runId = decodeURIComponent(url.split("=")[1] ?? "");
        const run = savedRuns.find((item) => item.runId === runId);
        if (!run) {
          return Promise.resolve({
            ok: false,
            json: async () => ({ error: "BatchRun not found" }),
          });
        }

        updateRunProgress(run);

        return Promise.resolve({
          ok: true,
          json: async () => ({
            runId: run.runId,
            createdAt: run.createdAt,
            totalPrompts: run.totalPrompts,
            completedCount: run.completedCount,
            failedCount: run.failedCount,
            skippedCount: run.skippedCount,
            rankingSnapshot: run.rankingSnapshot,
            logs: run.logs,
            status: run.status,
            currentStrategyName: run.currentStrategyName,
            candidates: run.candidates.map((candidate: any) => ({
              id: candidate.id,
              strategyId: candidate.strategyId,
              prompt: candidate.prompt,
              strategyName: candidate.strategyName,
              status: candidate.status,
              errorMessage: candidate.errorMessage,
              metrics: candidate.metrics,
            })),
          }),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
  });

  it("서버 batch run을 시작하고 폴링 결과를 진행률, 랭킹, 실패 목록에 반영한다", async () => {
    render(<RunAllTestsModal isOpen onClose={vi.fn()} currentPrompt="현재 입력 전략" />);

    expect(screen.getByTestId("run-all-tests-modal-panel")).toHaveClass(
      "h-[calc(100dvh-1rem)]",
      "lg:h-[min(88vh,920px)]"
    );
    expect(screen.getByTestId("run-all-tests-modal-header")).toHaveClass(
      "px-4",
      "py-3",
      "lg:px-5",
      "lg:py-4"
    );
    expect(screen.getByTestId("run-all-tests-modal-content")).toHaveClass("p-3", "lg:p-5");

    fireEvent.click(screen.getByRole("button", { name: "현재 입력 추가" }));
    fireEvent.change(screen.getByRole("textbox"), {
      target: {
        value: "모멘텀 전략 프롬프트\n\n가치 전략 프롬프트\n\n실패 전략 프롬프트",
      },
    });

    fireEvent.click(screen.getByRole("button", { name: "모두 테스트 시작" }));

    await waitFor(() => {
      expect(screen.getByText("100%")).toBeInTheDocument();
    });

    expect(screen.getByText("모멘텀 전략")).toBeInTheDocument();
    expect(screen.getByText("가치 전략")).toBeInTheDocument();
    expect(screen.getByText(/Cache Hit · hash_value/)).toBeInTheDocument();
    expect(screen.getByText("파싱 실패")).toBeInTheDocument();
    expect(screen.getByText("최고 성과")).toBeInTheDocument();
    expect(screen.getByText("배치 실행이 완료되었습니다.")).toBeInTheDocument();
    expect(screen.getByTestId("run-all-tests-leaderboard-scroll")).toHaveClass(
      "overflow-x-auto",
      "lg:overflow-x-visible"
    );
    expect(screen.getByTestId("run-all-tests-leaderboard-grid")).toHaveClass(
      "min-w-[760px]",
      "lg:min-w-0"
    );
    expect(savedRuns).toHaveLength(1);
    expect(savedRuns[0].completedCount).toBe(2);
    expect(savedRuns[0].failedCount).toBe(1);
    expect(savedRuns[0].rankingSnapshot[0].name).toBe("모멘텀 전략");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/strategy/batch-runs",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"prompts\""),
      })
    );
  });

  it("실행 중단 요청을 보내고 서버 취소 상태를 반영한다", async () => {
    render(<RunAllTestsModal isOpen onClose={vi.fn()} />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: {
        value: "모멘텀 전략 프롬프트\n\n가치 전략 프롬프트",
      },
    });

    fireEvent.click(screen.getByRole("button", { name: "모두 테스트 시작" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "중단" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "중단" }));

    await waitFor(() => {
      expect(screen.getAllByText("사용자 요청으로 스킵됨").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/strategy/batch-runs",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"action\":\"cancel\""),
      })
    );
  });

  it("서버에 저장된 실행 이력을 다시 불러올 수 있다", async () => {
    savedRuns.push({
      runId: "batch_run_saved",
      createdAt: "2026-04-21T10:00:00.000Z",
      totalPrompts: 2,
      completedCount: 1,
      failedCount: 1,
      skippedCount: 0,
      rankingSnapshot: [
        {
          rank: 1,
          strategyId: "hash_saved_top",
          name: "저장된 전략",
          status: "cache_hit",
          cagr: 22.1,
          totalReturn: 48.2,
          sharpe: 1.9,
          maxDrawdown: -8.4,
          profitFactor: 1.8,
          trades: 14,
        },
      ],
      status: "COMPLETED",
      currentStrategyName: null,
      pollCount: 99,
      prompts: ["저장된 프롬프트", "실패 프롬프트"],
      logs: ["저장된 배치 실행"],
      candidates: [
        {
          id: "saved-1",
          prompt: "저장된 프롬프트",
          strategyName: "저장된 전략",
          strategyId: "hash_saved_top",
          status: "cache_hit",
          errorMessage: null,
          metrics: {
            strategy_id: "hash_saved_top",
            totalReturn: 48.2,
            cagr: 22.1,
            buyAndHoldReturn: 11.2,
            maxDrawdown: -8.4,
            winRate: 57,
            profitFactor: 1.8,
            sharpe: 1.9,
            sortino: 2.1,
            volatility: 18.3,
            trades: 14,
            equity: [10000000, 14820000],
            dates: ["2025-01-01", "2026-01-01"],
            signals: [],
          },
        },
        {
          id: "saved-2",
          prompt: "실패 프롬프트",
          strategyName: "실패 전략",
          strategyId: null,
          status: "failed",
          errorMessage: "저장된 실패",
          metrics: null,
        },
      ],
    });

    render(<RunAllTestsModal isOpen onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("batch_run_saved")).toBeInTheDocument();
    });

    expect(screen.getByText(/최고 성과: 저장된 전략/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "이력 불러오기" }));

    await waitFor(() => {
      expect(screen.getByText("저장된 전략")).toBeInTheDocument();
    });

    expect(screen.getByText("Cache Hit · hash_saved_top")).toBeInTheDocument();
    expect(screen.getByText("저장된 실패")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/strategy/batch-runs?runId=batch_run_saved");
  });
});
