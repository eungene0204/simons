"use client";

import { useState } from "react";
import { ChartLineUp } from "phosphor-react";

import type { AnalyticsHistogramBin, AnalyticsResult, AnalyticsStat } from "@/types/strategy";
import { formatCompactNumberEn, t } from "@/lib/i18n";

interface Props {
  analytics: AnalyticsResult;
  dates: string[];
  currency?: "krw" | "usd";
}

const POSITIVE = "#ef4444";
const NEGATIVE = "#377af4";

function pct(v: number | null | undefined, digits = 2, signed = true): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function num(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function money(v: number | null | undefined, currency: "krw" | "usd"): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (currency === "usd") return `$${Math.round(v).toLocaleString()}`;
  const compactEn = formatCompactNumberEn(v);
  if (compactEn !== null) return compactEn;
  if (Math.abs(v) >= 1_0000_0000) return t("{0}억", (v / 1_0000_0000).toFixed(1));
  if (Math.abs(v) >= 10_000) return t("{0}만", (v / 10_000).toFixed(0));
  return `${Math.round(v).toLocaleString()}원`;
}

function colorClass(v: number | null | undefined): string {
  if (v == null) return "text-gray-400";
  return v > 0 ? "text-main-red" : v < 0 ? "text-main-blue" : "text-gray-400";
}

function binLabel(bin: AnalyticsHistogramBin): string {
  const unit = bin.unit === "days" ? t("일") : "%";
  if (bin.from == null) return `< ${bin.to}${unit}`;
  if (bin.to == null) return `≥ ${bin.from}${unit}`;
  return `${bin.from}~${bin.to}${unit}`;
}

function Histogram({ bins, color, ariaLabel }: { bins: AnalyticsHistogramBin[]; color: (bin: AnalyticsHistogramBin) => string; ariaLabel: string }) {
  const max = Math.max(1, ...bins.map((b) => b.count));
  const width = 100 / Math.max(1, bins.length);
  return (
    <div>
      <svg viewBox="0 0 100 40" className="h-28 w-full" role="img" aria-label={ariaLabel} preserveAspectRatio="none">
        {bins.map((b, i) => {
          const h = (b.count / max) * 34;
          return <rect key={i} x={i * width + width * 0.1} y={38 - h} width={width * 0.8} height={h} fill={color(b)} opacity={0.85} />;
        })}
      </svg>
      <div className="mt-1 grid text-[9px] font-bold text-gray-500" style={{ gridTemplateColumns: `repeat(${bins.length}, minmax(0, 1fr))` }}>
        {bins.map((b, i) => (
          <span key={i} className="truncate text-center" title={`${binLabel(b)}: ${b.count}`}>{b.count}</span>
        ))}
      </div>
      <div className="grid text-[8px] text-gray-600" style={{ gridTemplateColumns: `repeat(${bins.length}, minmax(0, 1fr))` }}>
        {bins.map((b, i) => (
          <span key={i} className="truncate text-center">{binLabel(b)}</span>
        ))}
      </div>
    </div>
  );
}

function LineSeries({ values, dates, ariaLabel, zero }: { values: Array<number | null>; dates: string[]; ariaLabel: string; zero?: boolean }) {
  const finite = values.filter((v): v is number => v != null && Number.isFinite(v));
  if (finite.length < 2) return <p className="text-xs font-bold text-gray-500">{t("표본이 부족해 그릴 수 없습니다.")}</p>;
  const min = Math.min(...finite, zero ? 0 : Infinity);
  const max = Math.max(...finite, zero ? 0 : -Infinity);
  const span = max - min || 1;
  const n = values.length;
  let d = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v == null || !Number.isFinite(v)) { pen = false; return; }
    const x = (i / Math.max(1, n - 1)) * 100;
    const y = 38 - ((v - min) / span) * 36;
    d += `${pen ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)} `;
    pen = true;
  });
  const zeroY = zero ? 38 - ((0 - min) / span) * 36 : null;
  return (
    <div>
      <svg viewBox="0 0 100 40" className="h-28 w-full" role="img" aria-label={ariaLabel} preserveAspectRatio="none">
        {zeroY != null && <line x1={0} x2={100} y1={zeroY} y2={zeroY} stroke="#525252" strokeWidth={0.3} strokeDasharray="1 1" />}
        <path d={d} fill="none" stroke="#38bdf8" strokeWidth={0.6} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex justify-between text-[9px] font-bold text-gray-600">
        <span>{dates[0]}</span>
        <span>{t("최소 {0} · 최대 {1}", num(min), num(max))}</span>
        <span>{dates[dates.length - 1]}</span>
      </div>
    </div>
  );
}

function StatRow({ label, stat }: { label: string; stat: AnalyticsStat | null }) {
  if (!stat) return null;
  return (
    <tr className="border-t border-white/5">
      <td className="px-2 py-1 text-left text-gray-400">{label}</td>
      <td className="px-2 py-1 text-right">{pct(stat.mean)}</td>
      <td className="px-2 py-1 text-right">{pct(stat.median)}</td>
      <td className="px-2 py-1 text-right">{pct(stat.worst)}</td>
      <td className="px-2 py-1 text-right">{pct(stat.best)}</td>
      <td className="px-2 py-1 text-right text-gray-500">{stat.count}</td>
    </tr>
  );
}

const FACTOR_LABELS: Record<string, string> = { MKT: "시장", SMB: "규모(소형−대형)", HML: "가치(저PBR−고PBR)", MOM: "모멘텀(12-1)" };

export default function AdvancedAnalyticsSection({ analytics, dates, currency = "krw" }: Props) {
  const [open, setOpen] = useState(true);
  const a = analytics;
  const td = a.tradeDistribution;
  const fe = a.factorExposure;

  return (
    <section data-testid="backtest-advanced-analytics" className="border-t border-white/[0.08] p-4 sm:p-5">
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-2 text-left">
        <ChartLineUp className="h-4 w-4 text-gray-400" />
        <h3 className="text-sm font-black text-white">{t("심화 분석 (과거 통계)")}</h3>
        <span className="ml-auto text-[11px] font-bold text-gray-500">{open ? t("접기") : t("펼치기")}</span>
      </button>
      <p className="mt-1 text-[11px] font-bold leading-5 text-gray-500">
        {t("아래 값은 이 백테스트의 과거 데이터에서 계산한 기술 통계입니다. 미래 수익을 예측하거나 전략을 추천하지 않습니다.")}
      </p>
      {open && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {/* 회전율·위험 */}
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid="analytics-risk">
            <div className="text-[11px] font-black uppercase tracking-widest text-gray-500">{t("회전율·꼬리 위험")}</div>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-bold text-gray-200 sm:grid-cols-3">
              <dt className="text-gray-500">{t("연환산 회전율")}</dt><dd>{pct(a.turnover.annual, 0, false)}</dd>
              <dt className="text-gray-500">{t("기간 회전율")}</dt><dd>{pct(a.turnover.total, 0, false)}</dd>
              <dt className="text-gray-500">VaR 95%</dt><dd>{pct(a.riskStats.var95, 2, false)}</dd>
              <dt className="text-gray-500">CVaR 95%</dt><dd>{pct(a.riskStats.cvar95, 2, false)}</dd>
              <dt className="text-gray-500">VaR 99%</dt><dd>{pct(a.riskStats.var99, 2, false)}</dd>
              <dt className="text-gray-500">CVaR 99%</dt><dd>{pct(a.riskStats.cvar99, 2, false)}</dd>
            </dl>
            <p className="mt-1 text-[10px] text-gray-600">{t("VaR·CVaR는 일간 수익률의 역사적 분포에서 구한 하루 손실 한도(%)입니다.")}</p>
            <div className="mt-3 text-[10px] font-black uppercase tracking-widest text-gray-500">{t("{0}거래일 롤링 샤프", a.riskStats.window)}</div>
            <LineSeries values={a.riskStats.rollingSharpe} dates={dates} ariaLabel={t("롤링 샤프")} zero />
            {a.riskStats.rollingBeta.length > 0 && (
              <>
                <div className="mt-3 text-[10px] font-black uppercase tracking-widest text-gray-500">{t("{0}거래일 롤링 베타 (벤치마크 대비)", a.riskStats.window)}</div>
                <LineSeries values={a.riskStats.rollingBeta} dates={dates} ariaLabel={t("롤링 베타")} zero />
              </>
            )}
          </div>

          {/* 귀인 */}
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid="analytics-attribution">
            <div className="text-[11px] font-black uppercase tracking-widest text-gray-500">{t("성과 귀인 (초기 자본 대비 기여도)")}</div>
            {a.attribution.symbols.length === 0 ? (
              <p className="mt-2 text-xs font-bold text-gray-500">{t("완결된 거래가 없어 기여도를 계산하지 못했습니다.")}</p>
            ) : (
              <>
                <table className="mt-2 w-full text-xs font-bold text-gray-200">
                  <thead className="text-[10px] uppercase tracking-widest text-gray-500">
                    <tr><th className="px-2 py-1 text-left">{t("종목")}</th><th className="px-2 py-1 text-left">{t("섹터")}</th><th className="px-2 py-1 text-right">{t("손익")}</th><th className="px-2 py-1 text-right">{t("기여도")}</th></tr>
                  </thead>
                  <tbody>
                    {a.attribution.symbols.map((r) => (
                      <tr key={r.symbol} className="border-t border-white/5">
                        <td className="px-2 py-1">{r.name} <span className="text-gray-500">{r.symbol}</span></td>
                        <td className="px-2 py-1 text-gray-400">{r.sector}</td>
                        <td className={`px-2 py-1 text-right ${colorClass(r.pnl)}`}>{money(r.pnl, currency)}</td>
                        <td className={`px-2 py-1 text-right ${colorClass(r.contributionPct)}`}>{pct(r.contributionPct)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="mt-3 text-[10px] font-black uppercase tracking-widest text-gray-500">{t("섹터별 기여도")}</div>
                <ul className="mt-1 space-y-0.5 text-xs font-bold text-gray-300">
                  {a.attribution.sectors.slice(0, 8).map((s) => (
                    <li key={s.sector} className="flex justify-between"><span>{s.sector} <span className="text-gray-600">({s.symbols})</span></span><span className={colorClass(s.contributionPct)}>{pct(s.contributionPct)}</span></li>
                  ))}
                </ul>
              </>
            )}
          </div>

          {/* 팩터 노출 */}
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid="analytics-factor">
            <div className="text-[11px] font-black uppercase tracking-widest text-gray-500">{t("팩터 노출 (유니버스 내 팩터 회귀)")}</div>
            {!fe.available ? (
              <p className="mt-2 text-xs font-bold text-gray-500">
                {fe.reason === "universe_too_small"
                  ? t("유니버스가 {0}종목이라 팩터 포트폴리오를 만들 수 없습니다(최소 {1}종목).", fe.symbols ?? 0, fe.minSymbols ?? 30)
                  : fe.reason === "too_few_observations"
                    ? t("관측이 {0}일로 부족합니다(최소 60일).", fe.observations ?? 0)
                    : t("팩터 자료(시가총액·PBR·모멘텀)가 없어 계산하지 못했습니다.")}
              </p>
            ) : (
              <>
                <table className="mt-2 w-full text-xs font-bold text-gray-200">
                  <thead className="text-[10px] uppercase tracking-widest text-gray-500">
                    <tr><th className="px-2 py-1 text-left">{t("팩터")}</th><th className="px-2 py-1 text-right">{t("베타")}</th><th className="px-2 py-1 text-right">t</th></tr>
                  </thead>
                  <tbody>
                    {(fe.loadings ?? []).map((l) => (
                      <tr key={l.factor} className="border-t border-white/5">
                        <td className="px-2 py-1">{t(FACTOR_LABELS[l.factor] ?? l.factor)}</td>
                        <td className={`px-2 py-1 text-right ${colorClass(l.beta)}`}>{num(l.beta)}</td>
                        <td className="px-2 py-1 text-right text-gray-400">{num(l.tStat, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-2 text-[11px] font-bold text-gray-400">
                  {t("알파(연환산) {0} (t={1}) · R² {2} · 관측 {3}일 · 유니버스 {4}종목", pct(fe.alphaAnnualPct), num(fe.alphaTStat, 1), num(fe.r2), fe.observations ?? 0, fe.symbols ?? 0)}
                </p>
                <p className="mt-1 text-[10px] text-gray-600">{t("팩터 포트폴리오는 이 백테스트 유니버스 안에서 매월 상·하위 30%를 롱·숏한 균등 수익률입니다(Fama-French 공식 팩터가 아닙니다).")}</p>
              </>
            )}
          </div>

          {/* 거래 분포 */}
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid="analytics-trades">
            <div className="text-[11px] font-black uppercase tracking-widest text-gray-500">{t("거래 분포 ({0}건)", td.trades)}</div>
            {td.trades === 0 ? (
              <p className="mt-2 text-xs font-bold text-gray-500">{t("완결된 거래가 없습니다.")}</p>
            ) : (
              <>
                <div className="mt-2 text-[10px] font-bold text-gray-500">{t("거래 수익률 분포")}</div>
                <Histogram bins={td.returnHistogram} ariaLabel={t("거래 수익률 분포")} color={(b) => ((b.from ?? -1) >= 0 ? POSITIVE : NEGATIVE)} />
                <div className="mt-3 text-[10px] font-bold text-gray-500">
                  {t("보유 기간 분포")}{td.holdingDays ? ` · ${t("평균 {0}일 · 중앙값 {1}일 · 최장 {2}일", num(td.holdingDays.mean, 0), num(td.holdingDays.median, 0), td.holdingDays.max)}` : ""}
                </div>
                <Histogram bins={td.holdingHistogram} ariaLabel={t("보유 기간 분포")} color={() => "#a3a3a3"} />
                <table className="mt-3 w-full text-xs font-bold text-gray-200">
                  <thead className="text-[10px] uppercase tracking-widest text-gray-500">
                    <tr><th className="px-2 py-1 text-left">MAE/MFE</th><th className="px-2 py-1 text-right">{t("평균")}</th><th className="px-2 py-1 text-right">{t("중앙값")}</th><th className="px-2 py-1 text-right">{t("최악")}</th><th className="px-2 py-1 text-right">{t("최선")}</th><th className="px-2 py-1 text-right">n</th></tr>
                  </thead>
                  <tbody>
                    <StatRow label={t("MAE 전체")} stat={td.mae?.all ?? null} />
                    <StatRow label={t("MAE 승리")} stat={td.mae?.winners ?? null} />
                    <StatRow label={t("MAE 패배")} stat={td.mae?.losers ?? null} />
                    <StatRow label={t("MFE 전체")} stat={td.mfe?.all ?? null} />
                    <StatRow label={t("MFE 승리")} stat={td.mfe?.winners ?? null} />
                    <StatRow label={t("MFE 패배")} stat={td.mfe?.losers ?? null} />
                  </tbody>
                </table>
                <p className="mt-1 text-[10px] text-gray-600">{t("MAE=보유 중 진입가 대비 최저 도달률, MFE=최고 도달률. 손절·익절 폭을 과거 거래와 견줄 때 씁니다.")}</p>
              </>
            )}
          </div>

          {/* 유동성 */}
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid="analytics-liquidity">
            <div className="text-[11px] font-black uppercase tracking-widest text-gray-500">{t("유동성 (주문금액 ÷ 20일 평균 거래대금)")}</div>
            {a.liquidity.orders === 0 || a.liquidity.maxParticipation == null ? (
              <p className="mt-2 text-xs font-bold text-gray-500">{t("거래대금 자료가 없어 참여율을 계산하지 못했습니다.")}</p>
            ) : (
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-bold text-gray-200">
                <dt className="text-gray-500">{t("주문 수")}</dt><dd>{a.liquidity.orders}</dd>
                <dt className="text-gray-500">{t("최대 참여율")}</dt><dd>{pct(a.liquidity.maxParticipation, 2, false)}</dd>
                <dt className="text-gray-500">{t("평균 참여율")}</dt><dd>{pct(a.liquidity.meanParticipation, 2, false)}</dd>
                <dt className="text-gray-500">{t("상위 5% 참여율")}</dt><dd>{pct(a.liquidity.p95Participation, 2, false)}</dd>
                <dt className="text-gray-500">{t("참여율 {0}% 초과 주문 비율", a.liquidity.cap)}</dt><dd>{pct(a.liquidity.shareAboveCap, 1, false)}</dd>
                <dt className="text-gray-500">{t("참여율 {0}% 이내 운용 가능 자본(추정)", a.liquidity.cap)}</dt><dd>{money(a.liquidity.capitalAtCap, currency)}</dd>
              </dl>
            )}
          </div>

          {/* 벤치마크 비교 */}
          <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4" data-testid="analytics-benchmarks">
            <div className="text-[11px] font-black uppercase tracking-widest text-gray-500">{t("다중 벤치마크 비교")}</div>
            {a.benchmarks.length === 0 ? (
              <p className="mt-2 text-xs font-bold text-gray-500">{t("벤치마크 자료가 없습니다.")}</p>
            ) : (
              <table className="mt-2 w-full text-xs font-bold text-gray-200">
                <thead className="text-[10px] uppercase tracking-widest text-gray-500">
                  <tr><th className="px-2 py-1 text-left">{t("벤치마크")}</th><th className="px-2 py-1 text-right">{t("총수익률")}</th><th className="px-2 py-1 text-right">CAGR</th><th className="px-2 py-1 text-right">MDD</th><th className="px-2 py-1 text-right">β</th><th className="px-2 py-1 text-right">α</th><th className="px-2 py-1 text-right">IR</th></tr>
                </thead>
                <tbody>
                  {a.benchmarks.map((b) => (
                    <tr key={b.symbol} className="border-t border-white/5">
                      <td className="px-2 py-1">{b.name}{b.partial ? <span className="ml-1 text-[9px] text-amber-300">{t("일부 기간")}</span> : null}</td>
                      <td className={`px-2 py-1 text-right ${colorClass(b.totalReturn)}`}>{pct(b.totalReturn)}</td>
                      <td className={`px-2 py-1 text-right ${colorClass(b.cagr)}`}>{pct(b.cagr)}</td>
                      <td className="px-2 py-1 text-right text-main-blue">{pct(b.maxDrawdown)}</td>
                      <td className="px-2 py-1 text-right">{num(b.beta)}</td>
                      <td className={`px-2 py-1 text-right ${colorClass(b.alpha)}`}>{pct(b.alpha)}</td>
                      <td className="px-2 py-1 text-right">{num(b.informationRatio)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="mt-1 text-[10px] text-gray-600">{t("β·α·정보비율은 전략 일간 수익률을 각 벤치마크에 회귀한 값입니다.")}</p>
          </div>
        </div>
      )}
    </section>
  );
}
