import { describe, expect, it } from "vitest";
import { buildVectorMemoryUpsertCommand, computeCacheKey } from "@/lib/server/backtestCache";

const baseBody = {
  strategy_id: "strategy_hash_rsi",
  symbols: ["005930", "000660"],
  universe_id: "kospi200",
  period: "3y",
  risk: {
    init_cash: 10000000,
    execution_timing: "next_open",
    liquidity_limit_pct: 10,
  },
  options: {
    fee_rate: 0.0015,
    slippage_rate: 0.0005,
  },
};

describe("backtest cache key", () => {
  it("does not reuse a raw strategy_id as the full backtest cache key", () => {
    expect(computeCacheKey(baseBody)).not.toBe(baseBody.strategy_id);
  });

  it("keeps the same key for equivalent symbol ordering and period casing", () => {
    const left = computeCacheKey(baseBody);
    const right = computeCacheKey({
      ...baseBody,
      symbols: ["000660", "005930"],
      period: "3Y",
    });

    expect(left).toBe(right);
  });

  it("separates identical strategies when initial capital changes", () => {
    const lowCapital = computeCacheKey(baseBody);
    const highCapital = computeCacheKey({
      ...baseBody,
      risk: {
        ...baseBody.risk,
        init_cash: 50000000,
      },
    });

    expect(lowCapital).not.toBe(highCapital);
  });

  it("separates identical strategies when transaction cost assumptions change", () => {
    const lowCost = computeCacheKey(baseBody);
    const highCost = computeCacheKey({
      ...baseBody,
      options: {
        ...baseBody.options,
        fee_rate: 0.003,
      },
    });

    expect(lowCost).not.toBe(highCost);
  });

  it("separates current engine results from legacy cache generations", () => {
    const legacyV2Key = "2e19acbfb06c4644f251b3cc8a0aa036acbed3e3a6d11d6dc7f8da2e5309a168";

    expect(computeCacheKey(baseBody)).not.toBe(legacyV2Key);
  });

  it("separates strategy_id cache keys from versionless cache generations", () => {
    const versionlessStrategyKey = "79c5fbb10ea562e55e5cb535d8120c9027241720d7b7e2b3e609f9854e79f1b6";

    expect(computeCacheKey(baseBody)).not.toBe(versionlessStrategyKey);
  });
});

describe("backtest vector memory upsert", () => {
  it("builds a Python command that migrates stored backtests into ChromaDB", () => {
    const command = buildVectorMemoryUpsertCommand("/repo/root");

    expect(command.command).toBe(process.env.PYTHON_BIN || process.env.PYTHON || "python3");
    expect(command.args).toHaveLength(2);
    expect(command.args[0]).toBe("-c");
    expect(command.args[1]).toContain("migrate_backtest_results_to_chroma");
    expect(command.args[1]).toContain("from vector_memory import migrate_backtest_results_to_chroma");
    expect(command.args[1]).toContain("persist_path=chroma_path()");
    expect(command.args[1]).not.toContain("advisor.vector_memory");
    expect(command.options.cwd).toBe("/repo/root");
    expect(command.options.stdio).toBe("ignore");
  });
});
