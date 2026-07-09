// 백테스트 결과 다운로드(내보내기) — CSV/JSON 파일 생성 로직 (순수 함수, 서버·클라이언트 공용)
//
// 원칙:
// - 전략명은 메타데이터/제목에 한 번만 포함하고, 각 행(row)에 반복하지 않는다.
// - CSV는 Excel 한글 깨짐 방지를 위해 UTF-8 BOM을 붙인다.
// - 향후 Excel/PDF 등 포맷 추가가 쉽도록 buildExportFile 의 포맷 분기만 확장하면 되게 한다.

export type ExportFormat = "csv" | "json";

/** 현재 지원하는 다운로드 포맷 목록 (모달 버튼 렌더링·검증에 공용) */
export const EXPORT_FORMATS: ReadonlyArray<{ format: ExportFormat; label: string; mimeType: string }> = [
  { format: "csv", label: "CSV 다운로드", mimeType: "text/csv;charset=utf-8" },
  { format: "json", label: "JSON 다운로드", mimeType: "application/json;charset=utf-8" },
];

export function isExportFormat(value: unknown): value is ExportFormat {
  return value === "csv" || value === "json";
}

export interface BacktestExportMetadata {
  strategyName: string;
  backtestId: string;
  /** ISO 8601 (타임존 포함) */
  exportedAt: string;
  period: { from: string; to: string };
  universe: string;
  initialCapital: number;
  finalEquity: number;
  /** 수수료율 (소수, 예: 0.00015 = 0.015%) */
  commission?: number;
  /** 슬리피지율 (소수, 예: 0.0005 = 0.05%) */
  slippage?: number;
  benchmark?: string;
}

/** 종목 분석 행 — 비율(winRate/totalReturn)은 모두 소수(0~1)로 저장한다. */
export interface StockAnalysisRow {
  symbol: string;
  name: string;
  tradeCount: number;
  winRate: number;
  totalReturn: number;
  totalProfit: number;
}

/** 매매 기록 행 — 엔진이 내려주는 개별 체결(매수/매도) 이벤트 단위이다. */
export interface TradeHistoryRow {
  date: string;
  symbol: string;
  name: string;
  type: "buy" | "sell";
  price: number;
  quantity: number;
  amount: number;
  reason: string;
}

export interface BacktestExportPayload {
  metadata: BacktestExportMetadata;
  stockAnalysis: StockAnalysisRow[];
  tradeHistory: TradeHistoryRow[];
}

export interface ExportFile {
  fileName: string;
  mimeType: string;
  content: string;
}

/** 전략명 → 파일명 슬러그. 한글/기호를 제거하고 영숫자만 남기며, 비면 기본값. */
export function strategySlug(name: string): string {
  const slug = (name || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return slug || "strategy";
}

function yyyymmdd(iso: string): string {
  // ISO 문자열 앞 10자(YYYY-MM-DD)에서 하이픈만 제거
  const datePart = (iso || "").slice(0, 10);
  const digits = datePart.replace(/[^0-9]/g, "");
  return digits.length === 8 ? digits : datePart;
}

export function exportFileName(payload: BacktestExportPayload, format: ExportFormat): string {
  const slug = strategySlug(payload.metadata.strategyName);
  const stamp = yyyymmdd(payload.metadata.exportedAt);
  return `${slug}_backtest_result_${stamp}.${format}`;
}

// ── CSV ─────────────────────────────────────────────────────────────────────

const UTF8_BOM = "﻿";

/** CSV 셀 이스케이프: 콤마/따옴표/개행이 있으면 따옴표로 감싼다. */
function csvCell(value: string | number): string {
  const str = String(value ?? "");
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function csvRow(cells: Array<string | number>): string {
  return cells.map(csvCell).join(",");
}

function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(2)}%`;
}

// 수수료/슬리피지처럼 아주 작은 비율은 2자리로는 0이 되어버리므로(0.015% → 0.01%)
// 정밀도를 높이고 뒤의 불필요한 0을 제거한다. (0.00015 → "0.015%", 0.0005 → "0.05%")
function formatRatePercent(fraction: number): string {
  return `${Number((fraction * 100).toFixed(4))}%`;
}

function tradeTypeLabel(type: "buy" | "sell"): string {
  return type === "buy" ? "매수" : "매도";
}

function buildCsv(payload: BacktestExportPayload): string {
  const { metadata, stockAnalysis, tradeHistory } = payload;
  const lines: string[] = [];

  // 메타데이터 — 전략명은 여기에 한 번만 포함한다.
  lines.push(csvRow(["전략명", metadata.strategyName]));
  lines.push(csvRow(["백테스트 ID", metadata.backtestId]));
  lines.push(csvRow(["기간", `${metadata.period.from} ~ ${metadata.period.to}`]));
  lines.push(csvRow(["생성시간", metadata.exportedAt]));
  lines.push(csvRow(["유니버스", metadata.universe]));
  lines.push(csvRow(["초기자본", metadata.initialCapital]));
  lines.push(csvRow(["최종자산", metadata.finalEquity]));
  if (metadata.commission != null) lines.push(csvRow(["수수료", formatRatePercent(metadata.commission)]));
  if (metadata.slippage != null) lines.push(csvRow(["슬리피지", formatRatePercent(metadata.slippage)]));

  // 종목 분석
  lines.push("[종목 분석]");
  lines.push(csvRow(["종목코드", "종목명", "거래횟수", "승률", "수익률", "총손익"]));
  for (const r of stockAnalysis) {
    lines.push(
      csvRow([r.symbol, r.name, r.tradeCount, formatPercent(r.winRate), formatPercent(r.totalReturn), Math.round(r.totalProfit)])
    );
  }

  // 매매 기록
  lines.push("[매매 기록]");
  lines.push(csvRow(["날짜", "종목코드", "종목명", "구분", "체결가", "수량", "거래금액", "매매사유"]));
  for (const t of tradeHistory) {
    lines.push(
      csvRow([t.date, t.symbol, t.name, tradeTypeLabel(t.type), Math.round(t.price), Math.floor(t.quantity), Math.round(t.amount), t.reason])
    );
  }

  return UTF8_BOM + lines.join("\r\n");
}

// ── 진입점 ──────────────────────────────────────────────────────────────────

export function buildExportFile(payload: BacktestExportPayload, format: ExportFormat): ExportFile {
  const fileName = exportFileName(payload, format);
  if (format === "json") {
    return {
      fileName,
      mimeType: "application/json;charset=utf-8",
      content: JSON.stringify(payload, null, 2),
    };
  }
  // 기본: csv (향후 xlsx/pdf 추가 시 여기 분기만 확장)
  return {
    fileName,
    mimeType: "text/csv;charset=utf-8",
    content: buildCsv(payload),
  };
}
