import React, { useState, useRef } from "react";
import { CircleNotch, Sparkle, WarningCircle, ArrowRight, X } from "phosphor-react";
import ReactMarkdown from 'react-markdown';
import { OptimizationResponse } from "@/types/strategy";

interface StrategyOptimizerModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOptimize: (prompt: string, targetMetric: string, nTrials?: number, signal?: AbortSignal) => Promise<OptimizationResponse>;
  onApplyParameters: (parameters: Record<string, any>) => void;
}

export function StrategyOptimizerModal({ open, onOpenChange, onOptimize, onApplyParameters }: StrategyOptimizerModalProps) {
  const [targetMetric, setTargetMetric] = useState("cagr");
  const [nTrials, setNTrials] = useState(50);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [result, setResult] = useState<OptimizationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  if (!open) return null;

  const handleOptimize = async () => {
    setIsOptimizing(true);
    setError(null);
    setResult(null);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const resp = await onOptimize("자동 생성된 범위 내에서 최고의 성과 도출", targetMetric, nTrials, controller.signal);
      setResult(resp);
    } catch (err: any) {
      if (err.name === "AbortError") {
        setError("최적화가 사용자에 의해 취소되었습니다.");
      } else {
        setError(err.message || "최적화 중 오류가 발생했습니다.");
      }
    } finally {
      abortRef.current = null;
      setIsOptimizing(false);
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
  };


  return (
    <div className="fixed inset-0 z-[9999] flex items-start justify-center p-4 pt-32 bg-black/60 backdrop-blur-md" onClick={() => !isOptimizing && onOpenChange(false)}>
      <div 
        className="w-full max-w-3xl bg-[#161616] rounded-3xl shadow-2xl flex flex-col backdrop-blur-2xl border border-white/10 overflow-hidden max-h-[85vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6 flex items-center justify-between border-b border-white/5">
          <div className="flex items-center gap-3">
             <div className="w-10 h-10 bg-indigo-500/10 rounded-xl flex items-center justify-center">
                <Sparkle className="w-5 h-5 text-indigo-400" weight="fill" />
             </div>
             <div>
               <h3 className="text-xl font-black text-white tracking-tight">AI 최적화</h3>
             </div>
          </div>
          <button 
            type="button"
            onClick={() => !isOptimizing && onOpenChange(false)}
            className="w-10 h-10 rounded-xl flex items-center justify-center text-white/40 hover:text-white hover:bg-white/10 transition-all"
            disabled={isOptimizing}
          >
            <X size={20} weight="bold" />
          </button>
        </div>

        <div className="p-6 overflow-y-auto custom-scrollbar flex-1 space-y-6">
          {!result && !isOptimizing && (
            <div className="space-y-6">
              <div className="space-y-2">
                <label className="text-sm font-black text-white/70 uppercase tracking-widest">최적화 목표 지표</label>
                <select 
                  value={targetMetric} 
                  onChange={(e) => setTargetMetric(e.target.value)}
                  className="w-full px-4 py-3.5 bg-black/40 border border-white/10 hover:border-white/20 rounded-xl text-sm font-black text-white outline-none appearance-none cursor-pointer transition-all"
                  style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 16px center' }}
                >
                  <option value="cagr" style={{ background: '#0d0d0d' }}>연평균 수익률 (CAGR)</option>
                  <option value="maxDrawdown" style={{ background: '#0d0d0d' }}>최대낙폭 (MDD)</option>
                  <option value="profitFactor" style={{ background: '#0d0d0d' }}>손익비 (Profit Factor)</option>
                  <option value="totalProfit" style={{ background: '#0d0d0d' }}>총 수익 (Total Profit)</option>
                  <option value="totalReturn" style={{ background: '#0d0d0d' }}>총 수익률 (Total Return)</option>
                </select>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-black text-white/70 uppercase tracking-widest">시뮬레이션 탐색 횟수 (Trials)</label>
                  <span className="text-indigo-400 font-mono font-bold text-sm bg-indigo-500/10 px-2 py-1 rounded">{nTrials}회</span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="500"
                  step="10"
                  value={nTrials}
                  onChange={(e) => setNTrials(Number(e.target.value))}
                  className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                />
                <p className="text-xs text-white/30 font-medium">
                  탐색 횟수가 클수록 모델이 최적점을 정밀하게 찾지만 더 오랜 시간이 소요됩니다. (추천: 50~100회)
                </p>
              </div>
            </div>
          )}

          {isOptimizing && (
            <div className="flex flex-col items-center justify-center py-16 space-y-5">
              <CircleNotch className="w-12 h-12 animate-spin text-indigo-500" weight="bold" />
              <div className="text-center space-y-2">
                <h3 className="font-black text-lg text-white">최적의 설정값을 찾고 있습니다</h3>
                <p className="text-sm text-white/40">총 {nTrials}가지 조합을 자동으로 테스트하고 있습니다. 잠시만 기다려주세요.</p>
              </div>
              <button
                type="button"
                onClick={handleCancel}
                className="mt-2 px-6 py-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/20 text-red-400 text-sm font-black uppercase tracking-widest transition-all border border-red-500/20"
              >
                최적화 중단
              </button>
            </div>
          )}

          {error && (
            <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-xl flex gap-3 text-red-400">
              <WarningCircle className="w-5 h-5 shrink-0" weight="fill" />
              <div className="space-y-1">
                <h4 className="text-sm font-bold">최적화 실패</h4>
                <p className="text-xs">{error}</p>
              </div>
            </div>
          )}

          {result && !isOptimizing && (
            <div className="space-y-5">

              {/* 핵심 지표 — 가장 먼저 */}
              {result.best_metrics && (
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-white/[0.04] border border-white/8 rounded-2xl p-4 text-center">
                    <div className="text-[11px] font-bold text-white/40 mb-2 tracking-wide">총 수익</div>
                    <div className="font-black text-lg text-white leading-none">{result.best_metrics.totalProfit?.toLocaleString()}<span className="text-sm font-medium text-white/50 ml-1">원</span></div>
                  </div>
                  <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-2xl p-4 text-center">
                    <div className="text-[11px] font-bold text-indigo-400/60 mb-2 tracking-wide">CAGR</div>
                    <div className="font-black text-2xl text-indigo-300 leading-none">{result.best_metrics.cagr?.toFixed(1)}<span className="text-sm font-medium ml-0.5">%</span></div>
                  </div>
                  <div className="bg-white/[0.04] border border-white/8 rounded-2xl p-4 text-center">
                    <div className="text-[11px] font-bold text-white/40 mb-2 tracking-wide">최대 낙폭</div>
                    <div className="font-black text-lg text-red-400 leading-none">-{result.best_metrics.maxDrawdown?.toFixed(1)}<span className="text-sm font-medium ml-0.5">%</span></div>
                  </div>
                </div>
              )}


              {/* AI 분석 리포트 */}
              {result.report && (
                <div className="rounded-2xl border border-white/8 overflow-hidden">
                  <div className="px-4 py-3 border-b border-white/5 bg-white/[0.02]">
                    <span className="text-xs font-bold text-white/60 tracking-wide flex items-center gap-2">
                      <Sparkle className="w-3.5 h-3.5 text-indigo-400" weight="fill" /> AI 분석 리포트
                    </span>
                  </div>
                  <div className="p-5 prose prose-sm prose-invert max-w-none
                    prose-headings:text-white prose-headings:font-bold prose-headings:text-sm prose-headings:mt-4 prose-headings:mb-2
                    prose-p:text-white/60 prose-p:leading-relaxed prose-p:text-sm
                    prose-strong:text-white prose-strong:font-semibold
                    prose-li:text-white/60 prose-li:text-sm
                    prose-ul:my-2 prose-ol:my-2
                    [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                    <ReactMarkdown components={{ table: () => null, thead: () => null, tbody: () => null, tr: () => null, th: () => null, td: () => null }}>{result.report}</ReactMarkdown>
                  </div>
                </div>
              )}

            </div>
          )}
        </div>

        <div className="p-6 border-t border-white/5 bg-white/[0.01] flex justify-end gap-3">
          {!result && !isOptimizing && (
            <>
              <button 
                type="button" 
                onClick={() => onOpenChange(false)}
                className="px-6 py-3 rounded-xl bg-white/5 hover:bg-white/10 text-white text-sm font-black uppercase tracking-widest transition-all"
              >
                취소
              </button>
              <button 
                onClick={handleOptimize} 
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-black uppercase tracking-widest transition-all shadow-[0_10px_30px_rgba(79,70,229,0.3)] active:scale-[0.98]"
              >
                <Sparkle className="w-4 h-4" weight="fill" /> 최적화 시작
              </button>
            </>
          )}

          {result && !isOptimizing && (
            <>
              <button 
                type="button" 
                onClick={() => setResult(null)}
                className="px-6 py-3 rounded-xl bg-white/5 hover:bg-white/10 text-white text-sm font-black uppercase tracking-widest transition-all"
              >
                다시 시도
              </button>
              <button 
                onClick={() => {
                  if (result.best_parameters) {
                    onApplyParameters(result.best_parameters);
                  }
                  onOpenChange(false);
                }}
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-[#4B9FFF] hover:bg-blue-400 text-white text-sm font-black uppercase tracking-widest transition-all shadow-[0_10px_30px_rgba(59,130,246,0.3)] active:scale-[0.98]"
              >
                전략에 적용하기 <ArrowRight className="w-4 h-4" weight="bold" />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
