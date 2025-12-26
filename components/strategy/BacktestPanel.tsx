"use client";

import { useState, useEffect, useMemo } from "react";
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ChartBarIcon,
  InformationCircleIcon,
} from "@heroicons/react/24/outline";
import { StrategyDSL, BacktestResult, BacktestScenario } from "@/types/strategy";
import { runBacktest } from "@/lib/backtest-engine";

interface BacktestPanelProps {
  strategy: StrategyDSL;
}

export default function BacktestPanel({ strategy }: BacktestPanelProps) {
  const [backtestPeriod, setBacktestPeriod] = useState<"1Y" | "3Y" | "5Y" | "Max">("1Y");
  const [backtestStatus, setBacktestStatus] = useState<
    "idle" | "running" | "completed" | "error"
  >("idle");
  const [results, setResults] = useState<BacktestResult | null>(null);
  const [resultTab, setResultTab] = useState<"summary" | "chart" | "report">("summary");
  const [chartType, setChartType] = useState<
    "equity" | "drawdown" | "heatmap" | "distribution"
  >("equity");
  const [savedScenarios, setSavedScenarios] = useState<BacktestScenario[]>([]);
  const [showCompare, setShowCompare] = useState(false);

  // Load saved scenarios
  useEffect(() => {
    const saved = localStorage.getItem(`backtest_scenarios_${strategy.id}`);
    if (saved) {
      try {
        setSavedScenarios(JSON.parse(saved));
      } catch (e) {
        console.error("Failed to load scenarios", e);
      }
    }
  }, [strategy.id]);

  // Run backtest
  const handleRunBacktest = async () => {
    setBacktestStatus("running");
    setResults(null);

    try {
      // Simulate backtest execution
      await new Promise((resolve) => setTimeout(resolve, 2000));

      const result = await runBacktest(strategy, backtestPeriod);
      setResults(result);
      setBacktestStatus("completed");
    } catch (error) {
      console.error("Backtest error:", error);
      setBacktestStatus("error");
    }
  };

  // Save scenario
  const handleSaveScenario = () => {
    if (!results) return;

    const scenario: BacktestScenario = {
      id: `scenario_${Date.now()}`,
      strategyId: strategy.id,
      strategyName: strategy.name,
      params: {
        period: backtestPeriod,
      },
      results,
      timestamp: new Date().toISOString(),
    };

    const updated = [...savedScenarios, scenario];
    setSavedScenarios(updated);
    localStorage.setItem(
      `backtest_scenarios_${strategy.id}`,
      JSON.stringify(updated)
    );
    alert("시나리오가 저장되었습니다.");
  };

  // Format price
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  return (
    <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white mb-1">{strategy.name}</h2>
          <p className="text-sm text-gray-400">{strategy.description}</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-[#0f0f0f] rounded-lg p-1 border border-gray-800">
            {(["1Y", "3Y", "5Y", "Max"] as const).map((period) => (
              <button
                key={period}
                onClick={() => setBacktestPeriod(period)}
                className={`px-3 py-1 text-xs rounded transition-colors ${
                  backtestPeriod === period
                    ? "bg-blue-600 text-white"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                {period}
              </button>
            ))}
          </div>
          <button
            onClick={handleRunBacktest}
            disabled={backtestStatus === "running"}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors flex items-center gap-2 ${
              backtestStatus === "running"
                ? "bg-yellow-600 text-white cursor-not-allowed"
                : backtestStatus === "completed"
                ? "bg-blue-600 text-white"
                : "bg-blue-600 text-white hover:bg-blue-600"
            } disabled:bg-gray-600 disabled:cursor-not-allowed`}
          >
            {backtestStatus === "running" ? (
              <>
                <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>실행 중...</span>
              </>
            ) : backtestStatus === "completed" ? (
              <>
                <CheckCircleIcon className="w-4 h-4" />
                <span>실행</span>
              </>
            ) : (
              <span>백테스트 실행</span>
            )}
          </button>
        </div>
      </div>

      {/* Progress */}
      {backtestStatus === "running" && (
        <div className="mb-6 w-full bg-gray-700 rounded-full h-1.5">
          <div
            className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
            style={{ width: "60%" }}
          />
        </div>
      )}

      {/* Quick Results Preview */}
      {backtestStatus === "completed" && results && (
        <div className="mb-6 grid grid-cols-5 gap-3">
          <div className="p-3 bg-[#0f0f0f] rounded-lg border border-gray-800">
            <div className="text-xs text-gray-400 mb-1">수익률</div>
            <div
              className={`text-lg font-bold ${
                results.totalReturn >= 0 ? "text-red-400" : "text-blue-400"
              }`}
            >
              {results.totalReturn >= 0 ? "+" : ""}
              {results.totalReturn.toFixed(2)}%
            </div>
          </div>
          <div className="p-3 bg-[#0f0f0f] rounded-lg border border-gray-800">
            <div className="text-xs text-gray-400 mb-1">MDD</div>
            <div className="text-lg font-bold text-yellow-400">
              {results.maxDrawdown.toFixed(2)}%
            </div>
          </div>
          <div className="p-3 bg-[#0f0f0f] rounded-lg border border-gray-800">
            <div className="text-xs text-gray-400 mb-1">승률</div>
            <div className="text-lg font-bold text-white">
              {results.winRate.toFixed(1)}%
            </div>
          </div>
          <div className="p-3 bg-[#0f0f0f] rounded-lg border border-gray-800">
            <div className="text-xs text-gray-400 mb-1">Sharpe</div>
            <div className="text-lg font-bold text-white">
              {results.sharpe.toFixed(2)}
            </div>
          </div>
          <div className="p-3 bg-[#0f0f0f] rounded-lg border border-gray-800">
            <div className="text-xs text-gray-400 mb-1">거래</div>
            <div className="text-lg font-bold text-white">{results.trades}회</div>
          </div>
        </div>
      )}

      {/* Results Tabs */}
      {backtestStatus === "completed" && results ? (
        <>
          <div className="flex items-center gap-1 border-b border-gray-800 pb-2 mb-4">
            <button
              onClick={() => setResultTab("summary")}
              className={`px-3 py-1.5 text-xs font-medium transition-colors rounded ${
                resultTab === "summary"
                  ? "text-white bg-[#252525] border-b-2 border-transparent"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              요약
            </button>
            <button
              onClick={() => setResultTab("chart")}
              className={`px-3 py-1.5 text-xs font-medium transition-colors rounded ${
                resultTab === "chart"
                  ? "text-white bg-[#252525] border-b-2 border-transparent"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              차트
            </button>
            <button
              onClick={() => setResultTab("report")}
              className={`px-3 py-1.5 text-xs font-medium transition-colors rounded ${
                resultTab === "report"
                  ? "text-white bg-[#252525] border-b-2 border-transparent"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              리포트
            </button>
            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={handleSaveScenario}
                className="px-2.5 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-1"
              >
                <span>💾</span>
                <span>저장</span>
              </button>
              <button
                onClick={() => setShowCompare(!showCompare)}
                className={`px-2.5 py-1 text-xs rounded hover:bg-blue-600 flex items-center gap-1 ${
                  showCompare
                    ? "bg-blue-600 text-white"
                    : "bg-blue-600/50 text-white"
                }`}
              >
                <span>📊</span>
                <span>비교</span>
              </button>
            </div>
          </div>

          {/* Summary Tab */}
          {resultTab === "summary" && (
            <div className="space-y-4 mt-4">
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">총 수익률</div>
                  <div
                    className={`text-xl font-bold ${
                      results.totalReturn >= 0 ? "text-red-400" : "text-blue-400"
                    }`}
                  >
                    {results.totalReturn >= 0 ? "+" : ""}
                    {results.totalReturn.toFixed(2)}%
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    CAGR: {results.cagr >= 0 ? "+" : ""}
                    {results.cagr.toFixed(2)}%
                  </div>
                </div>
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">MDD</div>
                  <div className="text-xl font-bold text-yellow-400">
                    {results.maxDrawdown.toFixed(2)}%
                  </div>
                  <div
                    className={`text-xs mt-1 ${
                      results.maxDrawdown < 10
                        ? "text-blue-400"
                        : results.maxDrawdown < 20
                        ? "text-yellow-400"
                        : "text-red-400"
                    }`}
                  >
                    {results.maxDrawdown < 10
                      ? "우수"
                      : results.maxDrawdown < 20
                      ? "보통"
                      : "주의"}
                  </div>
                </div>
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">승률</div>
                  <div className="text-xl font-bold text-white">
                    {results.winRate.toFixed(1)}%
                  </div>
                  <div
                    className={`text-xs mt-1 ${
                      results.winRate > 60
                        ? "text-blue-400"
                        : results.winRate > 50
                        ? "text-yellow-400"
                        : "text-red-400"
                    }`}
                  >
                    {results.winRate > 60
                      ? "우수"
                      : results.winRate > 50
                      ? "보통"
                      : "낮음"}
                  </div>
                </div>
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">손익비</div>
                  <div className="text-xl font-bold text-white">
                    {results.profitFactor.toFixed(2)}
                  </div>
                  <div
                    className={`text-xs mt-1 ${
                      results.profitFactor > 2
                        ? "text-blue-400"
                        : results.profitFactor > 1.5
                        ? "text-yellow-400"
                        : "text-red-400"
                    }`}
                  >
                    {results.profitFactor > 2
                      ? "우수"
                      : results.profitFactor > 1.5
                      ? "보통"
                      : "낮음"}
                  </div>
                </div>
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">거래 횟수</div>
                  <div className="text-xl font-bold text-white">{results.trades}</div>
                  <div className="text-xs text-gray-500 mt-1">회</div>
                </div>
              </div>
            </div>
          )}

          {/* Chart Tab */}
          {resultTab === "chart" && (
            <div className="space-y-4 mt-4">
              <div className="flex items-center gap-1 bg-[#0f0f0f] rounded-lg p-1 border border-gray-800">
                {[
                  { key: "equity", label: "수익곡선" },
                  { key: "drawdown", label: "낙폭" },
                  { key: "heatmap", label: "히트맵" },
                  { key: "distribution", label: "분포" },
                ].map((type) => (
                  <button
                    key={type.key}
                    onClick={() => setChartType(type.key as any)}
                    className={`px-3 py-1 text-xs rounded transition-colors ${
                      chartType === type.key
                        ? "bg-blue-600 text-white"
                        : "text-gray-400 hover:text-white"
                    }`}
                  >
                    {type.label}
                  </button>
                ))}
              </div>

              {/* Equity Curve */}
              {chartType === "equity" && (
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-medium text-white">누적 수익 곡선</h4>
                    <span className="text-xs text-gray-500">
                      최종: {formatPrice(results.finalEquity)}원
                    </span>
                  </div>
                  <div className="h-56 flex items-end gap-0.5">
                    {results.equity
                      .filter(
                        (_: number, i: number) =>
                          i % Math.ceil(results.equity.length / 100) === 0
                      )
                      .map((value: number, i: number) => {
                        const maxEquity = Math.max(...results.equity);
                        const minEquity = Math.min(...results.equity);
                        const height =
                          ((value - minEquity) / (maxEquity - minEquity)) * 100;
                        return (
                          <div
                            key={i}
                            className="flex-1 bg-blue-600 rounded-t hover:bg-blue-600 transition-colors"
                            style={{ height: `${height}%` }}
                            title={`${formatPrice(value)}원`}
                          />
                        );
                      })}
                  </div>
                </div>
              )}

              {/* Drawdown */}
              {chartType === "drawdown" && (
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-medium text-white">Drawdown</h4>
                    <span className="text-xs text-yellow-400">
                      최대: {results.maxDrawdown.toFixed(2)}%
                    </span>
                  </div>
                  <div className="h-56 flex items-end gap-0.5">
                    {results.equity.map((value: number, i: number) => {
                      const peak = Math.max(...results.equity.slice(0, i + 1));
                      const drawdown = ((peak - value) / peak) * 100;
                      return (
                        <div
                          key={i}
                          className="flex-1 bg-red-500 rounded-t"
                          style={{
                            height: `${Math.min(drawdown * 2, 100)}%`,
                          }}
                        />
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Heatmap */}
              {chartType === "heatmap" && (
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <h4 className="text-sm font-medium text-white mb-3">
                    Monthly Returns Heatmap
                  </h4>
                  <div className="grid grid-cols-12 gap-1">
                    {Object.entries(results.monthlyReturns || {}).map(
                      ([month, returnPct]: [string, any]) => (
                        <div
                          key={month}
                          className={`p-2 rounded text-xs text-center ${
                            returnPct > 5
                              ? "bg-blue-600 text-white"
                              : returnPct > 0
                              ? "bg-blue-600 text-white"
                              : returnPct > -5
                              ? "bg-red-400 text-white"
                              : "bg-red-600 text-white"
                          }`}
                          title={`${month}: ${returnPct.toFixed(2)}%`}
                        >
                          {returnPct >= 0 ? "+" : ""}
                          {returnPct.toFixed(1)}%
                        </div>
                      )
                    )}
                  </div>
                </div>
              )}

              {/* Distribution */}
              {chartType === "distribution" && (
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <h4 className="text-sm font-medium text-white mb-3">
                    수익/손실 분포
                  </h4>
                  <div className="h-56 flex items-end gap-1">
                    {Array.from({ length: 20 }).map((_, i) => {
                      const range = (i - 10) * 2; // -20% to +20%
                      const count = Math.floor(Math.random() * 30); // Mock data
                      return (
                        <div
                          key={i}
                          className="flex-1 bg-blue-700 rounded-t"
                          style={{ height: `${count * 3}%` }}
                          title={`${range}%: ${count}건`}
                        />
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Report Tab */}
          {resultTab === "report" && (
            <div className="space-y-4 mt-4">
              {/* Stats */}
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <h4 className="text-sm font-semibold text-white mb-3">고급 지표</h4>
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <div className="text-xs text-gray-400 mb-1">Sharpe Ratio</div>
                    <div className="text-lg font-semibold text-white">
                      {results.sharpe.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400 mb-1">Sortino Ratio</div>
                    <div className="text-lg font-semibold text-white">
                      {results.sortino.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400 mb-1">Kelly %</div>
                    <div className="text-lg font-semibold text-white">
                      {results.kelly.toFixed(2)}%
                    </div>
                  </div>
                </div>
              </div>

              {/* Trades Table */}
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <h4 className="text-sm font-semibold text-white mb-3">거래 내역</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-800">
                        <th className="text-left py-2 text-gray-400">날짜</th>
                        <th className="text-left py-2 text-gray-400">유형</th>
                        <th className="text-right py-2 text-gray-400">가격</th>
                        <th className="text-right py-2 text-gray-400">수량</th>
                        <th className="text-right py-2 text-gray-400">금액</th>
                        <th className="text-left py-2 text-gray-400">사유</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.tradesList.slice(-20).map((trade: any, i: number) => (
                        <tr key={i} className="border-b border-gray-800/50">
                          <td className="py-2 text-gray-300">{trade.date}</td>
                          <td
                            className={`py-2 font-medium ${
                              trade.type === "buy" ? "text-red-400" : "text-blue-400"
                            }`}
                          >
                            {trade.type === "buy" ? "매수" : "매도"}
                          </td>
                          <td className="py-2 text-right text-white">
                            {formatPrice(trade.price)}원
                          </td>
                          <td className="py-2 text-right text-gray-300">
                            {trade.quantity || "-"}
                          </td>
                          <td className="py-2 text-right text-white">
                            {formatPrice(trade.price * (trade.quantity || 1))}원
                          </td>
                          <td className="py-2 text-gray-400 text-xs">{trade.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Signals Timeline */}
              {results.signals && results.signals.length > 0 && (
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <h4 className="text-sm font-semibold text-white mb-3">신호 타임라인</h4>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {results.signals.slice(-30).map((signal: any, i: number) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-2 bg-[#1a1a1a] rounded"
                      >
                        <div className="flex items-center gap-3">
                          <span
                            className={`px-2 py-1 text-xs rounded ${
                              signal.type === "entry"
                                ? "bg-blue-600/20 text-blue-400"
                                : "bg-red-600/20 text-red-400"
                            }`}
                          >
                            {signal.type === "entry" ? "매수" : "매도"}
                          </span>
                          <span className="text-xs text-gray-400">{signal.date}</span>
                          <span className="text-xs text-gray-500">{signal.condition}</span>
                        </div>
                        <span className="text-xs text-white">
                          {formatPrice(signal.price)}원
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Scenario Compare */}
          {showCompare && savedScenarios.length > 0 && (
            <div className="mt-4 p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
              <h4 className="text-sm font-semibold text-white mb-3">시나리오 비교</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="text-left py-2 text-gray-400">전략</th>
                      <th className="text-right py-2 text-gray-400">Return</th>
                      <th className="text-right py-2 text-gray-400">MDD</th>
                      <th className="text-right py-2 text-gray-400">Sharpe</th>
                      <th className="text-right py-2 text-gray-400">승률</th>
                      <th className="text-right py-2 text-gray-400">거래</th>
                    </tr>
                  </thead>
                  <tbody>
                    {savedScenarios.map((scenario) => (
                      <tr
                        key={scenario.id}
                        className="border-b border-gray-800/50 hover:bg-gray-800/30 cursor-pointer"
                        onClick={() => setResults(scenario.results)}
                      >
                        <td className="py-2 text-white">{scenario.strategyName}</td>
                        <td
                          className={`py-2 text-right font-medium ${
                            scenario.results.totalReturn >= 0
                              ? "text-red-400"
                              : "text-blue-400"
                          }`}
                        >
                          {scenario.results.totalReturn >= 0 ? "+" : ""}
                          {scenario.results.totalReturn.toFixed(2)}%
                        </td>
                        <td className="py-2 text-right text-yellow-400">
                          {scenario.results.maxDrawdown.toFixed(2)}%
                        </td>
                        <td className="py-2 text-right text-white">
                          {scenario.results.sharpe.toFixed(2)}
                        </td>
                        <td className="py-2 text-right text-white">
                          {scenario.results.winRate.toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-white">
                          {scenario.results.trades}회
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : backtestStatus === "idle" ? (
        <div className="p-8 bg-[#0f0f0f] rounded-lg border border-gray-800 text-center">
          <ChartBarIcon className="w-12 h-12 text-gray-600 mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-white mb-2">백테스트 준비 완료</h3>
          <p className="text-xs text-gray-400">
            테스트 기간을 선택하고 실행 버튼을 클릭하세요
          </p>
        </div>
      ) : backtestStatus === "error" ? (
        <div className="p-8 bg-[#0f0f0f] rounded-lg border border-red-800 text-center">
          <ExclamationTriangleIcon className="w-12 h-12 text-red-400 mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-red-400 mb-2">실행 오류</h3>
          <p className="text-xs text-gray-400">
            백테스트 실행 중 오류가 발생했습니다. 다시 시도해주세요.
          </p>
        </div>
      ) : null}
    </div>
  );
}

