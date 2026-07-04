/**
 * 백테스트 실행만으로 자동 저장된 Strategy 행은 한때 canonical_strategy_dsl
 * (entry_signals/최상위 stop_loss_pct 같은 사람이 읽기 좋은 요약)만 settings에
 * 저장하고, 실제 재실행/워크포워드에 필요한 entry.conditions/exit.conditions/risk.*
 * DSL은 저장하지 않았다(lib/server/backtestCache.ts의 upsertStrategyForResult 버그,
 * 이제 수정됨). 이 스크립트는 canonical 필드만 남은 기존 행을 백엔드
 * to_backtest_request()와 동일한 규칙으로 역변환해 entry/exit/risk/period/options/
 * universe_id를 채워 넣는다.
 *
 * 기본은 dry-run이다. 실제로 DB에 쓰려면 --apply를 넘겨라.
 *   npx ts-node scripts/backfill-strategy-settings-dsl.ts
 *   npx ts-node scripts/backfill-strategy-settings-dsl.ts --apply
 */
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

interface TechnicalSignal {
  indicator: string;
  signal_type: string;
  short_period?: number | null;
  long_period?: number | null;
  period?: number | null;
  operator?: string | null;
  value?: number | null;
  mode?: string | null;
  lookback_period?: number | null;
  threshold?: number | null;
}

interface FundamentalFilter {
  metric: string;
  operator: string;
  value: number;
}

// backend/engine/strategy_converter.py:_tech_signal_to_condition 포팅
function techSignalToCondition(sig: TechnicalSignal) {
  const params: Record<string, unknown> = { signalType: sig.signal_type };

  switch (sig.indicator) {
    case "ma_crossover":
      params.shortMA = sig.short_period || 5;
      params.longMA = sig.long_period || 20;
      break;
    case "rsi":
      params.period = sig.period || 14;
      params.operator = sig.operator || (sig.signal_type === "buy" ? "<" : ">");
      params.value = sig.value ?? (sig.signal_type === "buy" ? 30 : 70);
      if (sig.mode) params.mode = sig.mode;
      break;
    case "ema":
      if (sig.short_period && sig.long_period) {
        params.shortPeriod = sig.short_period;
        params.longPeriod = sig.long_period;
      } else {
        params.period = sig.period || 20;
      }
      break;
    case "macd":
      params.mode = sig.mode || "crossover";
      break;
    case "bollinger_bands":
      break;
    case "breakout":
      params.lookbackPeriod = sig.lookback_period || 20;
      break;
    case "volume_spike":
      params.period = sig.period || 20;
      break;
    case "stochastic":
      params.mode = sig.mode || "crossover";
      if (sig.operator) params.operator = sig.operator;
      if (sig.value != null) params.value = sig.value;
      break;
    case "cci":
    case "adx":
      if (sig.period) params.period = sig.period;
      if (sig.operator) params.operator = sig.operator;
      if (sig.value != null) params.value = sig.value;
      break;
    case "ai_model":
    case "ai_drop_model":
      params.threshold = sig.threshold ?? 70;
      if (sig.indicator === "ai_drop_model") params.targetType = "down";
      break;
    default:
      break;
  }

  return {
    type: "indicator",
    id: sig.indicator,
    params,
    weight: 1.0,
  };
}

function fundamentalFilterToCondition(filter: FundamentalFilter) {
  return {
    type: "filter",
    id: filter.metric,
    params: { operator: filter.operator, value: filter.value },
    weight: 1.0,
  };
}

function percentToRate(value: number | null | undefined): number | null {
  if (value == null) return null;
  return value / 100;
}

function deriveUniverseId(universe: unknown): string {
  if (Array.isArray(universe) && universe.length > 0) {
    return [...universe].map((m) => String(m).toLowerCase()).sort().join("_");
  }
  return "kospi200";
}

// canonical_strategy_dsl 잔재만 있는 (entry.conditions/risk가 없는) settings인지 판별
export function needsBackfill(settings: any): boolean {
  if (!settings || typeof settings !== "object") return false;
  const hasDsl = Array.isArray(settings.entry?.conditions) || (settings.risk && typeof settings.risk === "object");
  if (hasDsl) return false;

  const hasCanonicalMarkers =
    Array.isArray(settings.entry_signals) ||
    Array.isArray(settings.exit_signals) ||
    Array.isArray(settings.fundamental_filters) ||
    typeof settings.stop_loss_pct === "number" ||
    typeof settings.take_profit_pct === "number" ||
    typeof settings.trailing_stop_pct === "number" ||
    typeof settings.max_mdd_limit_pct === "number" ||
    typeof settings.max_positions === "number";

  return hasCanonicalMarkers;
}

// backend/engine/strategy_converter.py:to_backtest_request 중 DSL 구성 부분 포팅
export function buildDslFromCanonical(settings: any) {
  const entryConditions = [
    ...((settings.fundamental_filters ?? []) as FundamentalFilter[]).map(fundamentalFilterToCondition),
    ...((settings.entry_signals ?? []) as TechnicalSignal[]).map(techSignalToCondition),
  ];
  const exitConditions = ((settings.exit_signals ?? []) as TechnicalSignal[]).map(techSignalToCondition);

  const maxPositions = settings.max_positions ?? 10;
  const positionSizePct = Math.round((100 / maxPositions) * 100) / 100;

  const rebalancingPeriod = settings.rebalancing_period ?? null;
  let maxHoldingDays = settings.hold_period_days ?? null;
  if (rebalancingPeriod && rebalancingPeriod !== "none") {
    maxHoldingDays = null;
  }

  const risk: Record<string, unknown> = {
    position_size_pct: positionSizePct,
    max_positions: maxPositions,
    stop_loss_pct: settings.stop_loss_pct ?? null,
    take_profit_pct: settings.take_profit_pct ?? null,
    trailing_stop_pct: settings.trailing_stop_pct ?? null,
    max_mdd_limit_pct: settings.max_mdd_limit_pct ?? null,
    max_holding_days: maxHoldingDays,
    rebalancing_period: rebalancingPeriod,
    init_cash: settings.initial_capital ?? null,
    ranking_enabled: true,
    ranking_weight_value: 0.5,
    ranking_weight_quality: 0.5,
    ranking_metric: settings.ranking_metric ?? null,
    ranking_lookback_days:
      settings.ranking_lookback_days ?? (settings.ranking_metric ? 60 : null),
    execution_timing: settings.execution_timing ?? null,
    allocation_type: "equal",
  };

  const patch: Record<string, unknown> = {
    entry: { conditions: entryConditions },
    exit: { conditions: exitConditions },
    risk,
    universe_id: deriveUniverseId(settings.universe),
    options: {
      fee_rate: percentToRate(settings.fee_rate),
      slippage_rate: percentToRate(settings.slippage_rate),
    },
  };

  if (settings.backtest_period) patch.period = settings.backtest_period;
  if (settings.backtest_start_date) patch.startDate = settings.backtest_start_date;
  if (settings.backtest_end_date) patch.endDate = settings.backtest_end_date;

  return patch;
}

async function main() {
  const apply = process.argv.includes("--apply");

  const strategies = await prisma.strategy.findMany({
    select: { id: true, name: true, settings: true },
  });

  let scanned = 0;
  let candidates = 0;
  let fixed = 0;
  let parseErrors = 0;

  for (const strategy of strategies) {
    scanned += 1;
    let settings: any;
    try {
      settings = JSON.parse(strategy.settings);
    } catch {
      parseErrors += 1;
      continue;
    }

    if (!needsBackfill(settings)) continue;

    candidates += 1;
    const patch = buildDslFromCanonical(settings);
    const nextSettings = { ...settings, ...patch };

    console.log(
      `${apply ? "[FIX]" : "[DRY-RUN]"} ${strategy.id} (${strategy.name}) — ` +
        `entry조건 ${(nextSettings.entry as any).conditions.length}개, ` +
        `exit조건 ${(nextSettings.exit as any).conditions.length}개, ` +
        `stop_loss_pct=${(nextSettings.risk as any).stop_loss_pct}, ` +
        `take_profit_pct=${(nextSettings.risk as any).take_profit_pct}`
    );

    if (apply) {
      await prisma.strategy.update({
        where: { id: strategy.id },
        data: { settings: JSON.stringify(nextSettings) },
      });
      fixed += 1;
    }
  }

  console.log("");
  console.log(`전체 ${scanned}개 중 파싱 실패 ${parseErrors}개, 복구 대상 ${candidates}개, ${apply ? `실제 수정 ${fixed}개` : "dry-run(미적용)"}`);
  if (!apply && candidates > 0) {
    console.log("실제로 적용하려면: npx ts-node scripts/backfill-strategy-settings-dsl.ts --apply");
  }
}

if (require.main === module) {
  main()
    .catch((err) => {
      console.error(err);
      process.exitCode = 1;
    })
    .finally(async () => {
      await prisma.$disconnect();
    });
}
