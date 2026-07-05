import { createHash } from "crypto";
import { spawn } from "child_process";
import { prisma } from "@/lib/prisma";

function pruneUndefined(val: any): any {
  if (Array.isArray(val)) return val.map(pruneUndefined);
  if (val !== null && typeof val === "object") {
    return Object.fromEntries(
      Object.entries(val)
        .filter(([, value]) => value !== undefined)
        .map(([key, value]) => [key, pruneUndefined(value)])
    );
  }
  return val;
}

function sortDeep(val: any): any {
  if (Array.isArray(val)) return val.map(sortDeep);
  if (val !== null && typeof val === "object") {
    return Object.fromEntries(
      Object.keys(val)
        .sort()
        .map((key) => [key, sortDeep(val[key])])
    );
  }
  return val;
}

function sha256(input: string): string {
  return createHash("sha256").update(input).digest("hex");
}

function stableStringify(value: any): string {
  return JSON.stringify(sortDeep(pruneUndefined(value)));
}

let vectorMemoryUpsertChain: Promise<void> = Promise.resolve();
const BACKTEST_CACHE_VERSION = 4;

export function buildVectorMemoryUpsertCommand(cwd = process.cwd()) {
  const python = process.env.PYTHON_BIN || process.env.PYTHON || "python3";
  const script = [
    "import asyncio, os, sqlite3, sys",
    "from pathlib import Path",
    "sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))",
    "from vector_memory import migrate_backtest_results_to_chroma",
    "def db_path():",
    "    project_root = os.getcwd()",
    "    db_url = os.getenv('DATABASE_URL', '')",
    "    if db_url.startswith('file:'):",
    "        rel = db_url.replace('file:', '', 1)",
    "        for candidate in (os.path.join(project_root, 'prisma', rel), os.path.join(project_root, rel.lstrip('./'))):",
    "            if os.path.exists(candidate):",
    "                return candidate",
    "    return os.path.join(project_root, 'prisma', 'prisma', 'dev.db')",
    "def chroma_path():",
    "    configured = os.getenv('ADVISOR_CHROMA_PATH')",
    "    return Path(configured) if configured else Path(os.getcwd()) / 'backend' / 'advisor' / '.chroma'",
    "async def main():",
    "    conn = sqlite3.connect(db_path(), check_same_thread=False, timeout=5.0)",
    "    conn.row_factory = sqlite3.Row",
    "    try:",
    "        await migrate_backtest_results_to_chroma(conn, persist_path=chroma_path())",
    "    finally:",
    "        conn.close()",
    "asyncio.run(main())",
  ].join("\n");

  return {
    command: python,
    args: ["-c", script],
    options: {
      cwd,
      env: process.env,
      stdio: "ignore" as const,
    },
  };
}

function spawnVectorMemoryBacktestUpsert(): Promise<void> {
  return new Promise((resolve, reject) => {
    const { command, args, options } = buildVectorMemoryUpsertCommand();
    const child = spawn(command, args, options);

    child.on("error", reject);
    child.on("close", (code) => {
      if (code && code !== 0) {
        reject(new Error(`ChromaDB upsert exited with code ${code}`));
        return;
      }
      resolve();
    });
    child.unref();
  });
}

export async function runVectorMemoryBacktestUpsert(options: { throwOnFailure?: boolean } = {}) {
  if (process.env.ADVISOR_VECTOR_UPSERT_ON_BACKTEST === "0") {
    return;
  }

  const upsert = vectorMemoryUpsertChain
    .catch(() => undefined)
    .then(spawnVectorMemoryBacktestUpsert);
  vectorMemoryUpsertChain = upsert.catch(() => undefined);

  try {
    await upsert;
  } catch (err) {
    console.error("[VectorMemory] ChromaDB upsert failed:", err);
    if (options.throwOnFailure) {
      throw err;
    }
  }
}

export function triggerVectorMemoryBacktestUpsert() {
  void runVectorMemoryBacktestUpsert();
}

function sortedSymbols(value: any): string[] {
  return Array.isArray(value)
    ? value.map((symbol) => String(symbol)).sort()
    : [];
}

function normalizePeriod(value: any): string {
  return String(value ?? "5Y").toUpperCase();
}

function buildBacktestCacheConfig(body: any) {
  const options = body?.options ?? {};
  const risk = body?.risk ?? {};

  return sortDeep(pruneUndefined({
    version: BACKTEST_CACHE_VERSION,
    market: body?.market ?? null,
    universe_id: body?.universe_id ?? body?.universeId ?? body?.universe ?? null,
    universe_snapshot_hash: body?.universe_snapshot_hash ?? body?.universeSnapshotHash ?? null,
    symbols: sortedSymbols(body?.symbols),
    symbol_count: body?.symbol_count ?? null,
    symbols_resolved: body?.symbols_resolved ?? null,
    timeframe: body?.timeframe ?? body?.interval ?? "1d",
    period: normalizePeriod(body?.period ?? body?.backtest_period),
    start_date: body?.start_date ?? body?.startDate ?? options.start_date ?? options.startDate ?? null,
    end_date: body?.end_date ?? body?.endDate ?? options.end_date ?? options.endDate ?? null,
    initial_capital:
      body?.initial_capital ??
      body?.initialCapital ??
      risk.init_cash ??
      risk.initial_capital ??
      risk.initialCapital ??
      options.initial_capital ??
      options.initialCapital ??
      null,
    fee_rate: options.fee_rate ?? body?.fee_rate ?? null,
    slippage_rate: options.slippage_rate ?? body?.slippage_rate ?? null,
    execution_type: options.execution_type ?? risk.execution_timing ?? null,
    liquidity_limit_pct: risk.liquidity_limit_pct ?? null,
    liquidity_policy: body?.liquidity_policy ?? body?.liquidityPolicy ?? null,
    engine_version: body?.engine_version ?? body?.engineVersion ?? null,
  }));
}

export function canonicalizeStrategyDsl(dsl: any): any {
  if (!dsl || typeof dsl !== "object") return {};

  const {
    id: _id,
    name: _name,
    description: _description,
    version: _version,
    created_at: _createdAt,
    updated_at: _updatedAt,
    strategy_id: _strategyId,
    canonical_strategy_dsl: _canonicalDsl,
    ...rest
  } = dsl;

  return sortDeep(pruneUndefined(rest));
}

export function computeStrategyIdFromDsl(dsl: any): string {
  return sha256(stableStringify(canonicalizeStrategyDsl(dsl)));
}

// saveCachedResult가 비가시(isVisible=false) 캐시 행을 만들 때 붙이는 자리표시자 이름인지 판별한다.
// 자동 노출(auto-save) 시 "기존 이름 유지" 로직이 이 자리표시자를 진짜 이름으로 오인해
// 사용자 프롬프트 기반 이름을 덮어쓰지 못하게 막는 문제를 방지하기 위해 쓰인다.
export function isPlaceholderStrategyName(name: string | null | undefined): boolean {
  if (!name) return true;
  return /^전략 [0-9a-f]{8}$/.test(name);
}

export function resolveStrategyId(payload: any): string | null {
  const directId = payload?.strategy_id ?? payload?.strategyId;
  if (typeof directId === "string" && directId.trim()) {
    return directId.trim();
  }

  const canonicalDsl = payload?.canonical_strategy_dsl ?? payload?.canonicalStrategyDsl;
  if (canonicalDsl) {
    const canonical =
      typeof canonicalDsl === "string"
        ? canonicalDsl
        : stableStringify(canonicalDsl);
    return sha256(canonical);
  }

  if (payload?.dsl) {
    return computeStrategyIdFromDsl(payload.dsl);
  }

  return null;
}

export function computeCacheKey(body: any): string {
  const strategyId = resolveStrategyId(body);
  const backtestConfig = buildBacktestCacheConfig(body);

  if (strategyId) {
    return sha256(stableStringify({
      cache_version: BACKTEST_CACHE_VERSION,
      strategy_id: strategyId,
      backtest_config: backtestConfig,
    }));
  }

  const normalized = sortDeep({
    cache_version: BACKTEST_CACHE_VERSION,
    symbols: [...(body.symbols ?? [])].sort(),
    entry: {
      conditions: [...(body.entry?.conditions ?? [])].sort((a: any, b: any) =>
        (a.id ?? "").localeCompare(b.id ?? "")
      ),
    },
    exit: {
      conditions: [...(body.exit?.conditions ?? [])].sort((a: any, b: any) =>
        (a.id ?? "").localeCompare(b.id ?? "")
      ),
    },
    risk: body.risk ?? {},
    backtest_config: backtestConfig,
  });

  return sha256(JSON.stringify(normalized));
}

function buildBacktestMetrics(result: any) {
  return {
    totalReturn: result.totalReturn ?? 0,
    cagr: result.cagr ?? 0,
    mdd: result.maxDrawdown ?? 0,
    winRate: result.winRate ?? 0,
    profitFactor: result.profitFactor ?? 0,
    buyHold: result.buyAndHoldReturn ?? 0,
    trades: result.trades ?? 0,
    executionTime: result.executionTime ?? 0,
    perAssetStats: result.perAssetStats ?? null,
    topSymbols: result.topSymbols ?? null,
  };
}

function buildBacktestSummary(result: any) {
  return {
    totalReturn: result.totalReturn ?? 0,
    cagr: result.cagr ?? 0,
    maxDrawdown: result.maxDrawdown ?? 0,
    profitFactor: result.profitFactor ?? 0,
    sharpe: result.sharpe ?? 0,
    sortino: result.sortino ?? 0,
    kelly: result.kelly ?? 0,
    volatility: result.volatility ?? 0,
    buyAndHoldReturn: result.buyAndHoldReturn ?? 0,
    trades: result.trades ?? 0,
    avgProfit: result.avgProfit ?? 0,
    avgLoss: result.avgLoss ?? 0,
    maxConsecutiveWins: result.maxConsecutiveWins ?? 0,
    maxConsecutiveLosses: result.maxConsecutiveLosses ?? 0,
    initialCapital: result.initialCapital ?? 0,
    finalEquity: result.finalEquity ?? 0,
    symbols: result.symbols ?? [],
    perAssetStats: result.perAssetStats ?? null,
    equity: result.equity ?? [],
    benchmarkEquity: result.benchmark_equity ?? result.benchmarkEquity ?? [],
    dates: result.dates ?? [],
    warnings: result.warnings ?? [],
    executionTime: result.executionTime ?? 0,
    topSymbols: result.topSymbols ?? [],
  };
}

export function resolveHistoryUniverseLabel(body: any, result: any = {}): string {
  const rawUniverse =
    body?.universe_id ??
    body?.universeId ??
    body?.universe ??
    result?.universe_id ??
    result?.universeId ??
    result?.universe;

  const normalize = (value: unknown): string | null => {
    if (Array.isArray(value)) {
      const labels = value.map(normalize).filter(Boolean);
      return labels.length > 0 ? labels.join(", ") : null;
    }

    if (typeof value !== "string") return null;
    const trimmed = value.trim();
    if (!trimmed) return null;

    if (/^\d{6}(?:\s*,\s*\d{6})*$/.test(trimmed)) {
      return "선택 종목";
    }

    const normalized = trimmed.toLowerCase().replace(/[\s_-]/g, "");
    if (normalized === "kospi200") return "KOSPI200";
    if (normalized === "kospi") return "KOSPI";
    if (normalized === "kosdaq") return "KOSDAQ";
    return trimmed;
  };

  return normalize(rawUniverse) ?? (Array.isArray(body?.symbols) && body.symbols.length > 0 ? "선택 종목" : "기타");
}

async function upsertStrategyForResult(strategyId: string, body: any) {
  const canonicalDsl = body?.canonical_strategy_dsl ?? body?.canonicalStrategyDsl;
  if (!canonicalDsl) return;

  const settingsObject =
    typeof canonicalDsl === "string" ? JSON.parse(canonicalDsl) : canonicalDsl;

  // canonical_strategy_dsl은 사람이 읽기 좋은 요약(entry_signals, top-level stop_loss_pct 등)일 뿐,
  // 실제 백테스트를 재실행하거나 워크포워드 파라미터 범위를 뽑아내는 데 필요한
  // entry.conditions/exit.conditions/risk.* 형태의 DSL은 아니다. 그 DSL은 같은
  // body(백엔드 to_backtest_request 응답)에 형제 필드로 함께 들어있으므로 같이 보존한다.
  const settingsPayload = JSON.stringify({
    ...settingsObject,
    ...(body?.entry ? { entry: body.entry } : {}),
    ...(body?.exit ? { exit: body.exit } : {}),
    ...(body?.risk ? { risk: body.risk } : {}),
    ...(body?.period ? { period: body.period } : {}),
    ...(body?.options ? { options: body.options } : {}),
    ...(body?.universe_id ? { universe_id: body.universe_id } : {}),
    ...(body?.startDate ? { startDate: body.startDate } : {}),
    ...(body?.endDate ? { endDate: body.endDate } : {}),
    id: strategyId,
  });

  await prisma.strategy.upsert({
    where: { id: strategyId },
    // update는 isSaved를 건드리지 않아 이미 저장된 전략의 노출 상태를 유지한다
    update: {
      settings: settingsPayload,
    },
    create: {
      id: strategyId,
      name: `전략 ${strategyId.slice(0, 8)}`,
      description: null,
      settings: settingsPayload,
      strategyType: "기타",
      isSaved: false,
    },
  });
}

export async function saveCachedResult(
  cacheKey: string,
  body: any,
  result: any,
  options: { awaitVectorUpsert?: boolean } = {}
) {
  try {
    const strategyId = resolveStrategyId({
      ...body,
      strategy_id: body?.strategy_id ?? result?.strategy_id ?? result?.strategyId,
    }) ?? cacheKey;
    const metrics = buildBacktestMetrics(result);
    const summary = buildBacktestSummary(result);

    await upsertStrategyForResult(strategyId, body);

    const existingBacktestResult = await prisma.backtestResult.findFirst({
      where: { strategyId },
      orderBy: { createdAt: "desc" },
    });

    if (existingBacktestResult) {
      await prisma.backtestResult.update({
        where: { id: existingBacktestResult.id },
        data: {
          summary: JSON.stringify(summary),
          trades: JSON.stringify(result.tradesList ?? []),
        },
      });
    } else {
      await prisma.backtestResult.create({
        data: {
          strategyId,
          summary: JSON.stringify(summary),
          trades: JSON.stringify(result.tradesList ?? []),
        },
      });
    }

    const existingHistory = await prisma.backtestHistory.findFirst({
      where: { cacheKey },
      orderBy: { createdAt: "desc" },
    });

    const historyData = {
      strategyId,
      strategyName: body?.strategy_name ?? `전략 ${strategyId.slice(0, 8)}`,
      universe: resolveHistoryUniverseLabel(body, result),
      conditions: JSON.stringify({ entry: body.entry, exit: body.exit }),
      metrics: JSON.stringify(metrics),
      result: JSON.stringify({
        ...result,
        strategy_id: strategyId,
        cacheKey,
      }),
      cacheKey,
      isVisible: false,
    };

    if (existingHistory) {
      await prisma.backtestHistory.update({
        where: { id: existingHistory.id },
        data: historyData,
      });
      if (options.awaitVectorUpsert) {
        await runVectorMemoryBacktestUpsert({ throwOnFailure: true });
      } else {
        triggerVectorMemoryBacktestUpsert();
      }
      return;
    }

    await prisma.backtestHistory.create({
      data: historyData,
    });

    if (options.awaitVectorUpsert) {
      await runVectorMemoryBacktestUpsert({ throwOnFailure: true });
    } else {
      triggerVectorMemoryBacktestUpsert();
    }
  } catch (err) {
    console.error("[BacktestHistory] 자동 저장 실패:", err);
    if (options.awaitVectorUpsert) {
      throw err;
    }
  }
}
