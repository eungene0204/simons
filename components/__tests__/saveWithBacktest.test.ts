// @ts-nocheck
/**
 * app/api/strategy/save-with-backtest/route.ts 회귀 테스트
 *
 * 수정 내용:
 * - Strategy.id에 @default(cuid()) 없음 → Prisma create 호출 시 deterministic id 필요
 * - Strategy.updatedAt에 @updatedAt 누락 → create 시 updatedAt 필드 오류
 * - 위 두 문제로 "저장에 실패했습니다." 응답이 발생했음
 *
 * 검증 항목:
 * 1. name/dsl 없을 때 400 반환
 * 2. Prisma create 호출 시 Strategy.id를 deterministic hash로 명시하고 updatedAt은 스키마에 의존
 * 3. backtestResult 포함/미포함 모두 처리
 * 4. 성공 시 strategyId, backtestResultId, message 포함 응답
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ── Prisma mock ─────────────────────────────────────────────────────────────
const mockStrategyCreate = vi.fn();
const mockBacktestResultCreate = vi.fn();
const mockTransaction = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    $transaction: mockTransaction,
  },
}));

// ── route 핸들러 import (mock 이후) ─────────────────────────────────────────
const { POST } = await import("@/app/api/strategy/save-with-backtest/route");

// ── 헬퍼: NextRequest 유사 객체 생성 ──────────────────────────────────────
function makeRequest(body: object): Request {
  return new Request("http://localhost/api/strategy/save-with-backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── 픽스처 ──────────────────────────────────────────────────────────────────
const MOCK_STRATEGY = {
  id: "clxxxxxxxxxxxxxx",
  name: "AI 전략",
  description: null,
  settings: "{}",
  createdAt: new Date(),
  updatedAt: new Date(),
};

const MOCK_BACKTEST_RECORD = {
  id: "clyyyyyyyyyyyyyy",
  strategyId: MOCK_STRATEGY.id,
  summary: "{}",
  trades: "[]",
  createdAt: new Date(),
};

const VALID_DSL = {
  universe: ["KOSDAQ"],
  entry_signals: [{ indicator: "ai_model" }],
  exit_signals: [{ indicator: "ai_drop_model" }],
  max_positions: 15,
  stop_loss_pct: 10,
};

const VALID_BACKTEST_RESULT = {
  totalReturn: 25.3,
  cagr: 12.1,
  maxDrawdown: -8.5,
  winRate: 0.62,
  profitFactor: 1.8,
  sharpe: 1.4,
  trades: 120,
  equity: [10000000, 10500000, 11000000],
  dates: ["2023-01-01", "2023-06-01", "2024-01-01"],
  tradesList: [{ symbol: "005930", pnl: 50000 }],
  perAssetStats: {
    A: { symbol: "A", totalReturn: 1, trades: 2, profit: 10, winRate: 50 },
    B: { symbol: "B", totalReturn: 5, trades: 3, profit: 50, winRate: 60 },
    C: { symbol: "C", totalReturn: 3, trades: 4, profit: 30, winRate: 55 },
    D: { symbol: "D", totalReturn: 8, trades: 1, profit: 80, winRate: 100 },
    E: { symbol: "E", totalReturn: 2, trades: 2, profit: 20, winRate: 50 },
    F: { symbol: "F", totalReturn: 9, trades: 5, profit: 90, winRate: 80 },
    G: { symbol: "G", totalReturn: 7, trades: 2, profit: 70, winRate: 75 },
    H: { symbol: "H", totalReturn: 4, trades: 3, profit: 40, winRate: 66 },
    I: { symbol: "I", totalReturn: 6, trades: 1, profit: 60, winRate: 100 },
    J: { symbol: "J", totalReturn: 10, trades: 6, profit: 100, winRate: 83 },
    K: { symbol: "K", totalReturn: 0.5, trades: 1, profit: 5, winRate: 50 },
  },
};

// ── 테스트 ──────────────────────────────────────────────────────────────────

describe("POST /api/strategy/save-with-backtest", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockTransaction.mockImplementation(async (fn) => {
      const tx = {
        strategy: { create: mockStrategyCreate },
        backtestResult: { create: mockBacktestResultCreate },
      };
      mockStrategyCreate.mockResolvedValue(MOCK_STRATEGY);
      mockBacktestResultCreate.mockResolvedValue(MOCK_BACKTEST_RECORD);
      return fn(tx);
    });
  });

  // ── 유효성 검사 ────────────────────────────────────────────────────────────

  it("name이 없으면 400 반환", async () => {
    const res = await POST(makeRequest({ dsl: VALID_DSL }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/이름/);
  });

  it("name이 공백만 있으면 400 반환", async () => {
    const res = await POST(makeRequest({ name: "   ", dsl: VALID_DSL }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/이름/);
  });

  it("dsl이 없으면 400 반환", async () => {
    const res = await POST(makeRequest({ name: "AI 전략" }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/설정/);
  });

  // ── 핵심 회귀: id/updatedAt 자동 생성 ────────────────────────────────────

  it("strategy.create 호출 시 deterministic id를 명시적으로 전달해야 함", async () => {
    await POST(makeRequest({ name: "AI 전략", dsl: VALID_DSL }));

    expect(mockStrategyCreate).toHaveBeenCalledOnce();
    const createArg = mockStrategyCreate.mock.calls[0][0];
    expect(createArg.data.id).toMatch(/^[a-f0-9]{64}$/);
  });

  it("strategy.create 호출 시 updatedAt을 명시적으로 전달하지 않아야 함 (스키마 @updatedAt 의존)", async () => {
    await POST(makeRequest({ name: "AI 전략", dsl: VALID_DSL }));

    const createArg = mockStrategyCreate.mock.calls[0][0];
    // updatedAt 필드가 없어야 함 — 있으면 @updatedAt이 필요 없음
    expect(createArg.data).not.toHaveProperty("updatedAt");
  });

  it("backtestResult.create 호출 시 id를 명시적으로 전달하지 않아야 함 (@default(cuid()) 의존)", async () => {
    await POST(
      makeRequest({ name: "AI 전략", dsl: VALID_DSL, backtestResult: VALID_BACKTEST_RESULT })
    );

    expect(mockBacktestResultCreate).toHaveBeenCalledOnce();
    const createArg = mockBacktestResultCreate.mock.calls[0][0];
    expect(createArg.data).not.toHaveProperty("id");
  });

  // ── 성공 케이스 ────────────────────────────────────────────────────────────

  it("backtestResult 없이도 전략만 저장 성공", async () => {
    const res = await POST(makeRequest({ name: "AI 전략", dsl: VALID_DSL }));
    expect(res.status).toBe(200);

    const body = await res.json();
    expect(body.strategyId).toBe(MOCK_STRATEGY.id);
    expect(body.backtestResultId).toBeNull();
    expect(body.message).toBeTruthy();

    // backtestResult.create는 호출되지 않아야 함
    expect(mockBacktestResultCreate).not.toHaveBeenCalled();
  });

  it("backtestResult 포함 시 strategy + backtestResult 함께 저장", async () => {
    const res = await POST(
      makeRequest({ name: "AI 전략", dsl: VALID_DSL, backtestResult: VALID_BACKTEST_RESULT })
    );
    expect(res.status).toBe(200);

    const body = await res.json();
    expect(body.strategyId).toBe(MOCK_STRATEGY.id);
    expect(body.backtestResultId).toBe(MOCK_BACKTEST_RECORD.id);
    expect(body.message).toBeTruthy();

    expect(mockStrategyCreate).toHaveBeenCalledOnce();
    expect(mockBacktestResultCreate).toHaveBeenCalledOnce();
  });

  it("strategy.create의 settings에 DSL이 JSON으로 직렬화됨", async () => {
    await POST(makeRequest({ name: "AI 전략", dsl: VALID_DSL }));

    const createArg = mockStrategyCreate.mock.calls[0][0];
    const parsed = JSON.parse(createArg.data.settings);
    expect(parsed.universe).toEqual(["KOSDAQ"]);
    expect(parsed.max_positions).toBe(15);
    expect(parsed.name).toBe("AI 전략"); // dslToSave에 name이 반영되어야 함
  });

  it("backtestResult의 tradesList가 trades 필드에 JSON으로 저장됨", async () => {
    await POST(
      makeRequest({ name: "AI 전략", dsl: VALID_DSL, backtestResult: VALID_BACKTEST_RESULT })
    );

    const createArg = mockBacktestResultCreate.mock.calls[0][0];
    const trades = JSON.parse(createArg.data.trades);
    expect(trades).toEqual(VALID_BACKTEST_RESULT.tradesList);
  });

  it("equity, dates 배열이 summary에 포함됨", async () => {
    await POST(
      makeRequest({ name: "AI 전략", dsl: VALID_DSL, backtestResult: VALID_BACKTEST_RESULT })
    );

    const createArg = mockBacktestResultCreate.mock.calls[0][0];
    const summary = JSON.parse(createArg.data.summary);
    expect(summary.equity).toEqual(VALID_BACKTEST_RESULT.equity);
    expect(summary.dates).toEqual(VALID_BACKTEST_RESULT.dates);
    expect(summary.totalReturn).toBe(VALID_BACKTEST_RESULT.totalReturn);
  });

  it("AI 리포트 상세 항목도 summary에 함께 저장됨", async () => {
    await POST(
      makeRequest({
        name: "AI 전략",
        dsl: VALID_DSL,
        backtestResult: VALID_BACKTEST_RESULT,
        aiSummary: "리포트 요약",
        aiScore: 87,
        aiStrengths: ["강점 1", "강점 2"],
        aiRisks: ["리스크 1"],
      })
    );

    const createArg = mockBacktestResultCreate.mock.calls[0][0];
    const summary = JSON.parse(createArg.data.summary);
    expect(summary.aiSummary).toBe("리포트 요약");
    expect(summary.aiScore).toBe(87);
    expect(summary.aiStrengths).toEqual(["강점 1", "강점 2"]);
    expect(summary.aiRisks).toEqual(["리스크 1"]);
  });

  it("summary에 수익률 상위 10개 종목과 해당 스탯이 저장됨", async () => {
    await POST(
      makeRequest({ name: "AI 전략", dsl: VALID_DSL, backtestResult: VALID_BACKTEST_RESULT })
    );

    const createArg = mockBacktestResultCreate.mock.calls[0][0];
    const summary = JSON.parse(createArg.data.summary);
    expect(summary.topSymbols).toEqual(["J", "F", "D", "G", "I", "B", "H", "C", "E", "A"]);
    expect(summary.topAssetStats).toHaveLength(10);
    expect(summary.topAssetStats[0]).toMatchObject({ symbol: "J", totalReturn: 10, trades: 6 });
  });

  // ── Prisma 오류 처리 ────────────────────────────────────────────────────────

  it("Prisma 오류 발생 시 500 반환", async () => {
    mockTransaction.mockRejectedValue(new Error("DB connection failed"));

    const res = await POST(makeRequest({ name: "AI 전략", dsl: VALID_DSL }));
    expect(res.status).toBe(500);

    const body = await res.json();
    expect(body.error).toBe("저장에 실패했습니다.");
  });
});
