/**
 * 다중 전략 결합(엔진 외 계산, 2026-09-23) — 저장된 백테스트 결과 여러 개의 자산곡선을 비중으로 섞어
 * 결합 포트폴리오의 자산곡선·통계·전략 간 상관을 구한다. 순수 함수(결정론)라 검증 페이지가 그 자리에서 계산한다.
 *
 * 규약
 * - 날짜는 교집합(모든 전략에 값이 있는 거래일)만 쓴다. 각 곡선은 첫 교집합 날 1.0으로 정규화한다.
 * - 리밸런싱 'none'은 첫날 비중대로 사서 들고 가는 것(드리프트), 그 밖은 해당 달력 주기의 첫 거래일마다
 *   목표 비중으로 되돌린다(거래 비용 없음 — 각 전략의 자산곡선에 이미 비용이 들어 있다).
 * - 연환산은 결과 화면과 같은 246거래일, 낙폭은 초기값 1.0을 기준점에 포함한다.
 */

export type CombineRebalance = "none" | "monthly" | "quarterly" | "yearly";

export interface CombineInput {
  id: string;
  name: string;
  dates: string[];
  equity: number[];
  weight: number; // 비중 % (합이 100이 아니면 정규화)
}

export interface CombineStats {
  totalReturn: number; // %
  cagr: number; // %
  maxDrawdown: number; // % (음수)
  volatility: number; // % 연환산
  sharpe: number;
  calmar: number | null;
}

export interface CombineResult {
  dates: string[];
  combined: number[]; // 정규화 자산곡선(1.0 시작)
  components: Array<{ id: string; name: string; weight: number; curve: number[]; stats: CombineStats }>;
  stats: CombineStats;
  correlation: number[][]; // 일수익률 피어슨 상관(성분 순서)
  rebalance: CombineRebalance;
  rebalanceCount: number;
}

export const COMBINE_TRADING_DAYS = 246;

function periodKey(date: string, rebalance: CombineRebalance): string {
  if (rebalance === "monthly") return date.slice(0, 7);
  if (rebalance === "yearly") return date.slice(0, 4);
  if (rebalance === "quarterly") {
    const month = Number(date.slice(5, 7));
    return `${date.slice(0, 4)}-Q${Math.ceil(month / 3)}`;
  }
  return "";
}

export function combineStats(curve: number[], dates: string[]): CombineStats {
  const n = curve.length;
  if (n === 0) return { totalReturn: 0, cagr: 0, maxDrawdown: 0, volatility: 0, sharpe: 0, calmar: null };
  const last = curve[n - 1];
  const totalReturn = (last - 1) * 100;
  const first = Date.parse(dates[0]);
  const end = Date.parse(dates[n - 1]);
  const years = Number.isFinite(first) && Number.isFinite(end) && end > first
    ? (end - first) / 86_400_000 / 365.25
    : Math.max(1e-6, n / COMBINE_TRADING_DAYS);
  const cagr = years > 0 && last > 0 ? (Math.pow(last, 1 / years) - 1) * 100 : 0;
  let peak = 1;
  let mdd = 0;
  for (const v of curve) {
    if (v > peak) peak = v;
    const dd = v / peak - 1;
    if (dd < mdd) mdd = dd;
  }
  const rets: number[] = [];
  let prev = 1;
  for (const v of curve) {
    rets.push(v / prev - 1);
    prev = v;
  }
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const variance = rets.length > 1 ? rets.reduce((a, r) => a + (r - mean) ** 2, 0) / (rets.length - 1) : 0;
  const std = Math.sqrt(variance);
  const volatility = std * Math.sqrt(COMBINE_TRADING_DAYS) * 100;
  const sharpe = std > 0 ? (mean / std) * Math.sqrt(COMBINE_TRADING_DAYS) : 0;
  const calmar = mdd < 0 ? cagr / Math.abs(mdd * 100) : null;
  return { totalReturn, cagr, maxDrawdown: mdd * 100, volatility, sharpe, calmar };
}

function pearson(a: number[], b: number[]): number {
  const n = Math.min(a.length, b.length);
  if (n < 2) return 0;
  const ma = a.slice(0, n).reduce((x, y) => x + y, 0) / n;
  const mb = b.slice(0, n).reduce((x, y) => x + y, 0) / n;
  let sab = 0;
  let saa = 0;
  let sbb = 0;
  for (let i = 0; i < n; i += 1) {
    const da = a[i] - ma;
    const db = b[i] - mb;
    sab += da * db;
    saa += da * da;
    sbb += db * db;
  }
  return saa > 0 && sbb > 0 ? sab / Math.sqrt(saa * sbb) : 0;
}

export function combineStrategies(inputs: CombineInput[], rebalance: CombineRebalance): CombineResult {
  const valid = inputs.filter((c) => c.dates.length > 1 && c.equity.length === c.dates.length);
  if (valid.length === 0) {
    throw new Error("결합할 자산곡선이 없습니다");
  }
  const totalWeight = valid.reduce((s, c) => s + Math.max(0, c.weight), 0);
  if (totalWeight <= 0) {
    throw new Error("비중 합이 0입니다");
  }
  const weights = valid.map((c) => Math.max(0, c.weight) / totalWeight);

  // 날짜 교집합
  let common = new Set(valid[0].dates);
  for (const c of valid.slice(1)) {
    const own = new Set(c.dates);
    common = new Set([...common].filter((d) => own.has(d)));
  }
  const dates = valid[0].dates.filter((d) => common.has(d));
  if (dates.length < 2) {
    throw new Error("전략들이 공통으로 가진 거래일이 2일 미만입니다");
  }
  const curves = valid.map((c) => {
    const byDate = new Map<string, number>();
    c.dates.forEach((d, i) => byDate.set(d, c.equity[i]));
    const base = byDate.get(dates[0]) as number;
    return dates.map((d) => (byDate.get(d) as number) / (base > 0 ? base : 1));
  });

  // 결합: 각 성분의 보유 금액을 추적, 리밸런싱일에 목표 비중으로 리셋
  const holdings = weights.slice();
  const combined: number[] = [];
  let rebalanceCount = 0;
  let lastKey = periodKey(dates[0], rebalance);
  for (let i = 0; i < dates.length; i += 1) {
    if (i > 0) {
      for (let k = 0; k < holdings.length; k += 1) {
        const growth = curves[k][i - 1] > 0 ? curves[k][i] / curves[k][i - 1] : 1;
        holdings[k] *= growth;
      }
      const key = periodKey(dates[i], rebalance);
      if (rebalance !== "none" && key !== lastKey) {
        const nav = holdings.reduce((s, h) => s + h, 0);
        for (let k = 0; k < holdings.length; k += 1) holdings[k] = nav * weights[k];
        rebalanceCount += 1;
        lastKey = key;
      }
    }
    combined.push(holdings.reduce((s, h) => s + h, 0));
  }

  const dailyReturns = curves.map((curve) => curve.slice(1).map((v, i) => (curve[i] > 0 ? v / curve[i] - 1 : 0)));
  const correlation = dailyReturns.map((a) => dailyReturns.map((b) => pearson(a, b)));

  return {
    dates,
    combined,
    components: valid.map((c, k) => ({
      id: c.id,
      name: c.name,
      weight: weights[k] * 100,
      curve: curves[k],
      stats: combineStats(curves[k], dates),
    })),
    stats: combineStats(combined, dates),
    correlation,
    rebalance,
    rebalanceCount,
  };
}
