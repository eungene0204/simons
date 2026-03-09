"use client";

import { useState, useEffect } from "react";
import { X, CheckCircle, Sliders, Question } from "phosphor-react";
import { Condition } from "@/types/strategy";
import { signalBlocks } from "@/lib/strategy-blocks";

interface ConditionBlockEditorProps {
  condition: Condition;
  onSave: (condition: Condition) => void;
  onCancel: () => void;
}

export default function ConditionBlockEditor({
  condition,
  onSave,
  onCancel,
}: ConditionBlockEditorProps) {
  const [params, setParams] = useState(condition.params);
  const [weight, setWeight] = useState(condition.weight || 1);
  const block = signalBlocks[condition.id];

  useEffect(() => {
    setParams(condition.params);
    setWeight(condition.weight || 1);
  }, [condition]);

  const handleParamChange = (key: string, value: any) => {
    setParams({ ...params, [key]: value });
  };

  const handleSave = () => {
    onSave({
      ...condition,
      params,
      weight,
    });
  };

  if (!block) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[100]">
      <div className="bg-[#0d0d0d] rounded-2xl border border-white/10 w-full max-w-md mx-4 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-6 border-b border-white/5 bg-white/[0.01]">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-3.5">
              <Sliders size={24} className="text-[rgb(59,134,247)]" />
              <h3 className="text-sm font-black text-white/90 uppercase tracking-tight">속성</h3>
            </div>
            <button
              onClick={onCancel}
              className="p-1.5 hover:bg-white/5 rounded-xl transition-colors text-white/20 hover:text-white"
            >
              <X size={16} />
            </button>
          </div>
          
          <div className="bg-black/40 rounded-2xl p-4 border border-white/5 shadow-inner">
            <h4 className="text-sm font-black text-white mb-2 uppercase tracking-tight">{block.name}</h4>
            <p className="text-[11px] text-white/50 font-medium leading-relaxed">
              {block.description}
            </p>
          </div>
        </div>

        {/* Parameters */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-6">
          {Object.entries(block.paramSchema).map(([key, schema]) => {
            const currentValue = params[key] !== undefined ? params[key] : block.defaultParams[key];

            return (
              <div key={key} className="space-y-2.5 group">
                <div className="flex items-center justify-between px-1">
                  <div className="flex items-center gap-1.5">
                    <label className="text-sm font-black text-white/50 uppercase tracking-[0.15em]">
                      {schema.label}
                    </label>
                    {schema.tooltip && (
                      <div className="relative group/tooltip">
                        <Question
                          size={13}
                          className="text-white/30 hover:text-blue-400 cursor-help transition-colors"
                        />
                        <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 hidden group-hover/tooltip:block z-[110] w-48">
                          <div className="bg-gray-900/95 backdrop-blur-md text-white text-[10px] p-2 rounded-lg border border-white/10 shadow-2xl leading-relaxed">
                            {schema.tooltip}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                  {schema.type === "number" && (
                    <span className="text-sm font-black text-[rgb(59,134,247)] tabular-nums">
                      {currentValue}{schema.suffix}
                    </span>
                  )}
                </div>

                {schema.type === "number" && (
                  <div className="flex items-center px-3 py-3.5 bg-black/40 border border-white/5 rounded-xl group-hover:border-white/10 transition-all shadow-inner">
                    <input
                      type="number"
                      min={schema.min}
                      max={schema.max}
                      step={schema.step || 1}
                      value={currentValue}
                      onChange={(e) =>
                        handleParamChange(key, parseFloat(e.target.value))
                      }
                      className="flex-1 bg-transparent text-sm font-black text-white outline-none tabular-nums placeholder:text-white/[0.05]"
                    />
                    {schema.suffix && (
                      <span className="text-xs font-black text-white/20 uppercase tracking-widest ml-2">
                        {schema.suffix}
                      </span>
                    )}
                  </div>
                )}

                {schema.type === "select" && (
                  <div className="relative">
                    <select
                      value={currentValue}
                      onChange={(e) => handleParamChange(key, e.target.value)}
                      className="w-full px-3 py-3 bg-black/40 border border-white/5 rounded-xl text-sm font-black text-white outline-none appearance-none cursor-pointer group-hover:border-white/10 transition-all"
                      style={{ 
                        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='rgba(255,255,255,0.3)' stroke-width='3'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`, 
                        backgroundRepeat: 'no-repeat', 
                        backgroundPosition: 'right 12px center' 
                      }}
                    >
                      {schema.options?.map((opt) => (
                        <option key={opt.value} value={opt.value} className="bg-[#0d0d0d] text-white">
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {schema.type === "boolean" && (
                  <label className="flex items-center justify-between px-3 py-3.5 bg-black/40 border border-white/5 rounded-xl cursor-pointer group-hover:border-white/10 transition-all">
                    <span className="text-sm font-black text-white/70 uppercase tracking-widest">활성화</span>
                    <input
                      type="checkbox"
                      checked={currentValue || false}
                      onChange={(e) => handleParamChange(key, e.target.checked)}
                      className="w-5 h-5 accent-[rgb(59,134,247)] cursor-pointer"
                    />
                  </label>
                )}
              </div>
            );
          })}

          {/* Weight for weighted sum */}
          {(condition.type === "indicator" || condition.type === "flow") && (
            <div className="space-y-2.5 group pt-4 border-t border-white/5">
              <div className="flex items-center justify-between px-1">
                <label className="text-sm font-black text-white/50 uppercase tracking-[0.15em]">가중치</label>
                <span className="text-sm font-black text-blue-400">{weight}</span>
              </div>
              <div className="flex items-center px-3 py-3.5 bg-black/40 border border-white/5 rounded-xl group-hover:border-white/10 transition-all shadow-inner">
                <input
                  type="number"
                  min={0}
                  max={10}
                  step={0.1}
                  value={weight}
                  onChange={(e) => setWeight(parseFloat(e.target.value))}
                  className="flex-1 bg-transparent text-sm font-black text-white outline-none tabular-nums"
                />
              </div>
              <p className="text-[10px] text-white/20 font-medium px-1">가중치 합계(Weighted Sum) 사용 시 반영됩니다.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 bg-white/[0.01] border-t border-white/5 space-y-3">
          <button
            onClick={handleSave}
            className="w-full py-4 rounded-xl bg-[rgb(59,134,247)] text-white text-xs font-black uppercase tracking-widest hover:bg-[#4B9FFF] transition-all shadow-xl shadow-blue-500/10 active:scale-[0.98] flex items-center justify-center gap-2"
          >
            <CheckCircle size={18} weight="bold" />
            저장하기
          </button>
          <button
            onClick={onCancel}
            className="w-full py-3 rounded-xl text-white/20 text-xs font-black uppercase tracking-widest hover:text-white/60 hover:bg-white/5 transition-all"
          >
            취소
          </button>
        </div>
      </div>
    </div>
  );
}

