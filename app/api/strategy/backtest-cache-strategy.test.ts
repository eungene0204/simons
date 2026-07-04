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

  /**
   * 버그: upsertStrategyForResult가 canonical_strategy_dsl(entry_signals, 최상위
   * stop_loss_pct 등 사람이 읽기 좋은 요약)만 저장하고, 같은 body에 형제 필드로
   * 들어있는 실행 가능한 entry.conditions/exit.conditions/risk.* DSL은 버렸다.
   * 그 결과 /backtest/[id]에서 워크포워드를 실행하면 buildWalkForwardParameterRanges가
   * baseStrategy.risk/entry를 찾지 못해 "숫자 파라미터가 없습니다" 오류가 났다.
   */
  it("body의 entry/exit/risk DSL도 canonical 요약과 함께 settings에 보존한다", async () => {
    const body = {
      canonical_strategy_dsl: {
        entry_signals: [{ indicator: "rsi", threshold: 30 }],
        stop_loss_pct: 10,
        take_profit_pct: 20,
      },
      entry: { conditions: [{ id: "rsi_cross", params: { period: 14, threshold: 30 } }] },
      exit: { conditions: [{ id: "rsi_exit", params: { threshold: 70 } }] },
      risk: { stop_loss_pct: 10, take_profit_pct: 20, max_positions: 8 },
      period: "5y",
      universe_id: "kospi200",
    };
    const result = { totalReturn: 0, cagr: 0, tradesList: [] };

    await saveCachedResult("cache-key-2", body, result);

    const upsertArg = mockStrategyUpsert.mock.calls[0][0];
    const savedSettings = JSON.parse(upsertArg.create.settings);

    expect(savedSettings.entry).toEqual(body.entry);
    expect(savedSettings.exit).toEqual(body.exit);
    expect(savedSettings.risk).toEqual(body.risk);
    expect(savedSettings.period).toBe("5y");
    // canonical 요약 필드도 계속 보존(요약 표시용 하위호환)
    expect(savedSettings.entry_signals).toEqual(body.canonical_strategy_dsl.entry_signals);
  });
});
