import { t } from "@/lib/i18n";
import { INDICATOR_LABELS, METRIC_LABELS } from "@/lib/strategy-summary";
import { metaName, unitText } from "./graphBuilder";
import type { DetailRow, EngineCondition, GraphMeta, IndicatorMeta, NodeStatus } from "./types";

// Describes ONE engine condition (entry/exit/filter) from its structured params. The meaning of
// each param mirrors backend/engine/signals.py (SignalEngine._eval_vec); nothing here reads user
// prose and nothing is guessed: a condition whose shape is not known is reported as check_needed.

export interface ConditionDescription {
  name: string;
  expression: string;
  rows: DetailRow[];
  status: NodeStatus;
  statusNote: string | null;
  /** Canonical indicator id resolved through the registry engine binding (null if unknown). */
  leafId: string | null;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const text = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const row = (label: string, value: string | number): DetailRow => ({ label, value: String(value) });

const NO_THRESHOLD = (): DetailRow => row(t("기준값"), t("해당 없음"));

// Index-style units ("point", "event") read better without a suffix in an expression.
const unitSuffix = (unit: string | null | undefined): string =>
  unit === "point" || unit === "event" ? "" : unitText(unit) ?? "";

export function resolveLeafId(cond: EngineCondition, meta: GraphMeta | null): string | null {
  const id = cond.id ?? "";
  if (!meta || !id) return null;
  const params = cond.params ?? {};
  if (id === "candle_pattern") {
    const pattern = text(params.pattern);
    return pattern ? meta.bindings[`technical_signal:candle_${pattern}`] ?? null : null;
  }
  if (cond.type === "filter") {
    const fundamental = meta.bindings[`fundamental_filter:${id}`];
    if (fundamental) return fundamental;
  }
  return meta.bindings[`technical_signal:${id}`] ?? meta.bindings[`fundamental_filter:${id}`] ?? null;
}

function indicatorName(cond: EngineCondition, meta: IndicatorMeta | null): string {
  if (meta) return metaName(meta);
  const id = cond.id ?? "";
  if (id === "candle_pattern") return t("캔들 패턴");
  return INDICATOR_LABELS[id] ?? METRIC_LABELS[id] ?? t("지표 이름 확인 불가");
}

function thresholdRows(
  op: string | null,
  value: number | null,
  unit: string,
): { rows: DetailRow[]; status: NodeStatus; note: string | null } {
  if (value === null) {
    return {
      rows: [row(t("기준값"), t("미정"))],
      status: "pending",
      note: t("기준값이 스냅샷에 없습니다. 실행 시 엔진 기본값이 쓰일 수 있습니다."),
    };
  }
  const rows = [row(t("기준값"), `${value}${unit}`)];
  if (op) rows.unshift(row(t("연산자"), op));
  return { rows, status: "ok", note: null };
}

function comparison(
  name: string,
  period: number | null,
  p: Record<string, unknown>,
  unitMeta: IndicatorMeta | null,
  periodLabel = t("기간"),
): Pick<ConditionDescription, "expression" | "rows" | "status" | "statusNote"> {
  const op = text(p.operator);
  const value = num(p.value);
  const unit = unitSuffix(unitMeta?.unit);
  const th = thresholdRows(op, value, unit);
  const head = period === null ? name : name.includes("(") ? `${name} · ${t("{0}일", period)}` : `${name}(${period})`;
  const expression = value === null ? `${head} ${op ?? ""}`.trim() : `${head} ${op ?? ""} ${value}${unit}`.trim();
  const rows = period !== null ? [row(periodLabel, t("{0}일", period)), ...th.rows] : th.rows;
  return { expression, rows, status: th.status, statusNote: th.note };
}

// Wording reuses the strings of lib/strategy-summary.ts (movingAverageLabel) so the graph reads
// like the rest of the product and shares its existing English translations.
function linePair(
  kind: "sma" | "ema",
  short: number | null,
  long: number | null,
  mode: string | null,
  sell: boolean,
): { expression: string; rows: DetailRow[] } {
  const rows: DetailRow[] = [];
  if (short !== null) rows.push(row(t("단기 기간"), t("{0}일", short)));
  if (long !== null) rows.push(row(t("장기 기간"), t("{0}일", long)));
  const stays = mode === "above" || mode === "below";
  const down = stays ? mode === "below" : sell;
  const priceRelative = short === null || short === 1;
  rows.push(row(t("판정 방식"), stays ? t("지속 상태(교차 사건 아님)") : t("교차 사건")), NO_THRESHOLD());
  if (long === null) return { expression: kind === "ema" ? "EMA" : t("이동평균"), rows };

  let expression: string;
  if (kind === "ema") {
    if (priceRelative) {
      expression = stays
        ? down ? t("종가가 EMA{0} 아래 유지", long) : t("종가가 EMA{0} 위 유지", long)
        : down ? t("가격 EMA{0} 하향 돌파", long) : t("가격 EMA{0} 상향 돌파", long);
    } else {
      expression = stays
        ? down ? t("EMA{0}이 EMA{1} 아래 유지", short, long) : t("EMA{0}이 EMA{1} 위 유지", short, long)
        : down ? t("EMA{0}-EMA{1} 데드크로스", short, long) : t("EMA{0}-EMA{1} 골든크로스", short, long);
    }
  } else if (priceRelative) {
    expression = stays
      ? down ? t("종가가 {0}일선 아래 유지", long) : t("종가가 {0}일선 위 유지", long)
      : down ? t("종가가 {0}일선 하향 이탈", long) : t("종가가 {0}일선 상향 돌파", long);
  } else {
    expression = stays
      ? down ? t("{0}일선이 {1}일선 아래 유지", short, long) : t("{0}일선이 {1}일선 위 유지", short, long)
      : down ? t("{0}일선-{1}일선 데드크로스", short, long) : t("{0}일선-{1}일선 골든크로스", short, long);
  }
  return { expression, rows };
}

function crossStatus(): { status: NodeStatus; statusNote: string | null } {
  return { status: "not_applicable", statusNote: t("교차 사건이라 기준값이 필요하지 않습니다.") };
}

const LEVEL_INDICATORS = new Set([
  "cci", "adx", "williams_r", "mfi", "roc", "disparity", "volatility", "relative_return",
  "volume_ratio", "trading_value_ratio", "trading_value",
]);

export function describeCondition(cond: EngineCondition, meta: GraphMeta | null): ConditionDescription {
  const id = cond.id ?? "";
  const p = (cond.params ?? {}) as Record<string, unknown>;
  const leafId = resolveLeafId(cond, meta);
  const leaf = leafId && meta ? meta.indicators[leafId] ?? null : null;
  const name = indicatorName(cond, leaf);
  const sell = p.signalType === "sell";
  const base = { name, leafId };

  if (cond.type === "filter" && (meta?.bindings[`fundamental_filter:${id}`] || METRIC_LABELS[id])) {
    const cmp = comparison(name, null, p, leaf);
    const period = text(p.period);
    return { ...base, ...cmp, rows: period ? [row(t("기준 기간"), period), ...cmp.rows] : cmp.rows };
  }

  if (id === "ma_crossover" || id === "ema") {
    const kind = id === "ema" ? "ema" : "sma";
    const short = num(kind === "ema" ? p.shortPeriod : p.shortMA);
    const long = num(kind === "ema" ? p.longPeriod ?? p.period : p.longMA);
    const mode = text(p.mode);
    const pair = linePair(kind, short, long, mode, sell);
    return { ...base, ...pair, ...(mode === "above" || mode === "below" ? { status: "not_applicable" as const, statusNote: t("지속 상태 판정이라 기준값이 필요하지 않습니다.") } : crossStatus()) };
  }

  if (id === "rsi") {
    const period = num(p.period);
    const head = period !== null ? `RSI(${period})` : "RSI";
    if (p.mode === "rebound") {
      const value = num(p.value);
      const rows = [
        ...(period !== null ? [row(t("기간"), t("{0}일", period))] : []),
        row(t("판정 방식"), t("기준선 재돌파")),
        row(t("기준값"), value === null ? t("미정") : String(value)),
      ];
      return {
        ...base,
        expression: sell
          ? t("{0}가 {1} 선을 하향 재돌파", head, value ?? "?")
          : t("{0}가 {1} 선을 상향 재돌파", head, value ?? "?"),
        rows,
        status: value === null ? "pending" : "ok",
        statusNote: value === null ? t("기준값이 스냅샷에 없습니다. 실행 시 엔진 기본값이 쓰일 수 있습니다.") : null,
      };
    }
    return { ...base, ...comparison("RSI", period, p, leaf) };
  }

  if (id === "macd") {
    const mode = text(p.mode) ?? "crossover";
    const fast = num(p.fastPeriod);
    const slow = num(p.slowPeriod);
    const sig = num(p.signalPeriod);
    const rows: DetailRow[] = [];
    if (fast !== null) rows.push(row(t("단기 기간"), t("{0}일", fast)));
    if (slow !== null) rows.push(row(t("장기 기간"), t("{0}일", slow)));
    if (sig !== null) rows.push(row(t("시그널 기간"), t("{0}일", sig)));
    if (mode === "zero") {
      rows.push(row(t("판정 방식"), t("0선 비교")), row(t("기준값"), "0"));
      return { ...base, expression: sell ? t("MACD < 0") : t("MACD > 0"), rows, status: "ok", statusNote: null };
    }
    rows.push(row(t("판정 방식"), t("교차 사건")), NO_THRESHOLD());
    return {
      ...base,
      expression: sell ? t("MACD가 시그널선을 하향 돌파") : t("MACD가 시그널선을 상향 돌파"),
      rows,
      ...crossStatus(),
    };
  }

  if (id === "bollinger_bands") {
    const period = num(p.period);
    const rows: DetailRow[] = period !== null ? [row(t("기간"), t("{0}일", period))] : [];
    const band = text(p.band);
    if (band) {
      const bandName = band === "upper" ? t("상단 밴드") : band === "middle" ? t("중심선") : t("하단 밴드");
      const bandObject = band === "middle" ? t("중심선을") : band === "upper" ? t("상단 밴드를") : t("하단 밴드를");
      const below = p.cross === "below";
      const lookback = num(p.touchLookback);
      rows.push(row(t("대상 밴드"), bandName), row(t("판정 방식"), t("교차 사건")), NO_THRESHOLD());
      if (lookback !== null) rows.push(row(t("하단 터치 확인 기간"), t("{0}거래일", lookback)));
      const cross = below ? t("종가가 {0} 하향 돌파", bandObject) : t("종가가 {0} 상향 돌파", bandObject);
      return {
        ...base,
        expression: lookback !== null ? t("{0} (직전 {1}거래일 안에 하단 터치)", cross, lookback) : cross,
        rows,
        ...crossStatus(),
      };
    }
    rows.push(row(t("판정 방식"), t("밴드 이탈 상태")), NO_THRESHOLD());
    return {
      ...base,
      expression: sell ? t("종가가 볼린저 상단 밴드 이상") : t("종가가 볼린저 하단 밴드 이하"),
      rows,
      status: "not_applicable",
      statusNote: t("밴드 위치로 판정해 기준값이 필요하지 않습니다."),
    };
  }

  if (id === "breakout") {
    const period = num(p.lookbackPeriod);
    const rows = [...(period !== null ? [row(t("확인 기간"), t("{0}거래일", period))] : []), row(t("판정 방식"), t("돌파 사건")), NO_THRESHOLD()];
    return {
      ...base,
      expression: p.priceBasis === "close"
        ? (sell || p.side === "low"
          ? t("종가가 직전 {0}거래일 최저 종가를 하향 돌파", period ?? "?")
          : t("종가가 직전 {0}거래일 최고 종가를 상향 돌파", period ?? "?"))
        : sell || p.side === "low"
          ? t("저가가 직전 {0}거래일 최저가를 하향 돌파", period ?? "?")
          : t("고가가 직전 {0}거래일 최고가를 상향 돌파", period ?? "?"),
      rows,
      ...crossStatus(),
    };
  }

  if (id === "volume_spike") {
    const period = num(p.period);
    return {
      ...base,
      expression: sell ? t("OBV가 {0}일 평균을 하향 돌파", period ?? "?") : t("OBV가 {0}일 평균을 상향 돌파", period ?? "?"),
      rows: [...(period !== null ? [row(t("기간"), t("{0}일", period))] : []), row(t("판정 방식"), t("교차 사건")), NO_THRESHOLD()],
      ...crossStatus(),
    };
  }

  if (id === "buy_at_start") {
    return {
      ...base,
      expression: t("백테스트 시작일에 매수하고 계속 보유"),
      rows: [row(t("판정 방식"), t("시작일 1회")), NO_THRESHOLD()],
      status: "not_applicable",
      statusNote: t("조건 없이 시작일에 사는 규칙이라 기준값이 필요하지 않습니다."),
    };
  }

  if (id === "consecutive_up") {
    const period = num(p.period);
    return {
      ...base,
      expression: t("{0}거래일 연속 종가 상승", period ?? "?"),
      rows: [...(period !== null ? [row(t("연속 기간"), t("{0}거래일", period))] : []), NO_THRESHOLD()],
      status: period === null ? "pending" : "not_applicable",
      statusNote: period === null ? t("연속 기간이 스냅샷에 없습니다.") : t("연속 상승 판정이라 기준값이 필요하지 않습니다."),
    };
  }

  if (id === "consecutive_down") {
    const period = num(p.period);
    return {
      ...base,
      expression: t("{0}거래일 연속 종가 하락", period ?? "?"),
      rows: [...(period !== null ? [row(t("연속 기간"), t("{0}거래일", period))] : []), NO_THRESHOLD()],
      status: period === null ? "pending" : "not_applicable",
      statusNote: period === null ? t("연속 기간이 스냅샷에 없습니다.") : t("연속 하락 판정이라 기준값이 필요하지 않습니다."),
    };
  }

  if (id === "candle_pattern") {
    return {
      ...base,
      expression: name,
      rows: [row(t("판정 방식"), t("패턴 감지")), NO_THRESHOLD()],
      status: "not_applicable",
      statusNote: t("패턴 감지라 기준값이 필요하지 않습니다."),
    };
  }

  if (id === "stochastic") {
    const mode = text(p.mode) ?? "crossover";
    if (mode === "level") {
      return { ...base, ...comparison(name, num(p.period), p, leaf) };
    }
    return {
      ...base,
      expression: sell ? t("%K가 %D를 하향 돌파") : t("%K가 %D를 상향 돌파"),
      rows: [row(t("판정 방식"), t("교차 사건")), NO_THRESHOLD()],
      ...crossStatus(),
    };
  }

  if (LEVEL_INDICATORS.has(id)) {
    return { ...base, ...comparison(name, num(p.period), p, leaf) };
  }

  if (id === "ai_model" || id === "ai_drop_model") {
    const threshold = num(p.threshold) ?? num(p.minProbability);
    const rank = p.exitMode === "rank";
    return {
      ...base,
      expression: name,
      rows: [row(t("기준값"), threshold === null ? (rank ? t("해당 없음") : t("미정")) : String(threshold))],
      status: threshold === null && !rank ? "pending" : "ok",
      statusNote: threshold === null && !rank ? t("기준값이 스냅샷에 없습니다. 실행 시 엔진 기본값이 쓰일 수 있습니다.") : null,
    };
  }

  return {
    ...base,
    expression: name,
    rows: [],
    status: "check_needed",
    statusNote: t("이 조건의 세부 의미를 스냅샷에서 확인할 수 없습니다."),
  };
}
