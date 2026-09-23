// 티어시트(HTML) 생성 — 백테스트 결과를 한 장의 독립 HTML 문서로 만든다(순수 함수, 서버·클라이언트 공용).
//
// 원칙
// - 외부 자원 없이 열린다(인라인 CSS·SVG). 브라우저 인쇄(Ctrl/Cmd+P)로 PDF 저장 — 문서 안에 인쇄 버튼과 @media print 규칙을 둔다.
// - 표시 문구는 t()를 거쳐 /us에서는 영어로 나간다.
// - 값은 과거 데이터의 통계이며 예측·추천 문구를 쓰지 않는다(규제 안전 원칙).

import { t } from "@/lib/i18n";

export interface TearsheetMetric { label: string; value: string }
export interface TearsheetSection { title: string; rows: Array<Array<string>>; header?: string[] }

export interface TearsheetPayload {
  strategyName: string;
  generatedAt: string;
  period: { from: string; to: string };
  universe: string;
  currency: "KRW" | "USD";
  initialCapital: number;
  finalEquity: number;
  /** 상단 핵심 지표(라벨·표시값) */
  metrics: TearsheetMetric[];
  /** 전략 조건 요약 줄 */
  summaryLines: string[];
  /** 자산곡선(정규화 전 금액)·날짜·벤치마크(선택) */
  dates: string[];
  equity: number[];
  benchmarkEquity?: Array<number | null>;
  /** 월별 수익률(YYYY-MM → %) */
  monthlyReturns?: Record<string, number>;
  /** 추가 표(심화 분석·종목 분석 등) */
  sections: TearsheetSection[];
  /** 결과 경고 */
  warnings: string[];
}

function esc(s: unknown): string {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fmtMoney(v: number, currency: "KRW" | "USD"): string {
  if (!Number.isFinite(v)) return "—";
  return currency === "USD" ? `$${Math.round(v).toLocaleString()}` : `${Math.round(v).toLocaleString()}원`;
}

/** 자산곡선 + 낙폭 SVG(인라인). 벤치마크는 있으면 회색 선. */
export function equitySvg(dates: string[], equity: number[], benchmark?: Array<number | null>): string {
  const n = equity.length;
  if (n < 2) return "";
  const w = 900;
  const h = 260;
  const pad = 36;
  const all = equity.filter(Number.isFinite).concat((benchmark ?? []).filter((v): v is number => v != null && Number.isFinite(v)));
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (n - 1)) * (w - pad * 2);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - pad * 2);
  const path = (vals: Array<number | null>) => {
    let d = "";
    let pen = false;
    vals.forEach((v, i) => {
      if (v == null || !Number.isFinite(v)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
    });
    return d;
  };
  // 낙폭
  let peak = -Infinity;
  const dd = equity.map((v) => { peak = Math.max(peak, v); return peak > 0 ? (v / peak - 1) * 100 : 0; });
  const ddMin = Math.min(...dd, -0.01);
  const ddH = 90;
  const ddY = (v: number) => 20 + (v / ddMin) * (ddH - 20);
  const ddPath = dd.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${ddY(v).toFixed(1)}`).join(" ") + ` L${x(n - 1).toFixed(1)},20 L${x(0).toFixed(1)},20 Z`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * (n - 1)));
  return `
<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="${esc(t("자산곡선"))}">
  <rect x="0" y="0" width="${w}" height="${h}" fill="#ffffff"/>
  ${benchmark ? `<path d="${path(benchmark)}" fill="none" stroke="#9ca3af" stroke-width="1.2"/>` : ""}
  <path d="${path(equity)}" fill="none" stroke="#0ea5e9" stroke-width="2"/>
  ${ticks.map((i) => `<text x="${x(i).toFixed(1)}" y="${h - 10}" font-size="10" text-anchor="middle" fill="#6b7280">${esc(dates[i] ?? "")}</text>`).join("")}
  <text x="${pad}" y="14" font-size="10" fill="#6b7280">${esc(t("최대 {0}", fmtShort(max)))}</text>
  <text x="${pad}" y="${h - pad + 12}" font-size="10" fill="#6b7280">${esc(t("최소 {0}", fmtShort(min)))}</text>
</svg>
<svg viewBox="0 0 ${w} ${ddH + 10}" width="100%" role="img" aria-label="${esc(t("낙폭"))}">
  <rect x="0" y="0" width="${w}" height="${ddH + 10}" fill="#ffffff"/>
  <path d="${ddPath}" fill="#fecaca" stroke="#ef4444" stroke-width="1"/>
  <text x="${pad}" y="${ddH + 4}" font-size="10" fill="#6b7280">${esc(t("최대 낙폭 {0}%", ddMin.toFixed(1)))}</text>
</svg>`;
}

function fmtShort(v: number): string {
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}억`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(0)}만`;
  return Math.round(v).toLocaleString();
}

function monthlyTable(monthly: Record<string, number>): string {
  const years = new Map<string, Record<number, number>>();
  for (const [ym, v] of Object.entries(monthly)) {
    const [yy, mm] = ym.split("-");
    if (!yy || !mm) continue;
    const row = years.get(yy) ?? {};
    row[Number(mm)] = v;
    years.set(yy, row);
  }
  if (years.size === 0) return "";
  const head = `<tr><th>${esc(t("연도"))}</th>${Array.from({ length: 12 }, (_, i) => `<th>${i + 1}</th>`).join("")}<th>${esc(t("연간"))}</th></tr>`;
  const body = Array.from(years.entries()).sort().map(([yy, row]) => {
    const cells = Array.from({ length: 12 }, (_, i) => {
      const v = row[i + 1];
      if (v == null) return "<td>—</td>";
      const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
      return `<td class="${cls}">${v.toFixed(1)}</td>`;
    }).join("");
    const annual = Object.values(row).reduce((acc, v) => acc * (1 + v / 100), 1) - 1;
    return `<tr><td>${esc(yy)}</td>${cells}<td class="${annual >= 0 ? "pos" : "neg"}">${(annual * 100).toFixed(1)}</td></tr>`;
  }).join("");
  return `<h2>${esc(t("월별 수익률 (%)"))}</h2><table class="grid">${head}${body}</table>`;
}

export function buildTearsheetHtml(p: TearsheetPayload): string {
  const totalReturn = p.initialCapital > 0 ? (p.finalEquity / p.initialCapital - 1) * 100 : 0;
  const sections = p.sections.map((s) => `
<h2>${esc(s.title)}</h2>
<table>${s.header ? `<tr>${s.header.map((h) => `<th>${esc(h)}</th>`).join("")}</tr>` : ""}
${s.rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</table>`).join("");
  return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>${esc(p.strategyName)} — ${esc(t("백테스트 티어시트"))}</title>
<style>
  body{font-family:-apple-system,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;color:#111827;margin:0;background:#f3f4f6}
  .page{max-width:960px;margin:0 auto;background:#fff;padding:32px 40px}
  h1{font-size:22px;margin:0 0 4px}h2{font-size:14px;margin:24px 0 8px;letter-spacing:.04em;text-transform:uppercase;color:#374151}
  .meta{color:#6b7280;font-size:12px}
  .metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:16px 0}
  .metric{border:1px solid #e5e7eb;border-radius:8px;padding:10px}.metric .l{font-size:11px;color:#6b7280}.metric .v{font-size:18px;font-weight:700}
  table{width:100%;border-collapse:collapse;font-size:12px}td,th{border-bottom:1px solid #e5e7eb;padding:4px 6px;text-align:right}
  td:first-child,th:first-child{text-align:left}th{color:#6b7280;font-weight:600}
  .grid td,.grid th{text-align:center;font-size:11px}.pos{color:#dc2626}.neg{color:#2563eb}
  ul.lines{font-size:12px;color:#374151;padding-left:18px}ul.warn{font-size:11px;color:#92400e;padding-left:18px}
  .print{position:fixed;right:16px;top:16px;padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;background:#fff;font-size:12px;cursor:pointer}
  .disclaimer{margin-top:24px;font-size:11px;color:#6b7280;border-top:1px solid #e5e7eb;padding-top:8px}
  @media print{.print{display:none}.page{padding:0}body{background:#fff}}
</style></head>
<body><button class="print" onclick="window.print()">${esc(t("PDF로 저장 (인쇄)"))}</button>
<div class="page">
<h1>${esc(p.strategyName)}</h1>
<div class="meta">${esc(t("기간"))} ${esc(p.period.from)} ~ ${esc(p.period.to)} · ${esc(t("유니버스"))} ${esc(p.universe)} · ${esc(t("생성"))} ${esc(p.generatedAt)}</div>
<div class="metrics">
  <div class="metric"><div class="l">${esc(t("초기 자본"))}</div><div class="v">${esc(fmtMoney(p.initialCapital, p.currency))}</div></div>
  <div class="metric"><div class="l">${esc(t("최종 자산"))}</div><div class="v">${esc(fmtMoney(p.finalEquity, p.currency))}</div></div>
  <div class="metric"><div class="l">${esc(t("총수익률"))}</div><div class="v ${totalReturn >= 0 ? "pos" : "neg"}">${totalReturn.toFixed(2)}%</div></div>
  ${p.metrics.map((m) => `<div class="metric"><div class="l">${esc(m.label)}</div><div class="v">${esc(m.value)}</div></div>`).join("")}
</div>
${p.summaryLines.length ? `<h2>${esc(t("전략 요약"))}</h2><ul class="lines">${p.summaryLines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}
<h2>${esc(t("자산곡선·낙폭"))}</h2>
${equitySvg(p.dates, p.equity, p.benchmarkEquity)}
${p.monthlyReturns ? monthlyTable(p.monthlyReturns) : ""}
${sections}
${p.warnings.length ? `<h2>${esc(t("결과 경고"))}</h2><ul class="warn">${p.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
<div class="disclaimer">${esc(t("이 문서는 과거 데이터 기반 시뮬레이션 결과입니다. 미래 수익은 보장되지 않으며 투자 권유나 추천이 아닙니다."))}</div>
</div></body></html>`;
}
