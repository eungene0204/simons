import { getTopAssetStats } from "@/lib/backtest-top-symbols";

/**
 * BacktestResult.summary 에 넣는 JSON을 만든다.
 *
 * 저장 경로가 둘(결과 화면의 "저장" 버튼 = save-with-backtest, 가상계좌 생성 직전의
 * ensure)이고 두 경로가 만든 행을 같은 화면(/analytics/[id])이 읽으므로, 필드 구성이
 * 갈라지지 않도록 한 곳에서 만든다.
 */
export type BacktestReportFields = {
  score?: number | null;
  aiSummary?: string | null;
  aiScore?: number | null;
  aiStrengths?: string[];
  aiWeaknesses?: string[];
  aiImprovements?: string[];
  aiRisks?: string[];
  advisorScore?: number | null;
  riskScore?: number | null;
  overfitRisk?: string | null;
};

export function buildBacktestResultSummary(backtestResult: any, report: BacktestReportFields = {}) {
  // 무거운 배열 데이터(equity, dates, tradesList)는 summary에 통째로 저장
  const topAssetStats = getTopAssetStats(backtestResult.perAssetStats, 10);

  return {
    totalReturn: backtestResult.totalReturn,
    cagr: backtestResult.cagr,
    maxDrawdown: backtestResult.maxDrawdown,
    winRate: backtestResult.winRate,
    score: report.score ?? null,
    profitFactor: backtestResult.profitFactor,
    sharpe: backtestResult.sharpe,
    sortino: backtestResult.sortino,
    kelly: backtestResult.kelly,
    volatility: backtestResult.volatility,
    buyAndHoldReturn: backtestResult.buyAndHoldReturn,
    trades: backtestResult.trades,
    avgProfit: backtestResult.avgProfit,
    avgLoss: backtestResult.avgLoss,
    maxConsecutiveWins: backtestResult.maxConsecutiveWins,
    maxConsecutiveLosses: backtestResult.maxConsecutiveLosses,
    initialCapital: backtestResult.initialCapital,
    finalEquity: backtestResult.finalEquity,
    symbols: backtestResult.symbols,
    perAssetStats: backtestResult.perAssetStats,
    topSymbols: topAssetStats.map((stat) => stat.symbol),
    topAssetStats,
    equity: backtestResult.equity,
    benchmarkEquity: backtestResult.benchmarkEquity,
    dates: backtestResult.dates,
    warnings: backtestResult.warnings,
    executionTime: backtestResult.executionTime,
    aiSummary: report.aiSummary ?? null,
    aiScore: report.aiScore ?? null,
    aiStrengths: report.aiStrengths ?? [],
    aiWeaknesses: report.aiWeaknesses ?? [],
    aiImprovements: report.aiImprovements ?? [],
    aiRisks: report.aiRisks ?? [],
    advisorScore: report.advisorScore ?? null,
    riskScore: report.riskScore ?? null,
    overfitRisk: report.overfitRisk ?? null,
  };
}
