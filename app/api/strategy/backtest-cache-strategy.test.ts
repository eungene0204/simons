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
const mockBacktestHistoryUpdate = vi.fn();

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
      update: (...a) => mockBacktestHistoryUpdate(...a),
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
  mockBacktestHistoryUpdate.mockResolvedValue({});
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

    const historyArg = mockBacktestHistoryCreate.mock.calls[0][0];
    expect(historyArg.data.strategyId).toBe(upsertArg.create.id);
  });

  it("화면 자동 저장 행이 먼저 생겨도 DSL Strategy와 strategyId를 연결한다", async () => {
    mockBacktestHistoryFindFirst.mockResolvedValueOnce({ id: "history-1" });
    const body = {
      strategy_id: "strategy-value-1",
      canonical_strategy_dsl: {
        fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
      },
      entry: {
        conditions: [
          { type: "filter", id: "pbr", params: { operator: "<=", value: 1 } },
        ],
      },
      risk: { stop_loss_pct: 12, max_positions: 8 },
      universe_id: "kospi",
    };

    await saveCachedResult("cache-key-existing", body, { totalReturn: 0, tradesList: [] });

    const upsertArg = mockStrategyUpsert.mock.calls[0][0];
    expect(JSON.parse(upsertArg.create.settings)).toMatchObject({
      entry: body.entry,
      risk: body.risk,
    });
    expect(mockBacktestHistoryCreate).not.toHaveBeenCalled();
    expect(mockBacktestHistoryUpdate).toHaveBeenCalledWith({
      where: { id: "history-1" },
      data: expect.objectContaining({
        strategyId: "strategy-value-1",
        cacheKey: "cache-key-existing",
      }),
    });
  });

  /**
   * 버그: 스트리밍 실행에서 클라이언트는 result 이벤트를 받은 즉시 자동 저장 POST를 보내는데,
   *      saveCachedResult는 스트림 종료 후에 실행된다. 자동 저장이 먼저 도착해 사용자 이름과
   *      isVisible=true로 행을 만들면, 뒤늦게 실행된 saveCachedResult가 그 행을
   *      "전략 <8자해시>" 자리표시자 이름과 isVisible=false로 덮어써서
   *      기록 카드에 해시 이름이 보였다.
   */
  it("자동 저장이 먼저 만든 행의 실제 이름과 노출 상태를 덮어쓰지 않는다", async () => {
    mockBacktestHistoryFindFirst.mockResolvedValueOnce({
      id: "history-race",
      strategyName: "코스피200 RSI 30 이하 매수",
      isVisible: true,
    });

    await saveCachedResult(
      "cache-key-race",
      { strategy_id: "strategy-race", canonical_strategy_dsl: { universe: "KOSPI200" } },
      { totalReturn: 0, tradesList: [] }
    );

    const updateArg = mockBacktestHistoryUpdate.mock.calls[0][0];
    expect(updateArg.data.strategyName).toBe("코스피200 RSI 30 이하 매수");
    expect(updateArg.data.isVisible).toBe(true);
  });

  it("기존 행 이름이 해시 자리표시자면 갱신 대상이다", async () => {
    mockBacktestHistoryFindFirst.mockResolvedValueOnce({
      id: "history-placeholder",
      strategyName: "전략 50e25330",
      isVisible: false,
    });

    await saveCachedResult(
      "cache-key-placeholder",
      {
        strategy_id: "strategy-placeholder",
        strategy_name: "저장한 이름",
        canonical_strategy_dsl: { universe: "KOSPI200" },
      },
      { totalReturn: 0, tradesList: [] }
    );

    const updateArg = mockBacktestHistoryUpdate.mock.calls[0][0];
    expect(updateArg.data.strategyName).toBe("저장한 이름");
    expect(updateArg.data.isVisible).toBe(false);
  });

  it("스트림 저장 경로에서는 DSL 영속화 실패를 호출자에게 전달한다", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    mockStrategyUpsert.mockRejectedValueOnce(new Error("DB write failed"));

    try {
      await expect(
        saveCachedResult(
          "cache-key-failed",
          {
            strategy_id: "strategy-failed",
            canonical_strategy_dsl: { universe: "KOSPI" },
          },
          { totalReturn: 0, tradesList: [] },
          { throwOnFailure: true }
        )
      ).rejects.toThrow("DB write failed");
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });
});
