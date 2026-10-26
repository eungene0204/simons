import { t } from "@/lib/i18n";
import { METRIC_LABELS, REBAL_LABELS, REBAL_METHOD_LABELS, UNIVERSE_LABELS, formatInitialCapital, formatRequestPeriodLabel } from "@/lib/strategy-summary";
import type { ParsedSummary } from "@/lib/strategy-summary";
import { classPathOf, linkIndicator, supportNote } from "./concepts";
import { describeCondition } from "./conditions";
import { GraphBuilder, metaName, row } from "./graphBuilder";
import type { DetailRow, EngineCondition, EngineRequestLike, NodeKind, NodeStatus, SectionKey } from "./types";

// Builds the strategy-instance part of the graph. Every value comes from the request (the
// executable truth) or, for confirmed snapshots, from the parsed result that was returned by the
// same confirm response (pending states live only there). Nothing is read from prose.

export interface SectionCtx {
  b: GraphBuilder;
  req: EngineRequestLike;
  parsed: ParsedSummary | null;
  /** Drafts: fields the user stated. null = everything counts as stated (confirmed/executed). */
  stated: ReadonlySet<string> | null;
}

const isStated = (ctx: SectionCtx, field: string): boolean => ctx.stated === null || ctx.stated.has(field);

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const risk = (ctx: SectionCtx): Record<string, unknown> => (ctx.req.risk ?? {}) as Record<string, unknown>;
const ref = (path: string) => `snapshot.${path}`;

export const SECTION_LABELS: Record<SectionKey, string> = {
  universe: "투자 대상",
  filters: "종목 선정 필터",
  ranking: "순위 선정",
  entry: "매수 규칙",
  exit: "매도 규칙",
  allocation: "자금 배분",
  rebalance: "리밸런싱",
  risk: "위험 관리",
};

function section(ctx: SectionCtx, key: SectionKey, rows: DetailRow[] = []): string {
  const id = `section:${key}`;
  if (!ctx.b.has(id)) {
    ctx.b.node(id, "section", t(SECTION_LABELS[key]), "ok", ref(key), key, { role: t(SECTION_LABELS[key]), rows });
    ctx.b.edge("has_section", "strategy", id, "");
  }
  return id;
}

interface SettingArgs {
  key: string;
  label: string;
  rows?: DetailRow[];
  status?: NodeStatus;
  note?: string | null;
  kind?: NodeKind;
  expression?: string | null;
  source?: "request" | "parsed" | "engine_default";
  path?: string;
}

function setting(ctx: SectionCtx, key: SectionKey, parent: string, a: SettingArgs): string {
  const id = `setting:${key}/${a.key}`;
  ctx.b.node(id, a.kind ?? "setting", a.label, a.status ?? "ok", ref(a.path ?? `${key}.${a.key}`), key, {
    role: t(SECTION_LABELS[key]),
    expression: a.expression ?? a.label,
    rows: a.rows ?? [],
    statusNote: a.note ?? null,
    valueSource: a.source ?? "request",
  });
  ctx.b.edge("contains", parent, id, "");
  return id;
}

// ── conditions (entry / exit / filters) ────────────────────────────────────────────────────

type CondRole = "filters" | "entry" | "exit";

function conditionNode(ctx: SectionCtx, key: CondRole, cond: EngineCondition, index: number, arrayName: "entry" | "exit", parent: string, edgeLabel: string): string {
  const desc = describeCondition(cond, ctx.b.meta);
  const id = `cond:${key}/${arrayName}.${index}`;
  const leaf = desc.leafId && ctx.b.meta ? ctx.b.meta.indicators[desc.leafId] : null;
  const rows = [...desc.rows];
  if (leaf) {
    const note = supportNote(leaf);
    if (note) rows.push(row(t("지원 상태"), note));
  }
  ctx.b.node(id, "condition", desc.expression, desc.status, ref(`request.${arrayName}.conditions[${index}]`), key, {
    role: t(SECTION_LABELS[key]),
    expression: desc.expression,
    rows,
    support: leaf?.supported ?? null,
    classPath: leaf && ctx.b.meta ? classPathOf(ctx.b.meta, leaf.classId) : [],
    statusNote: desc.statusNote,
    valueSource: "request",
  });
  ctx.b.edge(edgeLabel ? "combined_by" : "contains", parent, id, edgeLabel);
  linkIndicator(ctx.b, id, desc.leafId);
  return id;
}

/**
 * entry.logic only combines non-filter signals; filters are always AND (SignalEngine). The exit
 * group carries no logic of its own, so the engine default (OR) applies and is labelled so.
 */
function combineGroup(ctx: SectionCtx, key: CondRole, parent: string, count: number, logic: string | null | undefined, kind: "entry-signals" | "filters" | "exit"): { id: string; edgeLabel: string } {
  if (count < 2) return { id: parent, edgeLabel: "" };
  const gid = `group:${key}`;
  const upper = typeof logic === "string" ? logic.toUpperCase() : null;
  let label: string;
  let status: NodeStatus = "ok";
  let note: string | null = null;
  let source: "request" | "engine_default" = "request";
  let edgeLabel: string;
  if (kind === "filters") {
    label = t("모두 충족 (AND)");
    edgeLabel = "AND";
    note = t("필터 조건은 항상 AND로 결합됩니다.");
    source = "engine_default";
  } else if (upper === "AND" || upper === "OR") {
    label = upper === "AND" ? t("모두 충족 (AND)") : t("하나라도 충족 (OR)");
    edgeLabel = upper;
  } else if (logic == null && kind === "exit") {
    label = t("하나라도 충족 (OR)");
    edgeLabel = "OR";
    note = t("스냅샷에 결합 방식이 없어 엔진 기본값(OR)이 적용됩니다.");
    source = "engine_default";
  } else {
    label = t("결합 방식 확인 필요");
    status = "check_needed";
    edgeLabel = "?";
    note = t("스냅샷의 결합 방식을 확인할 수 없습니다.");
  }
  ctx.b.node(gid, "group", label, status, ref(kind === "exit" ? "request.exit.logic" : "request.entry.logic"), key, {
    role: t(SECTION_LABELS[key]),
    expression: label,
    statusNote: note,
    valueSource: source,
  });
  ctx.b.edge("contains", parent, gid, "");
  return { id: gid, edgeLabel };
}

export function buildFilters(ctx: SectionCtx): void {
  const entry = ctx.req.entry?.conditions ?? [];
  const filters = entry.map((c, i) => ({ c, i })).filter((x) => x.c.type === "filter");
  const r = risk(ctx);
  const prefilters: Array<{ key: string; label: string; rows: DetailRow[] }> = [];
  const topN = num(r.universe_market_cap_top_n);
  if (topN !== null) prefilters.push({ key: "mcap_top", label: t("시가총액 상위 {0}종목", topN), rows: [row(t("종목 수"), topN)] });
  const liq = num(r.universe_liquidity_exclude_bottom_pct);
  if (liq !== null) {
    const days = num(r.universe_liquidity_lookback_days);
    prefilters.push({ key: "liq_bottom", label: t("평균 거래대금 하위 {0}% 제외", liq), rows: [row(t("제외 비율"), `${liq}%`), ...(days !== null ? [row(t("산정 기간"), t("{0}일", days))] : [])] });
  }
  const mcapBottom = num(r.universe_market_cap_exclude_bottom_pct);
  if (mcapBottom !== null) prefilters.push({ key: "mcap_bottom", label: t("시가총액 하위 {0}% 제외", mcapBottom), rows: [row(t("제외 비율"), `${mcapBottom}%`)] });
  if (typeof r.universe_exclude_loss_making === "string" && r.universe_exclude_loss_making) {
    prefilters.push({ key: "loss", label: t("적자 기업 제외"), rows: [row(t("기준"), String(r.universe_exclude_loss_making))] });
  }
  if (filters.length === 0 && prefilters.length === 0) return;

  const sec = section(ctx, "filters");
  const g = combineGroup(ctx, "filters", sec, filters.length, null, "filters");
  filters.forEach(({ c, i }) => conditionNode(ctx, "filters", c, i, "entry", g.id, g.edgeLabel));
  prefilters.forEach((p) => setting(ctx, "filters", sec, { key: p.key, label: p.label, rows: p.rows, path: `request.risk.${p.key}` }));
}

export function buildEntry(ctx: SectionCtx): void {
  const entry = ctx.req.entry?.conditions ?? [];
  const signals = entry.map((c, i) => ({ c, i })).filter((x) => x.c.type !== "filter");
  if (signals.length === 0) return;
  const sec = section(ctx, "entry");
  const g = combineGroup(ctx, "entry", sec, signals.length, ctx.req.entry?.logic, "entry-signals");
  signals.forEach(({ c, i }) => conditionNode(ctx, "entry", c, i, "entry", g.id, g.edgeLabel));
}

export function buildExit(ctx: SectionCtx): void {
  const exit = ctx.req.exit?.conditions ?? [];
  if (exit.length === 0) return;
  const sec = section(ctx, "exit");
  const g = combineGroup(ctx, "exit", sec, exit.length, ctx.req.exit?.logic, "exit");
  exit.forEach((c, i) => conditionNode(ctx, "exit", c, i, "exit", g.id, g.edgeLabel));
}

// ── universe ───────────────────────────────────────────────────────────────────────────────

export function buildUniverse(ctx: SectionCtx): void {
  const req = ctx.req;
  const targets = req.target_stocks?.length ? req.target_stocks.map((s) => s.name || s.symbol) : req.backtest_mode === "single_asset" ? req.symbols ?? [] : [];
  if (!req.universe_id && targets.length === 0) return;
  const sec = section(ctx, "universe");
  if (targets.length > 0) {
    setting(ctx, "universe", sec, { key: "targets", label: t("지정 종목 {0}개", targets.length), rows: [row(t("종목"), targets.join(", "))], path: "request.target_stocks" });
  } else if (req.universe_id) {
    const tokens = req.universe_id.split("_").map((tok) => t(UNIVERSE_LABELS[tok] ?? UNIVERSE_LABELS[tok.toLowerCase()] ?? tok.toUpperCase()));
    setting(ctx, "universe", sec, { key: "markets", label: tokens.join(" + "), rows: [], path: "request.universe_id" });
  }
  const sector = Array.isArray(req.sector) ? req.sector.join(", ") : req.sector;
  if (sector) setting(ctx, "universe", sec, { key: "sector", label: t("업종: {0}", sector), rows: [row(t("업종"), sector)], path: "request.sector" });
  if (req.etf_theme) setting(ctx, "universe", sec, { key: "etf_theme", label: t("ETF 테마: {0}", req.etf_theme), rows: [row(t("ETF 테마"), req.etf_theme)], path: "request.etf_theme" });
  if (req.us_industry) setting(ctx, "universe", sec, { key: "us_industry", label: t("업종: {0}", req.us_industry), rows: [row(t("업종"), req.us_industry)], path: "request.us_industry" });
  if (req.exclude_sectors?.length) setting(ctx, "universe", sec, { key: "exclude_sectors", label: t("제외 업종: {0}", req.exclude_sectors.join(", ")), rows: [row(t("제외 업종"), req.exclude_sectors.join(", "))], path: "request.exclude_sectors" });
  if (req.listing_from || req.listing_to) {
    const span = `${req.listing_from ?? ""} ~ ${req.listing_to ?? ""}`;
    setting(ctx, "universe", sec, { key: "listing", label: t("상장 기간 {0}", span), rows: [row(t("상장 기간"), span)], path: "request.listing_from" });
  }
}

// ── ranking ────────────────────────────────────────────────────────────────────────────────

const PRICE_RANKINGS = new Set(["return", "volatility", "residual_reversal"]);

function rankingName(ctx: SectionCtx, metric: string): { name: string; leafId: string | null } {
  const meta = ctx.b.meta;
  const leafId = meta ? meta.bindings[`ranking:${metric}`] ?? meta.bindings[`fundamental_filter:${metric}`] ?? null : null;
  const ind = leafId && meta ? meta.indicators[leafId] : null;
  const name = ind ? metaName(ind) : null;
  return { name: name ?? METRIC_LABELS[metric] ?? t("순위 기준"), leafId };
}

export function buildRanking(ctx: SectionCtx): void {
  const r = risk(ctx);
  const metric = typeof r.ranking_metric === "string" ? r.ranking_metric : null;
  if (!metric || r.ranking_enabled === false) return;
  const sec = section(ctx, "ranking");
  const direction = r.ranking_direction === "bottom" ? t("낮은 순") : r.ranking_direction === "top" ? t("높은 순") : null;
  const rows: DetailRow[] = [];
  const lookback = num(r.ranking_lookback_days);
  if (direction) rows.push(row(t("정렬"), direction));
  if (lookback !== null) rows.push(row(t("산정 기간"), t("{0}일", lookback)));
  const skip = num(r.ranking_skip_days);
  if (skip !== null) rows.push(row(t("최근 제외 기간"), t("{0}거래일", skip)));
  const accumulation = num(r.ranking_accumulation_days);
  if (accumulation !== null) rows.push(row(t("잔차 누적 기간"), t("{0}일", accumulation)));
  const delay = num(r.ranking_entry_delay_days);
  if (delay !== null) rows.push(row(t("편입 지연"), t("{0}거래일", delay)));
  const expiry = num(r.ranking_expiry_days);
  if (expiry !== null) rows.push(row(t("제외 기한"), t("{0}거래일", expiry)));
  const groups = num(r.ranking_quantile_groups);
  if (groups !== null) rows.push(row(t("분위 그룹"), t("{0}개", groups)));
  const cap = num(r.ranking_group_cap);
  if (cap !== null) rows.push(row(t("그룹당 보유 상한"), t("{0}종목", cap)));
  const pct = num(r.max_positions_pct);
  if (pct !== null) rows.push(row(t("선정 비율"), `${pct}%`));
  const floor = metric === "return" ? num(r.absolute_momentum_threshold_pct) : null;
  if (floor !== null) rows.push(row(t("최소 수익률"), t("{0}% 초과", floor)));

  // A lookback the user never stated is filled by the compiler (60 days); say so when we can tell.
  const parsedLookback = ctx.parsed?.ranking_lookback_days;
  const compilerFilled = ctx.parsed != null && PRICE_RANKINGS.has(metric) && (parsedLookback === null || parsedLookback === undefined) && lookback !== null;
  const components = Array.isArray(r.ranking_components) ? (r.ranking_components as Array<Record<string, unknown>>) : [];

  if (metric === "composite") {
    const id = setting(ctx, "ranking", sec, { key: "composite", label: t("복합 순위 합산"), rows, kind: "condition", path: "request.risk.ranking_components" });
    components.forEach((c, i) => {
      const m = typeof c.metric === "string" ? c.metric : "";
      const { name, leafId } = rankingName(ctx, m);
      const crow: DetailRow[] = [row(t("정렬"), c.direction === "bottom" ? t("낮은 순") : t("높은 순"))];
      const lb = num(c.lookback_days);
      if (lb !== null) crow.push(row(t("산정 기간"), t("{0}일", lb)));
      const sk = num(c.skip_days);
      if (sk !== null) crow.push(row(t("최근 제외 기간"), t("{0}거래일", sk)));
      const w = num(c.weight);
      if (w !== null) crow.push(row(t("가중치"), w));
      if (typeof c.group === "string" && c.group) crow.push(row(t("묶음 점수"), c.group));
      const cid = `cond:ranking/component.${i}`;
      ctx.b.node(cid, "condition", name, "ok", ref(`request.risk.ranking_components[${i}]`), "ranking", { role: t(SECTION_LABELS.ranking), expression: name, rows: crow, valueSource: "request" });
      ctx.b.edge("contains", id, cid, "");
      linkIndicator(ctx.b, cid, leafId);
    });
    return;
  }

  const { name, leafId } = rankingName(ctx, metric);
  const base = direction ? `${name} (${direction})` : name;
  const id = setting(ctx, "ranking", sec, {
    key: "metric",
    // 하한은 라벨에도 싣는다 — 상세 줄에만 두면 그래프·요약 카드에서 '30% 이상 오른'이 보이지 않는다(2026-10-26).
    label: floor !== null ? t("{0} · 최소 {1}% 초과", base, floor) : base,
    rows,
    kind: "condition",
    note: compilerFilled ? t("산정 기간은 사용자가 지정하지 않아 컴파일러 보정값이 쓰였습니다.") : null,
    path: "request.risk.ranking_metric",
  });
  linkIndicator(ctx.b, id, leafId);
}

// ── allocation / rebalance / risk ──────────────────────────────────────────────────────────

const ALLOCATION_LABELS: Record<string, string> = {
  equal: "동일 비중",
  inverse_volatility: "변동성 역비중",
  market_cap: "시가총액 비중",
  min_variance: "최소 분산",
  risk_parity: "위험 기여 균등",
  max_sharpe: "최대 샤프",
  min_cvar: "최소 CVaR",
  fixed: "고정 배분",
};

function pendingNode(ctx: SectionCtx, key: SectionKey, parent: string, k: string, label: string): void {
  setting(ctx, key, parent, { key: `${k}_pending`, label: t("{0} (값 미정)", label), status: "pending", rows: [row(t("상태"), t("미정"))], note: t("값이 정해지지 않아 실행 요청에 포함되지 않았습니다."), source: "parsed", path: `parsed.${k}` });
}

export function buildAllocation(ctx: SectionCtx): void {
  const r = risk(ctx);
  const p = ctx.parsed;
  const rows: Array<() => void> = [];
  const sec = () => section(ctx, "allocation");

  const maxPos = isStated(ctx, "max_positions") ? num(r.max_positions) : null;
  const explicit = ctx.req.backtest_mode === "single_asset";
  if (maxPos !== null) {
    rows.push(() => setting(ctx, "allocation", sec(), { key: "max_positions", label: explicit ? t("지정 종목 {0}개", maxPos) : t("최대 {0}종목 보유", maxPos), rows: [row(t("종목 수"), maxPos)], path: "request.risk.max_positions" }));
  }
  const size = isStated(ctx, "max_positions") ? num(r.position_size_pct) : null;
  if (size !== null) {
    const cap = num(r.max_position_weight_pct);
    const drows = [row(t("비중"), `${size}%`), row(t("비중 기준"), t("진입 시점 포트폴리오 평가액(총자산) 대비"))];
    if (cap !== null) drows.push(row(t("종목당 상한"), `${cap}%`));
    rows.push(() => setting(ctx, "allocation", sec(), { key: "position_size", label: t("종목당 비중 {0}%", size), rows: drows, path: "request.risk.position_size_pct" }));
  }
  const alloc = typeof r.allocation_type === "string" ? r.allocation_type : null;
  if (alloc) {
    const lb = num(r.allocation_lookback_days);
    rows.push(() => setting(ctx, "allocation", sec(), { key: "allocation_type", label: t("비중 방식: {0}", t(ALLOCATION_LABELS[alloc] ?? alloc)), rows: lb !== null ? [row(t("산정 기간"), t("{0}일", lb))] : [], path: "request.risk.allocation_type" }));
  }
  const weights = r.target_weights as Record<string, number> | null | undefined;
  if (weights && typeof weights === "object") {
    rows.push(() => setting(ctx, "allocation", sec(), { key: "target_weights", label: t("고정 배분"), rows: Object.entries(weights).map(([k, v]) => row(k, `${v}%`)), path: "request.risk.target_weights" }));
  }
  const cash = isStated(ctx, "initial_capital") ? num(r.init_cash) : null;
  if (cash !== null) rows.push(() => setting(ctx, "allocation", sec(), { key: "init_cash", label: t("초기 자본 {0}", formatInitialCapital(cash)), rows: [row(t("초기 자본"), formatInitialCapital(cash))], path: "request.risk.init_cash" }));
  // Backtest window: relative period ("3y") or an explicit start/end range from the request.
  const periodLabel = isStated(ctx, "backtest_period") ? formatRequestPeriodLabel(ctx.req) : null;
  if (periodLabel) rows.push(() => setting(ctx, "allocation", sec(), { key: "period", label: t("백테스트 기간 {0}", periodLabel), rows: [row(t("기간"), periodLabel)], path: "request.period" }));
  const sizing = r.position_sizing as Record<string, unknown> | null | undefined;
  if (sizing && typeof sizing === "object") {
    const srows = Object.entries(sizing).filter(([k]) => k !== "method").map(([k, v]) => row(SIZING_LABELS[k] ?? k, String(v)));
    rows.push(() => setting(ctx, "allocation", sec(), { key: "position_sizing", label: sizing.method === "kelly" ? t("켈리 사이징") : t("ATR 위험 사이징"), rows: srows, path: "request.risk.position_sizing" }));
  }
  const sectorCap = num(r.max_sector_weight_pct);
  if (sectorCap !== null) rows.push(() => setting(ctx, "allocation", sec(), { key: "sector_cap", label: t("업종당 비중 상한 {0}%", sectorCap), rows: [row(t("상한"), `${sectorCap}%`)], path: "request.risk.max_sector_weight_pct" }));
  const tranches = r.entry_tranches as Record<string, unknown> | null | undefined;
  if (tranches && typeof tranches === "object") {
    const levels = Array.isArray(tranches.levels) ? (tranches.levels as Array<Record<string, unknown>>) : [];
    const trows = levels.length
      ? [row(t("첫 회차 비중"), `${tranches.first_pct}%`), ...levels.map((lv, i) => row(t("{0}단계", i + 1), t("{0}% 하락 시 {1}% 추가", lv.drop_pct, lv.size_pct)))]
      : [row(t("회차 수"), String(tranches.count)), row(t("회차 간격"), `${tranches.step_pct}%`)];
    rows.push(() => setting(ctx, "allocation", sec(), { key: "entry_tranches", label: t("분할 매수"), rows: trows, path: "request.risk.entry_tranches" }));
  }
  const contribution = num(r.contribution_amount);
  if (contribution !== null && r.contribution_period) {
    rows.push(() => setting(ctx, "allocation", sec(), { key: "contribution", label: t("정기 적립 {0}", formatInitialCapital(contribution)), rows: [row(t("금액"), formatInitialCapital(contribution)), row(t("주기"), t(REBAL_LABELS[String(r.contribution_period)] ?? String(r.contribution_period)))], path: "request.risk.contribution_amount" }));
  }
  const withdrawal = num(r.withdrawal_amount);
  if (withdrawal !== null && r.withdrawal_period) {
    rows.push(() => setting(ctx, "allocation", sec(), { key: "withdrawal", label: t("정기 인출 {0}", formatInitialCapital(withdrawal)), rows: [row(t("금액"), formatInitialCapital(withdrawal)), row(t("주기"), t(REBAL_LABELS[String(r.withdrawal_period)] ?? String(r.withdrawal_period)))], path: "request.risk.withdrawal_amount" }));
  }
  if (Array.isArray(r.contribution_rules) && r.contribution_rules.length) {
    rows.push(() => setting(ctx, "allocation", sec(), { key: "contribution_rules", label: t("조건부 납입액 {0}개", (r.contribution_rules as unknown[]).length), rows: [], path: "request.risk.contribution_rules" }));
  }
  if (r.contribution_funding === "cash_pool") {
    const crow = [r.cash_reserve_pct != null ? row(t("현금 하한"), `${r.cash_reserve_pct}%`) : null, r.cash_reserve_amount != null ? row(t("현금 하한"), String(r.cash_reserve_amount)) : null, r.max_buy_cash_pct != null ? row(t("회차 매수 상한"), `${r.max_buy_cash_pct}%`) : null].filter((x): x is DetailRow => x !== null);
    rows.push(() => setting(ctx, "allocation", sec(), { key: "cash_pool", label: t("현금 풀 적립"), rows: crow, path: "request.risk.contribution_funding" }));
  }
  const volTarget = num(r.target_volatility_pct);
  if (volTarget !== null) rows.push(() => setting(ctx, "allocation", sec(), { key: "vol_target", label: t("목표 변동성 {0}%", volTarget), rows: [row(t("목표"), `${volTarget}%`)], path: "request.risk.target_volatility_pct" }));
  if (typeof r.cash_asset === "string" && r.cash_asset) rows.push(() => setting(ctx, "allocation", sec(), { key: "cash_asset", label: t("현금 대용 자산"), rows: [row(t("자산"), r.cash_asset as string)], path: "request.risk.cash_asset" }));
  const taa = r.taa as Record<string, unknown> | null | undefined;
  if (taa && typeof taa === "object") rows.push(() => setting(ctx, "allocation", sec(), { key: "taa", label: t("전술 자산배분 {0}", String(taa.model).toUpperCase()), rows: [], path: "request.risk.taa" }));

  // Pending (confirmed snapshots only): present in the parsed result, absent from the request.
  if (p) {
    if (p.volatility_target && r.target_volatility_pct == null) rows.push(() => pendingNode(ctx, "allocation", sec(), "vol_target", t("목표 변동성")));
    if (p.entry_tranches && r.entry_tranches == null) rows.push(() => pendingNode(ctx, "allocation", sec(), "entry_tranches", t("분할 매수")));
    if (p.position_sizing && r.position_sizing == null) rows.push(() => pendingNode(ctx, "allocation", sec(), "position_sizing", t("포지션 사이징")));
    if (p.cash_pool && r.contribution_funding == null) rows.push(() => pendingNode(ctx, "allocation", sec(), "cash_pool", t("현금 풀 적립")));
    if (p.taa && r.taa == null) rows.push(() => pendingNode(ctx, "allocation", sec(), "taa", t("전술 자산배분")));
  }
  rows.forEach((fn) => fn());
}

const SIZING_LABELS: Record<string, string> = {
  risk_per_trade_pct: "거래당 위험(%)",
  atr_period: "ATR 기간",
  atr_multiple: "ATR 배수",
  kelly_fraction: "켈리 비율",
};

export function buildRebalance(ctx: SectionCtx): void {
  const r = risk(ctx);
  const rawPeriod = typeof r.rebalancing_period === "string" ? r.rebalancing_period : null;
  // The compiler's default is "none": a draft shows it only once the user answered, while any real
  // cadence ("monthly" ...) can only come from the user.
  const period = rawPeriod && (rawPeriod !== "none" || isStated(ctx, "rebalancing")) ? rawPeriod : null;
  const threshold = num(r.rebalance_threshold_pct);
  if (!period && threshold === null) return;
  const sec = section(ctx, "rebalance");
  if (period) {
    const method = typeof r.rebalance_method === "string" ? r.rebalance_method : null;
    const prow = [row(t("주기"), t(REBAL_LABELS[period] ?? period))];
    if (method && period !== "none") prow.push(row(t("방식"), t(REBAL_METHOD_LABELS[method] ?? method)));
    setting(ctx, "rebalance", sec, { key: "period", label: period === "none" ? t("리밸런싱 없음") : t("{0} 리밸런싱", t(REBAL_LABELS[period] ?? period)), rows: prow, path: "request.risk.rebalancing_period" });
  }
  if (threshold !== null) setting(ctx, "rebalance", sec, { key: "threshold", label: t("비중 이탈 {0}%p 시 조정", threshold), rows: [row(t("허용 이탈"), `${threshold}%p`)], path: "request.risk.rebalance_threshold_pct" });
  const minHold = num(r.min_holding_days);
  if (minHold !== null) setting(ctx, "rebalance", sec, { key: "min_hold", label: t("최소 보유 {0}거래일", minHold), rows: [row(t("기준"), t("거래일"))], path: "request.risk.min_holding_days" });
}

const MACRO_ROW_LABELS: Record<string, string> = { role: "역할", series: "시리즈", mode: "방식", operator: "연산자", value: "기준값", period: "기간", exposure_pct: "목표 노출(%)" };

export function buildRisk(ctx: SectionCtx): void {
  const r = risk(ctx);
  const p = ctx.parsed;
  const items: Array<() => void> = [];
  const present = (v: unknown) => v !== null && v !== undefined;
  const disabled = (v: number) => (v === 0 ? [row(t("상태"), t("0 (비활성)"))] : []);

  const sl = num(r.stop_loss_pct);
  if (sl !== null) items.push(() => setting(ctx, "risk", sec(), { key: "stop_loss", kind: "risk", label: t("손절 -{0}%", sl), rows: [row(t("기준가"), t("매수가")), row(t("판정 가격"), t("장중 저가")), ...disabled(sl)], path: "request.risk.stop_loss_pct" }));
  const tp = num(r.take_profit_pct);
  if (tp !== null) items.push(() => setting(ctx, "risk", sec(), { key: "take_profit", kind: "risk", label: t("익절 +{0}%", tp), rows: [row(t("기준가"), t("매수가")), row(t("판정 가격"), t("장중 고가")), ...disabled(tp)], path: "request.risk.take_profit_pct" }));
  const ts = num(r.trailing_stop_pct);
  if (ts !== null) {
    const act = num(r.trailing_stop_activation_pct);
    items.push(() => setting(ctx, "risk", sec(), { key: "trailing", kind: "risk", label: t("트레일링 -{0}%", ts), rows: [row(t("기준가"), t("보유 중 장중 고점")), row(t("판정 가격"), t("장중 저가")), ...(act !== null ? [row(t("작동 조건"), t("고점이 매수가 대비 +{0}% 이상일 때", act))] : []), ...disabled(ts)], path: "request.risk.trailing_stop_pct" }));
  }
  const hold = num(r.max_holding_days);
  const hasExitRule = [sl, tp, ts, hold].some((v) => v !== null);
  const sec = () =>
    section(ctx, "risk", hasExitRule ? [row(t("청산 평가 순서"), t("최대 보유기간 → 손절 → 익절 → 트레일링 (먼저 성립한 항목이 청산 사유가 됩니다)"))] : []);
  if (hold !== null) {
    items.push(() => setting(ctx, "risk", sec(), { key: "max_holding", kind: "risk", label: t("최대 보유 {0}거래일", hold), rows: [row(t("기준"), t("거래일")), ...disabled(hold)], path: "request.risk.max_holding_days" }));
  } else if (p && typeof p.hold_period_days === "number" && p.rebalancing_period && p.rebalancing_period !== "none") {
    const days = p.hold_period_days;
    items.push(() => setting(ctx, "risk", sec(), { key: "max_holding", kind: "risk", label: t("최대 보유 {0}거래일", days), status: "not_applicable", rows: [row(t("기준"), t("거래일"))], note: t("리밸런싱 주기가 있어 보유기간 만료 청산은 실행 요청에서 꺼집니다."), source: "parsed", path: "parsed.hold_period_days" }));
  }
  const mdd = num(r.max_mdd_limit_pct);
  if (mdd !== null) items.push(() => setting(ctx, "risk", sec(), { key: "mdd_limit", kind: "risk", label: t("최대 낙폭 한도 {0}%", mdd), rows: [row(t("한도"), `${mdd}%`)], path: "request.risk.max_mdd_limit_pct" }));
  const cooldown = num(r.stop_cooldown_days);
  if (cooldown !== null) items.push(() => setting(ctx, "risk", sec(), { key: "cooldown", kind: "risk", label: t("손절 후 재진입 금지 {0}거래일", cooldown), rows: [row(t("기준"), t("거래일"))], path: "request.risk.stop_cooldown_days" }));
  const partial = Array.isArray(r.partial_take_profits) ? (r.partial_take_profits as Array<Record<string, unknown>>) : [];
  if (partial.length) items.push(() => setting(ctx, "risk", sec(), { key: "partial_tp", kind: "risk", label: t("분할 익절 {0}단계", partial.length), rows: partial.map((s, i) => row(t("{0}단계", i + 1), t("+{0}%에서 {1}% 매도", s.profit_pct, s.sell_pct))), path: "request.risk.partial_take_profits" }));
  const regime = r.market_regime as Record<string, unknown> | null | undefined;
  if (regime && typeof regime === "object") {
    const rrows: DetailRow[] = [row(t("기준 지수"), String(regime.index ?? ""))];
    if (present(regime.ma_period)) rrows.push(row(t("이동평균 기간"), t("{0}일", regime.ma_period)));
    if (present(regime.volatility_multiple)) rrows.push(row(t("변동성 급등 배수"), `${regime.volatility_multiple}x`));
    if (present(regime.exposure_pct)) rrows.push(row(t("약세 시 목표 노출"), `${regime.exposure_pct}%`));
    items.push(() => setting(ctx, "risk", sec(), { key: "market_regime", label: t("시장 국면 필터"), rows: rrows, path: "request.risk.market_regime" }));
  }
  const macro = Array.isArray(r.macro_filters) ? (r.macro_filters as Array<Record<string, unknown>>) : [];
  macro.forEach((m, i) => {
    items.push(() => setting(ctx, "risk", sec(), { key: `macro_${i}`, label: t("매크로 조건 필터"), rows: Object.entries(m).map(([k, v]) => row(t(MACRO_ROW_LABELS[k] ?? k), String(v))), path: `request.risk.macro_filters[${i}]` }));
  });
  if (Array.isArray(r.seasonal_months) && r.seasonal_months.length) {
    items.push(() => setting(ctx, "risk", sec(), { key: "seasonal", label: t("계절 필터"), rows: [row(t("투자하는 달"), (r.seasonal_months as number[]).join(", "))], path: "request.risk.seasonal_months" }));
  }

  if (p) {
    if (p.market_regime && r.market_regime == null) items.push(() => pendingNode(ctx, "risk", sec(), "market_regime", t("시장 국면 필터")));
    const parsedMacro = p.macro_filters?.length ?? 0;
    if (parsedMacro > macro.length) items.push(() => pendingNode(ctx, "risk", sec(), "macro_filters", t("매크로 조건 필터")));
    const parsedPartial = p.partial_take_profits?.length ?? 0;
    if (parsedPartial > partial.length) items.push(() => pendingNode(ctx, "risk", sec(), "partial_tp", t("분할 익절")));
  }
  items.forEach((fn) => fn());
}

