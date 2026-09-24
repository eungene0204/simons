"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Funnel, ArrowClockwise } from "phosphor-react";

import { t } from "@/lib/i18n";
import { useRegionHref } from "@/lib/geo/useRegion";
import { tradeReasonText } from "@/lib/trade-reason";

// 독립 스크리너 — 저장된 전략의 조건을 **오늘 데이터**에 적용한 결과를 본다(엔진 v16.33).
// 백테스트가 과거를 계산한다면 이 화면은 같은 조건을 최신 봉에 한 번 적용한다. 판정 정본은
// 백엔드(engine/screener.py)이며 자동매매와 같은 평가기다 — 화면마다 조건 해석이 갈리면
// 같은 전략이 자리마다 다른 종목을 고른다.
// UI_GUIDELINES §12 그리드 테이블(행 보더 금지, divide + hover), flat 패널.
const GRID_COLS = "grid-cols-[minmax(0,1.4fr)_120px_100px_120px_minmax(0,1fr)]";
const HEADER_CLASS = "text-xs font-bold uppercase tracking-widest text-[var(--text-label)]";

interface StrategyOption {
  id: string;
  name: string;
  universe: string;
}

interface ScreenerRow {
  symbol: string;
  name: string;
  sector: string;
  close: number | null;
  changePct: number | null;
  tradingValue: number | null;
  date: string | null;
  rankValue: number | null;
  rankingReturnPct: number | null;
  condition: string | null;
  conditionParts: Array<Record<string, unknown>> | null;
}

interface ScreenerResult {
  asOf: string | null;
  scanned: number;
  matched: number;
  truncated: boolean;
  rankingMetric: string | null;
  rankingDirection: string | null;
  rows: ScreenerRow[];
  reason?: string;
}

function directionClass(value: number | null): string {
  if (value == null) return "text-gray-400";
  if (value > 0) return "text-[var(--main-red)]";
  if (value < 0) return "text-[var(--main-blue)]";
  return "text-white";
}

function formatPrice(value: number | null): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("ko-KR").format(Math.round(value));
}

function formatPct(value: number | null): string {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatTradingValue(value: number | null): string {
  if (value == null) return "—";
  if (value >= 1_0000_0000) return t("{0}억", (value / 1_0000_0000).toFixed(1));
  if (value >= 10_000) return t("{0}만", Math.round(value / 10_000).toLocaleString());
  return new Intl.NumberFormat("ko-KR").format(Math.round(value));
}

export default function StrategyScreener() {
  const router = useRouter();
  const regionHref = useRegionHref();
  const [strategies, setStrategies] = useState<StrategyOption[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [result, setResult] = useState<ScreenerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/dashboard/strategy-list", { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const data = await res.json();
        if (cancelled) return;
        const items: StrategyOption[] = (data.strategies ?? []).map((s: StrategyOption) => ({
          id: s.id,
          name: s.name,
          universe: s.universe,
        }));
        setStrategies(items);
        if (items.length > 0) setSelectedId(items[0].id);
      } catch {
        if (!cancelled) setError(t("전략 목록을 불러오지 못했습니다."));
      } finally {
        if (!cancelled) setListLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const runScreen = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const detail = await fetch(`/api/strategy/${selectedId}`, { cache: "no-store" });
      if (!detail.ok) throw new Error(t("전략을 불러오지 못했습니다."));
      const strategy = await detail.json();
      if (!strategy?.settings) throw new Error(t("이 전략에는 실행할 조건이 저장돼 있지 않습니다."));
      const res = await fetch("/api/screener", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy: strategy.settings, limit: 100 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? t("스크리너 실행에 실패했습니다."));
      setResult(data as ScreenerResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("스크리너 실행에 실패했습니다."));
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  const header = (
    <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
      <div className="flex items-center gap-2">
        <Funnel size={20} weight="fill" className="text-white" />
        <h1 className="text-base font-black text-white font-outfit">{t("전략 스크리너")}</h1>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          disabled={listLoading || strategies.length === 0}
          className="max-w-[260px] rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-sm font-bold text-white"
          aria-label={t("전략 선택")}
        >
          {strategies.length === 0 ? (
            <option value="">{t("저장된 전략이 없습니다")}</option>
          ) : (
            strategies.map((s) => (
              <option key={s.id} value={s.id} className="bg-[var(--bg-base)]">
                {s.name}
              </option>
            ))
          )}
        </select>
        <button
          type="button"
          onClick={runScreen}
          disabled={loading || !selectedId}
          className="flex items-center gap-2 rounded-xl bg-[var(--chat-accent)] px-4 py-2 text-sm font-black text-[var(--chat-accent-ink)] transition-colors hover:brightness-110 active:translate-y-[1px] disabled:opacity-50"
        >
          <ArrowClockwise size={16} weight="bold" />
          {loading ? t("검색 중…") : t("조건 검색")}
        </button>
      </div>
    </div>
  );

  return (
    <div className="w-full min-w-0 border border-white/[0.08]">
      <div className="divide-y divide-white/[0.08]">
        {header}

        <div className="px-5 py-3">
          <p className="text-xs font-bold text-gray-500">
            {t(
              "저장된 전략의 매수 조건을 최신 시세·재무 데이터에 그대로 적용한 계산 결과입니다. 과거·현재 데이터의 조건 충족 여부일 뿐이며 투자 추천이 아닙니다.",
            )}
          </p>
        </div>

        {error ? (
          <div className="px-5 py-6">
            <p className="text-sm font-bold text-[var(--main-blue)]">{error}</p>
          </div>
        ) : null}

        {loading ? (
          <div className="space-y-2 p-5 animate-pulse motion-reduce:animate-none">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 rounded-xl bg-white/[0.04]" />
            ))}
          </div>
        ) : null}

        {result && !loading ? (
          <>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1 px-5 py-3 text-xs font-bold text-gray-400">
              <span>{t("기준일 {0}", result.asOf ?? "—")}</span>
              <span>{t("검색 대상 {0}종목", result.scanned.toLocaleString())}</span>
              <span className="text-white">{t("조건 충족 {0}종목", result.matched.toLocaleString())}</span>
              {result.truncated ? <span>{t("상위 {0}개만 표시", result.rows.length)}</span> : null}
            </div>

            <div className="overflow-x-auto p-3">
              <div className="min-w-[720px]">
                <div className={`grid ${GRID_COLS} gap-2 px-2 mb-2`}>
                  <span className={HEADER_CLASS}>{t("종목")}</span>
                  <span className={`${HEADER_CLASS} text-right`}>{t("종가")}</span>
                  <span className={`${HEADER_CLASS} text-right`}>{t("등락률")}</span>
                  <span className={`${HEADER_CLASS} text-right`}>{t("거래대금")}</span>
                  <span className={HEADER_CLASS}>{t("충족 조건")}</span>
                </div>
                <div className="border-t border-white/[0.05] mb-1" />

                {result.rows.length === 0 ? (
                  <div className="px-2 py-10 text-center">
                    <p className="text-sm font-bold text-gray-400">
                      {result.reason === "no_buy_criteria"
                        ? t("이 전략에는 종목을 고르는 기준(매수 조건·랭킹)이 없습니다.")
                        : result.reason === "empty_universe"
                          ? t("이 전략의 유니버스에서 검색할 종목을 찾지 못했습니다.")
                          : t("오늘 조건을 충족한 종목이 없습니다.")}
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-white/[0.04]">
                    {result.rows.map((row) => (
                      <div
                        key={row.symbol}
                        role="link"
                        tabIndex={0}
                        onClick={() => router.push(regionHref(`/stock/${row.symbol}`))}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            router.push(regionHref(`/stock/${row.symbol}`));
                          }
                        }}
                        className={`grid ${GRID_COLS} items-center gap-2 rounded-xl px-2 py-3 transition-colors duration-150 hover:bg-white/[0.02] cursor-pointer`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-bold text-white">{row.name}</p>
                          <p className="truncate text-[11px] font-bold text-gray-500">
                            {row.symbol} · {row.sector}
                          </p>
                        </div>
                        <span className="text-right text-sm font-bold text-white">{formatPrice(row.close)}</span>
                        <span className={`text-right text-sm font-bold ${directionClass(row.changePct)}`}>
                          {formatPct(row.changePct)}
                        </span>
                        <span className="text-right text-sm font-bold text-gray-300">
                          {formatTradingValue(row.tradingValue)}
                        </span>
                        <span className="truncate text-xs font-bold text-gray-400">
                          {tradeReasonText(row.condition, row.conditionParts, (v) =>
                            new Intl.NumberFormat("ko-KR").format(Math.round(v)),
                          ) || "—"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        ) : null}

        {!result && !loading && !error ? (
          <div className="px-5 py-10 text-center">
            <p className="text-sm font-bold text-gray-400">
              {strategies.length === 0
                ? t("먼저 전략을 만들어 저장하면 그 조건으로 종목을 검색할 수 있습니다.")
                : t("전략을 고르고 '조건 검색'을 누르면 오늘 조건을 충족하는 종목을 보여 줍니다.")}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
