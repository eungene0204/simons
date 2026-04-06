"use client";

import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  X, 
  Info, 
  ArrowsClockwise,
  WarningCircle,
  ChartBar,
  Clock
} from "phosphor-react";

interface XAIModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  date: string;
}

interface XAEResult {
  symbol: string;
  date: string;
  status: string;
  attention_map: number[];
  shap_matrix: number[][]; // (60, 6)
  feature_importance_directional: number[];
  features: string[];
  error?: string;
}

const FEATURE_LABELS: Record<string, string> = {
  ret_open: "시가 수익률",
  ret_high: "고가 수익률",
  ret_low: "저가 수익률",
  ret_close: "종가 수익률",
  ret_volume: "거래량 변화",
  rsi_14: "RSI (14)",
};

export default function XAIModal({ isOpen, onClose, symbol, date }: XAIModalProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<XAEResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && symbol && date) {
      fetchXAI();
    }
  }, [isOpen, symbol, date]);

  const fetchXAI = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/backtest/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, date })
      });
      const data = await response.json();
      if (response.ok) {
        setResult(data);
      } else {
        setError(data.error || 'Failed to load XAI analysis');
      }
    } catch (err) {
      setError('Network error while fetching analysis');
    } finally {
      setLoading(false);
    }
  };

  const getShapColor = (val: number) => {
    // SHAP values are typically small. 
    // Red for positive (increased probability), Blue for negative (decreased probability)
    const intensity = Math.min(Math.abs(val) * 10, 1);
    if (val > 0) return `rgba(239, 68, 68, ${intensity})`; // main-red
    return `rgba(55, 122, 244, ${intensity})`; // main-blue
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center p-4">
      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onClose}
              className="absolute inset-0 bg-black/80 backdrop-blur-sm pointer-events-auto"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="relative w-full max-w-6xl bg-[#111] border border-white/10 rounded-3xl overflow-hidden shadow-[0_32px_64px_-12px_rgba(0,0,0,0.8)] flex flex-col max-h-[75vh] pointer-events-auto"
            >
            {/* Header - Drag Handle Area */}
            <div className="flex items-center justify-between px-6 py-3 border-b border-white/5 bg-[#161616] transition-colors">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-main-blue/10 rounded-xl">
                  <ChartBar className="w-5 h-5 text-main-blue" />
                </div>
                <div>
                  <h3 className="text-lg font-black text-white">AI 의사결정 분석 (XAI)</h3>
                  <p className="text-xs text-gray-500 font-bold uppercase tracking-widest">
                    {symbol} • {date} • 가중치 분석
                  </p>
                </div>
              </div>
              <button 
                onClick={onClose}
                className="p-2 hover:bg-white/5 rounded-full transition-colors"
              >
                <X className="w-6 h-6 text-gray-400" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-5 bg-[#0a0a0a] custom-scrollbar">
              {loading ? (
                <div className="h-96 flex flex-col items-center justify-center space-y-4">
                   <motion.div
                     animate={{ rotate: 360 }}
                     transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                   >
                     <ArrowsClockwise className="w-10 h-10 text-main-blue/50" />
                   </motion.div>
                   <div className="text-center">
                     <p className="text-white font-bold">모델 해석 중...</p>
                     <p className="text-xs text-gray-500 mt-1">SHAP 연산을 위해 약 30-60초가 소요될 수 있습니다.</p>
                   </div>
                </div>
              ) : error ? (
                <div className="h-96 flex flex-col items-center justify-center text-center space-y-3">
                   <WarningCircle className="w-12 h-12 text-main-red/40" />
                   <div>
                     <p className="text-white font-bold">{error}</p>
                     <p className="text-xs text-gray-500 mt-2">훈련 데이터셋에 해당 종목 정보가 부족할 수 있습니다.</p>
                   </div>
                   <button 
                     onClick={fetchXAI}
                     className="px-4 py-2 bg-white/5 hover:bg-white/10 text-white text-sm font-bold rounded-xl transition-all"
                   >
                     재시도
                   </button>
                </div>
              ) : result ? (
                <div className="space-y-5 animate-in fade-in duration-500">
                   {/* 1. Summary Cards */}
                   <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                     <div className="bg-[#161616] p-4 rounded-2xl border border-white/5">
                        <span className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-2">분석 범위</span>
                        <div className="flex items-end gap-2">
                           <span className="text-2xl font-black text-white">60일</span>
                           <span className="text-xs text-gray-500 mb-1 font-bold">Lookback Period</span>
                        </div>
                     </div>
                     <div className="bg-[#161616] p-4 rounded-2xl border border-white/5">
                        <span className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-2">설명 모델</span>
                        <div className="flex items-end gap-2">
                           <span className="text-2xl font-black text-main-blue">KernelSHAP</span>
                           <span className="text-xs text-gray-500 mb-1 font-bold">Hybrid Model</span>
                        </div>
                     </div>
                     <div className="bg-[#161616] p-4 rounded-2xl border border-white/5">
                        <span className="text-[10px] text-gray-500 font-black uppercase tracking-widest block mb-2">분석 신뢰도</span>
                        <div className="flex items-end gap-2">
                           <span className="text-2xl font-black text-main-green">High</span>
                           <span className="text-xs text-gray-500 mb-1 font-bold">nsamples=1000</span>
                        </div>
                     </div>
                   </div>

                   {/* 2. SHAP Matrix Heatmap */}
                   <div className="bg-[#111]/50 p-4 rounded-2xl border border-white/5">
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="text-sm font-black text-white flex items-center gap-2">
                          <Clock className="w-4 h-4 text-gray-500" /> 시계열 특징 기여도 (SHAP Heatmap)
                        </h4>
                        <div className="flex items-center gap-4 text-[10px] font-bold">
                           <div className="flex items-center gap-1.5">
                              <div className="w-2 h-2 rounded-full bg-main-blue" />
                              <span className="text-gray-500">하락 요인</span>
                           </div>
                           <div className="flex items-center gap-1.5">
                              <div className="w-2 h-2 rounded-full bg-main-red" />
                              <span className="text-gray-500">상승 요인</span>
                           </div>
                        </div>
                      </div>
                      
                      <div className="relative bg-[#111] p-1 rounded-xl border border-white/5">
                        {/* Feature Names Left Axis */}
                        <div className="flex">
                          <div className="w-24 flex-none py-8 flex flex-col justify-between">
                             {result.features.map(f => (
                               <span key={f} className="text-[9px] font-bold text-gray-500 text-right pr-3 truncate">
                                 {FEATURE_LABELS[f] || f}
                               </span>
                             ))}
                          </div>
                          
                          {/* Matrix Grid */}
                          <div className="flex-1 overflow-x-auto pb-2 custom-scrollbar">
                             <div className="w-[800px] h-40 flex">
                                {result.shap_matrix.map((dayShap, dayIdx) => (
                                  <div key={dayIdx} className="flex-1 flex flex-col">
                                    {dayShap.map((val, featIdx) => (
                                      <div 
                                        key={featIdx}
                                        className="flex-1 m-[1px] rounded-[1px] hover:ring-1 hover:ring-white/50 transition-all cursor-crosshair"
                                        style={{ backgroundColor: getShapColor(val) }}
                                        title={`Day -${59-dayIdx} | SHAP: ${val.toFixed(4)}`}
                                      />
                                    ))}
                                  </div>
                                ))}
                             </div>
                             <div className="flex justify-between mt-2 px-1">
                                <span className="text-[10px] text-gray-600 font-mono">-60일</span>
                                <span className="text-[10px] text-gray-600 font-mono">현재 시점</span>
                             </div>
                          </div>
                        </div>
                      </div>
                   </div>

                   {/* 3. Attention & Global Importance */}
                   <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                      {/* Attention Map */}
                      <div>
                        <h4 className="text-[11px] font-black text-white mb-3 flex items-center gap-2">
                           <Info className="w-4 h-4 text-gray-400" /> 모델 관심도 (Attention Map)
                        </h4>
                        <div className="bg-[#111] p-3 rounded-xl border border-white/5 h-32 flex items-end gap-[1px]">
                           {result.attention_map.map((v, i) => (
                             <div 
                               key={i} 
                               className="flex-1 bg-main-blue/30 hover:bg-main-blue transition-colors rounded-t-[1px]"
                               style={{ height: `${Math.min(v * 400, 100)}%` }}
                               title={`Attention: ${v.toFixed(4)}`}
                             />
                           ))}
                        </div>
                        <p className="text-[10px] text-gray-600 mt-2 italic">* Transformer 모델이 예측 시 어떤 과거 시점에 더 주목했는지 나타냅니다.</p>
                      </div>

                      {/* Feature Importance Bar Chart */}
                      <div>
                        <h4 className="text-sm font-black text-white mb-4 flex items-center gap-2">
                           <ChartBar className="w-4 h-4 text-gray-500" /> 종합 특징 중요도 (Global Summary)
                        </h4>
                        <div className="space-y-3">
                           {result.features.map((f, i) => {
                             const val = result.feature_importance_directional[i];
                             const maxVal = Math.max(...result.feature_importance_directional.map(Math.abs));
                             const width = (Math.abs(val) / (maxVal || 1)) * 100;
                             
                             return (
                               <div key={f} className="space-y-1">
                                 <div className="flex justify-between text-[10px] font-bold">
                                   <span className="text-gray-400">{FEATURE_LABELS[f] || f}</span>
                                   <span className={val > 0 ? "text-main-red" : "text-main-blue"}>
                                     {val > 0 ? '+' : ''}{val.toFixed(4)}
                                   </span>
                                 </div>
                                 <div className="h-2 bg-white/5 rounded-full overflow-hidden relative">
                                    <motion.div 
                                      initial={{ width: 0 }}
                                      animate={{ width: `${width}%` }}
                                      transition={{ duration: 1, ease: "circOut" }}
                                      className={`h-full rounded-full ${val > 0 ? 'bg-main-red' : 'bg-main-blue'}`}
                                    />
                                 </div>
                               </div>
                             );
                           })}
                        </div>
                      </div>
                   </div>
                </div>
              ) : null}
            </div>

            {/* Footer Info */}
            <div className="px-6 py-3 bg-[#161616] border-t border-white/5">
               <div className="flex items-start gap-3 bg-white/[0.03] p-3 rounded-xl border border-white/10">
                  <Info className="w-5 h-5 text-main-blue mt-0.5 flex-none" />
                  <p className="text-xs text-gray-400 leading-relaxed font-medium">
                    <span className="text-main-blue font-black mr-1">분석 안내:</span>
                    SHAP 값은 해당 시점의 특정 데이터가 AI 모델의 예측 확률(Long 확률)을 얼마나 변화시켰는지 나타냅니다. 
                    붉은색은 매수 확률을 높인 긍정적 요인, 푸른색은 확률을 낮춘 부정적 요인입니다.
                  </p>
               </div>
            </div>
          </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
