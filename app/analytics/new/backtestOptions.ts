/**
 * 백테스트 설정 패널(BacktestConfig)과 엔진 요청 사이의 기간 표현을 맞춘다.
 *
 * 두 표현이 서로 다른 어휘를 쓴다 — 엔진 요청은 소문자 상대 기간(`"5y"`)과 명시 창
 * (`startDate`/`endDate`)을 **함께** 실을 수 있고, 패널은 대문자 id(`"5Y"`) 하나로
 * 고른다. 그대로 이으면 두 방향 모두 어긋난다(2026-08-01 정리):
 *
 *   ① 표시 — 명시 창(2016~2026)으로 파싱된 전략이 패널에 `"5y"`로 넘어가 **어느 버튼도
 *      선택되지 않고**, 실제로 실행될 창이 화면 어디에도 없었다.
 *   ② 권위 — 패널에서 기간을 바꿔도 요청에 남은 이전 명시 창이 그대로 실려 나갔다.
 *      엔진은 `startDate`를 상대 기간보다 우선하므로(`backtest_engine`), 사용자가 방금
 *      고른 기간이 조용히 무시된다.
 *
 * 규칙은 하나다 — **화면에 보이는 기간이 곧 실행되는 창이다.**
 */

export interface BacktestCostOptions {
  fee_rate?: number | null;
  slippage_rate?: number | null;
  // 사용자가 말한 때만 실린다 — 없으면 엔진이 시행일 기준 법정 세율을 쓴다.
  sell_tax_rate?: number | null;
}

export interface BacktestWindowRequest {
  period?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  // 파싱이 실은 거래 비용(소수 비율). 사용자가 "수수료 0.1%"처럼 말한 값이 여기 있다.
  options?: BacktestCostOptions | null;
  risk?: { init_cash?: number | null } | null;
}

export interface RunOptions {
  period: string;
  startDate?: string;
  endDate?: string;
  initialCapital?: number;
  commissionPct?: number;
  slippagePct?: number;
}

/** 패널이 버튼으로 표현할 수 있는 기간 id. 파싱 정본 버킷(1y/3y/5y/full)을 모두 포함한다. */
export const PANEL_PERIOD_IDS = ["6M", "1Y", "3Y", "5Y", "10Y", "20Y", "full"] as const;

export const CUSTOM_PERIOD_ID = "custom";

// 패널 표기(%)의 기본 거래 비용 — 백엔드 ParsedStrategy 기본값(0.015%·0.05%)과 같다.
export const DEFAULT_COMMISSION_PCT = 0.015;
export const DEFAULT_SLIPPAGE_PCT = 0.05;

const rateToPct = (rate: number | null | undefined): number | undefined =>
  rate == null ? undefined : rate * 100;

/**
 * 실행 요청에 실을 거래 비용. 패널에서 고친 값이 있으면 그것, 없으면 **요청이 이미 싣고
 * 있던 값**, 그것도 없으면 기본값이다 — 종전에는 패널 값이 없을 때 곧장 기본값으로
 * 떨어져 사용자가 문장으로 요청한 수수료·슬리피지가 재실행에서 조용히 사라졌다(2026-09-14).
 */
export function applyRunCosts(
  request: BacktestWindowRequest | null | undefined,
  options: Pick<RunOptions, "commissionPct" | "slippagePct"> | null | undefined,
): BacktestCostOptions {
  const requested = request?.options ?? {};
  return {
    ...requested,
    fee_rate:
      options?.commissionPct != null
        ? options.commissionPct / 100
        : requested.fee_rate ?? DEFAULT_COMMISSION_PCT / 100,
    slippage_rate:
      options?.slippagePct != null
        ? options.slippagePct / 100
        : requested.slippage_rate ?? DEFAULT_SLIPPAGE_PCT / 100,
  };
}

/** 엔진 요청의 period 표기를 패널 id로 맞춘다. 대응하는 버튼이 없으면 null. */
export function toPanelPeriodId(period: string | null | undefined): string | null {
  if (!period) return null;
  const normalized = String(period).trim();
  if (normalized.toLowerCase() === "full") return "full";
  const upper = normalized.toUpperCase();
  return (PANEL_PERIOD_IDS as readonly string[]).includes(upper) ? upper : null;
}

/**
 * 실행 요청에서 설정 패널의 초기값을 만든다.
 * 명시 창이 있으면 '직접 입력'으로 열어 그 창을 그대로 보여준다 — 상대 기간 라벨을
 * 보여주면 화면과 실행이 어긋난다(엔진은 명시 창을 우선한다).
 */
export function backtestConfigOptions(
  request: BacktestWindowRequest | null | undefined,
): RunOptions {
  const startDate = request?.startDate ?? undefined;
  const endDate = request?.endDate ?? undefined;
  const base = {
    initialCapital: request?.risk?.init_cash ?? 10000000,
    // 요청이 실은 비용을 패널에 그대로 보인다 — 화면에 보이는 값이 곧 실행되는 값이다.
    commissionPct: rateToPct(request?.options?.fee_rate) ?? DEFAULT_COMMISSION_PCT,
    slippagePct: rateToPct(request?.options?.slippage_rate) ?? DEFAULT_SLIPPAGE_PCT,
  };
  if (startDate || endDate) {
    return { period: CUSTOM_PERIOD_ID, startDate, endDate, ...base };
  }
  return { period: toPanelPeriodId(request?.period) ?? "5Y", ...base };
}

/**
 * 패널에서 고른 기간을 실행 요청에 반영한다.
 * '직접 입력'이면 그 창을 싣고, 상대 기간이면 **이전 명시 창을 떼어낸다** — 남기면
 * 엔진이 날짜를 우선해 방금 고른 기간이 무시된다.
 */
export function applyRunWindow<T extends BacktestWindowRequest>(
  request: T,
  options: RunOptions,
): T {
  if (options.period === CUSTOM_PERIOD_ID) {
    return {
      ...request,
      period: CUSTOM_PERIOD_ID,
      startDate: options.startDate ?? request.startDate ?? null,
      endDate: options.endDate ?? request.endDate ?? null,
    };
  }
  const { startDate: _dropStart, endDate: _dropEnd, ...rest } = request;
  return { ...rest, period: options.period ?? request.period } as T;
}
