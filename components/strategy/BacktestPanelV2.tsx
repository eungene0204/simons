"use client";

import { useState, useEffect } from "react";
import {
  PlayCircleIcon,
  DocumentArrowDownIcon,
  ArrowPathIcon,
  ChartBarIcon,
  XMarkIcon,
  CalendarIcon,
  CurrencyDollarIcon,
  ClockIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";
import { StrategyDSL, BacktestResult } from "@/types/strategy";
import { runBacktest } from "@/lib/backtest-engine";
import BacktestChart from "./BacktestChart";

interface BacktestPanelV2Props {
  strategy: StrategyDSL | null;
  onEditStrategy?: () => void;
  onCompare?: () => void;
  onDownload?: (format: "json" | "csv") => void;
}

export default function BacktestPanelV2({
  strategy,
  onEditStrategy,
  onCompare,
  onDownload,
}: BacktestPanelV2Props) {
  // Settings
  const [startDate, setStartDate] = useState("2023-01-01");
  const [endDate, setEndDate] = useState(new Date().toISOString().split("T")[0]);
  const [initialCapital, setInitialCapital] = useState(10000000);
  const [commission, setCommission] = useState(0.15);
  const [slippage, setSlippage] = useState(0.1);
  const [benchmark, setBenchmark] = useState("kospi");

  // Status
  const [backtestStatus, setBacktestStatus] = useState<
    "idle" | "running" | "completed" | "error"
  >("idle");
  const [executionTime, setExecutionTime] = useState(0);
  const [progress, setProgress] = useState(0);

  // Results
  const [results, setResults] = useState<BacktestResult | null>(null);
  const [activeTab, setActiveTab] = useState<
    "trades" | "period" | "stocks" | "sector" | "risk" | "params"
  >("trades");

  // Run backtest
  const handleRunBacktest = async () => {
    if (!strategy) {
      alert("전략을 선택해주세요");
      return;
    }

    setBacktestStatus("running");
    setProgress(0);
    setExecutionTime(0);
    const startTime = Date.now();

    // Simulate progress
    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + 10;
      });
      setExecutionTime(Math.floor((Date.now() - startTime) / 1000));
    }, 200);

    try {
      const result = await runBacktest(strategy, "1Y");
      setResults(result);
      setProgress(100);
      setBacktestStatus("completed");
      clearInterval(progressInterval);
    } catch (error) {
      console.error("Backtest error:", error);
      setBacktestStatus("error");
      clearInterval(progressInterval);
    } finally {
      setExecutionTime(Math.floor((Date.now() - startTime) / 1000));
    }
  };

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  return (
    <div className="h-screen flex flex-col bg-[#0a0a0a] overflow-hidden">
      {/* Top Settings Area */}
      <div className="border-b border-gray-800 bg-[#1a1a1a] p-4">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">전략 선택</label>
              <input
                type="text"
                value={strategy?.name || ""}
                placeholder="전략 ID 또는 이름"
                className="w-full px-3 py-2 bg-[#0f0f0f] border border-gray-800 rounded text-sm text-white"
                readOnly
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">시작일</label>
              <div className="relative">
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-3 py-2 bg-[#0f0f0f] border border-gray-800 rounded text-sm text-white"
                />
                <CalendarIcon className="absolute right-2 top-2.5 w-4 h-4 text-gray-500 pointer-events-none" />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">종료일</label>
              <div className="relative">
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full px-3 py-2 bg-[#0f0f0f] border border-gray-800 rounded text-sm text-white"
                />
                <CalendarIcon className="absolute right-2 top-2.5 w-4 h-4 text-gray-500 pointer-events-none" />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">초기 자본</label>
              <div className="relative">
                <input
                  type="number"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(parseInt(e.target.value))}
                  className="w-full px-3 py-2 bg-[#0f0f0f] border border-gray-800 rounded text-sm text-white"
                />
                <CurrencyDollarIcon className="absolute right-2 top-2.5 w-4 h-4 text-gray-500 pointer-events-none" />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">수수료 / 슬리피지</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  step="0.01"
                  value={commission}
                  onChange={(e) => setCommission(parseFloat(e.target.value))}
                  placeholder="수수료"
                  className="flex-1 px-2 py-2 bg-[#0f0f0f] border border-gray-800 rounded text-xs text-white"
                />
                <input
                  type="number"
                  step="0.01"
                  value={slippage}
                  onChange={(e) => setSlippage(parseFloat(e.target.value))}
                  placeholder="슬리피지"
                  className="flex-1 px-2 py-2 bg-[#0f0f0f] border border-gray-800 rounded text-xs text-white"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">벤치마크</label>
              <select
                value={benchmark}
                onChange={(e) => setBenchmark(e.target.value)}
                className="w-full px-3 py-2 bg-[#0f0f0f] border border-gray-800 rounded text-sm text-white"
              >
                <option value="kospi">KOSPI</option>
                <option value="sp500">S&P 500</option>
                <option value="nasdaq">NASDAQ</option>
              </select>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              {backtestStatus === "running" && (
                <>
                  <div className="flex items-center gap-2 text-sm text-gray-400">
                    <ClockIcon className="w-4 h-4" />
                    <span>실행 중... {executionTime}초</span>
                  </div>
                  <div className="w-64 bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </>
              )}
              {backtestStatus === "completed" && (
                <div className="flex items-center gap-2 text-sm text-green-400">
                  <CheckCircleIcon className="w-4 h-4" />
                  <span>완료 ({executionTime}초)</span>
                </div>
              )}
              {backtestStatus === "error" && (
                <div className="flex items-center gap-2 text-sm text-red-400">
                  <ExclamationTriangleIcon className="w-4 h-4" />
                  <span>실행 실패</span>
                </div>
              )}
            </div>
            <button
              onClick={handleRunBacktest}
              disabled={backtestStatus === "running" || !strategy}
              className="px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <PlayCircleIcon className="w-4 h-4" />
              백테스트 실행
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Main Results */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Summary Cards */}
          {results && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="text-xs text-gray-400 mb-1">누적 수익률</div>
                <div
                  className={`text-xl font-bold ${
                    results.totalReturn >= 0 ? "text-red-400" : "text-blue-400"
                  }`}
                >
                  {results.totalReturn >= 0 ? "+" : ""}
                  {results.totalReturn.toFixed(2)}%
                </div>
              </div>
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="text-xs text-gray-400 mb-1">CAGR</div>
                <div className="text-xl font-bold text-white">
                  {results.cagr >= 0 ? "+" : ""}
                  {results.cagr.toFixed(2)}%
                </div>
              </div>
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="text-xs text-gray-400 mb-1">최대 낙폭</div>
                <div className="text-xl font-bold text-yellow-400">
                  {results.maxDrawdown.toFixed(2)}%
                </div>
              </div>
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="text-xs text-gray-400 mb-1">Sharpe Ratio</div>
                <div className="text-xl font-bold text-white">
                  {results.sharpe.toFixed(2)}
                </div>
              </div>
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="text-xs text-gray-400 mb-1">승률</div>
                <div className="text-xl font-bold text-white">
                  {results.winRate.toFixed(1)}%
                </div>
              </div>
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="text-xs text-gray-400 mb-1">평균 보유기간</div>
                <div className="text-xl font-bold text-white">-</div>
              </div>
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="text-xs text-gray-400 mb-1">트레이드 수</div>
                <div className="text-xl font-bold text-white">{results.trades}</div>
              </div>
            </div>
          )}

          {/* Charts */}
          {results && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
              <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
                <h4 className="text-sm font-semibold text-white mb-3">
                  Equity Curve (전략 vs 벤치마크)
                </h4>
                <div className="h-64">
                  <BacktestChart
                    equity={results.equity}
                    dates={results.dates}
                    type="equity"
                  />
                </div>
              </div>
              <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
                <h4 className="text-sm font-semibold text-white mb-3">Drawdown Curve</h4>
                <div className="h-64">
                  <BacktestChart
                    equity={results.equity}
                    dates={results.dates}
                    type="drawdown"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Analysis Tabs */}
          {results && (
            <div className="bg-[#0f0f0f] rounded-lg border border-gray-800">
              <div className="border-b border-gray-800 flex items-center overflow-x-auto">
                {[
                  { key: "trades", label: "트레이드 로그" },
                  { key: "period", label: "기간별 성과" },
                  { key: "stocks", label: "종목별 기여도" },
                  { key: "sector", label: "섹터 노출" },
                  { key: "risk", label: "리스크 분석" },
                  { key: "params", label: "파라미터 요약" },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key as any)}
                    className={`px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition ${
                      activeTab === tab.key
                        ? "border-blue-500 text-blue-400"
                        : "border-transparent text-gray-400 hover:text-white"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="p-4">
                {activeTab === "trades" && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-800">
                          <th className="text-left py-2 text-gray-400">진입일</th>
                          <th className="text-left py-2 text-gray-400">청산일</th>
                          <th className="text-right py-2 text-gray-400">진입가</th>
                          <th className="text-right py-2 text-gray-400">청산가</th>
                          <th className="text-right py-2 text-gray-400">수익률</th>
                          <th className="text-right py-2 text-gray-400">보유일</th>
                        </tr>
                      </thead>
                      <tbody>
                        {results.tradesList.slice(-20).map((trade: any, i: number) => (
                          <tr key={i} className="border-b border-gray-800/50">
                            <td className="py-2 text-gray-300">{trade.date}</td>
                            <td className="py-2 text-gray-300">-</td>
                            <td className="py-2 text-right text-white">
                              {formatPrice(trade.price)}
                            </td>
                            <td className="py-2 text-right text-white">-</td>
                            <td className="py-2 text-right text-gray-300">-</td>
                            <td className="py-2 text-right text-gray-300">-</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {activeTab === "period" && (
                  <div className="space-y-4">
                    <div>
                      <h5 className="text-sm font-semibold text-white mb-2">연도별 수익률</h5>
                      <div className="h-32 flex items-end gap-2">
                        {Object.entries(results.yearlyReturns || {}).map(([year, ret]: [string, any]) => (
                          <div key={year} className="flex-1 flex flex-col items-center">
                            <div
                              className={`w-full rounded-t ${
                                ret >= 0 ? "bg-blue-600" : "bg-red-600"
                              }`}
                              style={{ height: `${Math.abs(ret) * 2}%` }}
                            />
                            <span className="text-xs text-gray-400 mt-1">{year}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <h5 className="text-sm font-semibold text-white mb-2">월별 수익률 (Heatmap)</h5>
                      <div className="grid grid-cols-12 gap-1">
                        {Object.entries(results.monthlyReturns || {}).map(([month, ret]: [string, any]) => (
                          <div
                            key={month}
                            className={`p-2 rounded text-xs text-center ${
                              ret > 5
                                ? "bg-blue-600 text-white"
                                : ret > 0
                                ? "bg-blue-400 text-white"
                                : ret > -5
                                ? "bg-red-400 text-white"
                                : "bg-red-600 text-white"
                            }`}
                          >
                            {ret >= 0 ? "+" : ""}
                            {ret.toFixed(1)}%
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "stocks" && (
                  <div className="text-gray-400 text-sm">
                    종목별 기여도 분석 (구현 예정)
                  </div>
                )}

                {activeTab === "sector" && (
                  <div className="text-gray-400 text-sm">
                    섹터 노출 분석 (구현 예정)
                  </div>
                )}

                {activeTab === "risk" && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-3 bg-[#1a1a1a] rounded border border-gray-800">
                        <div className="text-xs text-gray-400 mb-1">Volatility</div>
                        <div className="text-lg font-semibold text-white">-</div>
                      </div>
                      <div className="p-3 bg-[#1a1a1a] rounded border border-gray-800">
                        <div className="text-xs text-gray-400 mb-1">Beta</div>
                        <div className="text-lg font-semibold text-white">-</div>
                      </div>
                      <div className="p-3 bg-[#1a1a1a] rounded border border-gray-800">
                        <div className="text-xs text-gray-400 mb-1">VaR</div>
                        <div className="text-lg font-semibold text-white">-</div>
                      </div>
                      <div className="p-3 bg-[#1a1a1a] rounded border border-gray-800">
                        <div className="text-xs text-gray-400 mb-1">Exposure</div>
                        <div className="text-lg font-semibold text-white">-</div>
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "params" && (
                  <div className="space-y-2 text-sm">
                    {strategy && (
                      <>
                        <div className="flex justify-between py-2 border-b border-gray-800">
                          <span className="text-gray-400">전략 이름</span>
                          <span className="text-white">{strategy.name}</span>
                        </div>
                        <div className="flex justify-between py-2 border-b border-gray-800">
                          <span className="text-gray-400">포지션 크기</span>
                          <span className="text-white">{strategy.risk.position_size_pct}%</span>
                        </div>
                        <div className="flex justify-between py-2 border-b border-gray-800">
                          <span className="text-gray-400">최대 포지션 수</span>
                          <span className="text-white">{strategy.risk.max_positions}</span>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {!results && backtestStatus === "idle" && (
            <div className="text-center py-20 text-gray-500">
              <ChartBarIcon className="w-16 h-16 mx-auto mb-4 text-gray-600" />
              <p className="text-sm">백테스트를 실행하세요</p>
            </div>
          )}
        </div>

        {/* Right: Quick Portfolio Status */}
        {results && (
          <div className="w-80 border-l border-gray-800 bg-[#0f0f0f] overflow-y-auto p-4">
            <div className="mb-4">
              <h4 className="text-sm font-semibold text-white mb-3">퀵 포트폴리오 상태</h4>
              <div className="space-y-3">
                <div className="p-3 bg-[#1a1a1a] rounded border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">Max Weight</div>
                  <div className="text-sm font-semibold text-white">-</div>
                </div>
                <div className="p-3 bg-[#1a1a1a] rounded border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">Min Weight</div>
                  <div className="text-sm font-semibold text-white">-</div>
                </div>
              </div>
            </div>
            <div className="mt-6">
              <h4 className="text-sm font-semibold text-white mb-3">포트폴리오 변동</h4>
              <div className="h-48 bg-[#1a1a1a] rounded border border-gray-800 p-3">
                <p className="text-xs text-gray-400">리밸런싱 시점 표시</p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Bottom Action Bar */}
      {results && (
        <div className="border-t border-gray-800 bg-[#1a1a1a] px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={onEditStrategy}
              className="px-4 py-2 bg-gray-700 text-white rounded text-sm hover:bg-gray-600 flex items-center gap-2"
            >
              <ArrowPathIcon className="w-4 h-4" />
              전략 수정하기
            </button>
            <button
              onClick={onCompare}
              className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-500 flex items-center gap-2"
            >
              <ChartBarIcon className="w-4 h-4" />
              다른 전략과 비교
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onDownload?.("json")}
              className="px-4 py-2 bg-gray-700 text-white rounded text-sm hover:bg-gray-600 flex items-center gap-2"
            >
              <DocumentArrowDownIcon className="w-4 h-4" />
              JSON 다운로드
            </button>
            <button
              onClick={() => onDownload?.("csv")}
              className="px-4 py-2 bg-gray-700 text-white rounded text-sm hover:bg-gray-600 flex items-center gap-2"
            >
              <DocumentArrowDownIcon className="w-4 h-4" />
              CSV 다운로드
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

