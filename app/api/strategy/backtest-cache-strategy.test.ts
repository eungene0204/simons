// @ts-nocheck
/**
 * lib/server/backtestCache.ts > saveCachedResult 회귀 테스트
 *
 * 버그: 백테스트를 "실행"만 해도 upsertStrategyForResult가 Strategy 행을
 *      "전략 <8자해시>" 이름으로 생성 → 사용자가 저장하지 않은 전략이
 *      분석/대시보드 목록에 노출됨.
 *
 * 수정: 캐시 자동 생성 행은 isSaved=false로 만들고, 목록은 isSaved=true만 노출.
 *
 * 검증: saveCachedResult가 canonical_strategy_dsl을 가진 결과를 캐싱할 때
 *      strategy.upsert의 create 페이로드에 isSaved: false가 포함되어야 한다.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockStrategyUpsert = vi.fn();
const mockBacktestResultFindFirst = vi.fn();
const mockBacktestResultCreate = vi.fn();
const mockBacktestHistoryFindFirst = vi.fn();
const mockBacktestHistoryCreate = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    strategy: { upsert: (...a) => mockStrategyUpsert(...a) },
    backtestResult: {
      findFirst: (...a) => mockBacktestResultFindFirst(...a),
      create: (...a) => mockBacktestResultCreate(...a),
    },
    backtestHistory: {
      findFirst: (...a) => mockBacktestHistoryFindFirst(...a),
      create: (...a) => mockBacktestHistoryCreate(...a),
    },
  },
}));

const { saveCachedResult } = await import("@/lib/server/backtestCache");

beforeEach(() => {
  vi.clearAllMocks();
  process.env.ADVISOR_VECTOR_UPSERT_ON_BACKTEST = "0";
  mockStrategyUpsert.mockResolvedValue({});
  mockBacktestResultFindFirst.mockResolvedValue(null);
  mockBacktestResultCreate.mockResolvedValue({});
  mockBacktestHistoryFindFirst.mockResolvedValue(null);
  mockBacktestHistoryCreate.mockResolvedValue({});
});

describe("saveCachedResult > 캐시 자동 생성 전략", () => {
  it("백테스트 실행만으로 생성되는 Strategy 행은 isSaved: false 여야 함", async () => {
    const body = {
      canonical_strategy_dsl: { entry: { conditions: [{ id: "rsi" }] } },
      symbols: ["005930"],
      universe_id: "kospi200",
    };
    const result = { totalReturn: 0, cagr: 0, tradesList: [] };

    await saveCachedResult("cache-key-1", body, result);

    expect(mockStrategyUpsert).toHaveBeenCalledOnce();
    const upsertArg = mockStrategyUpsert.mock.calls[0][0];
    expect(upsertArg.create.isSaved).toBe(false);
    // 이름은 "전략 <8자해시>" 자동 패턴
    expect(upsertArg.create.name).toMatch(/^전략 [a-f0-9]{8}$/);
    // update 분기는 isSaved를 건드리지 않아 이미 저장된 전략의 노출 상태를 유지
    expect(upsertArg.update).not.toHaveProperty("isSaved");
  });
});
