"use client";

import { 
  PlayCircleIcon, 
  ArrowLeftIcon, 
  ArrowRightIcon, 
  CheckCircleIcon 
} from "@heroicons/react/24/outline";
import { BacktestResult } from "@/types/strategy";
import BacktestChart from "@/components/strategy/BacktestChart";

interface Step5BacktestProps {
  strategyName: string;
  backtestResult: BacktestResult | null;
  isBacktesting: boolean;
  onPrev: () => void;
  onSave: () => void;
}

export default function Step5Backtest({
  strategyName,
  backtestResult,
  isBacktesting,
  onPrev,
  onSave,
}: Step5BacktestProps) {
  return (
    <div className="flex flex-col p-8 gap-6">
      <div className="flex items-center justify-between shrink-0 mb-4">
        <div>
          <h3 className="text-xl font-black text-white">전략 검증</h3>
          <p className="text-sm text-gray-500 mt-1 font-medium">
            결과를 확인하고 전략을 최종 점검하세요.
          </p>
        </div>
      </div>
      
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 flex-1 min-h-0">
        <div className="xl:col-span-2 space-y-4">
          <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
            <div className="h-72 bg-[#0a0a0f] rounded border border-gray-800 overflow-hidden relative">
              {backtestResult ? (
                <BacktestChart 
                  type="equity" 
                  height={288} 
                  equityData={backtestResult.dates.map((d: string, i: number) => ({ 
                    time: d, 
                    equity: backtestResult.equity[i], 
                    buyHold: backtestResult.initialCapital * (1 + (backtestResult.buyAndHoldReturn || 0)/100) 
                  }))} 
                />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">
                  {isBacktesting ? "시뮬레이션 중..." : "결과 없음"}
                </div>
              )}
            </div>
          </div>
          <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
            <h4 className="text-sm font-semibold text-white mb-3">로그</h4>
            <div className="space-y-2 pr-2 custom-scrollbar max-h-48 overflow-y-auto">
              {backtestResult?.tradesList && backtestResult.tradesList.length > 0 ? (
                backtestResult.tradesList.map((trade, i) => (
                  <div key={i} className="flex items-center justify-between text-[11px] p-2 rounded bg-[#0a0a0a] border border-gray-900 group">
                    <div className="flex items-center gap-3">
                      <span className="text-gray-500 font-mono">{trade.date}</span>
                      <span className={`font-bold px-1.5 py-0.5 rounded ${trade.type === 'buy' ? 'bg-red-500/10 text-red-400' : 'bg-blue-500/10 text-blue-400'}`}>
                        {trade.type === 'buy' ? '매수' : '매도'}
                      </span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-gray-300 font-bold">{trade.price.toLocaleString()}원</span>
                      <span className="text-gray-500">{trade.quantity}주</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-gray-600 text-xs italic">
                  기록된 거래가 없습니다.
                </div>
              )}
            </div>
          </div>
        </div>
        
        <div className="space-y-4">
          <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
            <h4 className="text-sm font-semibold text-white mb-3">성과</h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="p-3 rounded bg-[#0a0a0a] border border-gray-800">
                <div className="text-xs text-gray-400 mb-1">수익률</div>
                <div className={`text-lg font-bold ${(backtestResult?.totalReturn || 0) >= 0 ? "text-red-400" : "text-blue-400"}`}>
                  {backtestResult ? `${backtestResult.totalReturn.toFixed(1)}%` : "0.0%"}
                </div>
              </div>
              <div className="p-3 rounded bg-[#0a0a0a] border border-gray-800">
                <div className="text-xs text-gray-400 mb-1">MDD</div>
                <div className="text-lg font-bold text-blue-400">
                  {backtestResult ? `${backtestResult.maxDrawdown.toFixed(1)}%` : "0.0%"}
                </div>
              </div>
            </div>
          </div>
          <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4 space-y-4">
            <div className="flex items-center gap-2 text-green-400 mb-1">
              <CheckCircleIcon className="w-5 h-5" />
              <span className="text-sm font-bold uppercase tracking-wider">검증 종료</span>
            </div>
            <p className="text-xs text-gray-500 leading-relaxed">
              전략을 저장하고 테스트를 시작할 수 있습니다.
            </p>
          </div>
        </div>
      </div>
      
      <div className="p-8 flex justify-end gap-3 mt-auto sticky bottom-0 bg-[#0f0f0f]/90 backdrop-blur-md z-20">
        <button 
          onClick={onPrev} 
          className="px-6 py-3 bg-[#0a0a0a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 transition-all flex items-center gap-2"
        >
          <ArrowLeftIcon className="w-5 h-5" /> 이전 단계
        </button>
        <button 
          onClick={onSave} 
          className="px-8 py-3 bg-red-600 text-white rounded-xl text-md font-black hover:bg-red-500 transition-all flex items-center gap-3 shadow-xl shadow-red-900/40"
        >
          전략 저장 <ArrowRightIcon className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
