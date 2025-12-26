"use client";

import { useState, useMemo } from "react";
import { 
  MagnifyingGlassIcon, 
  XMarkIcon,
  SparklesIcon,
  AdjustmentsHorizontalIcon,
  ShieldExclamationIcon,
  CpuChipIcon
} from "@heroicons/react/24/outline";
import { signalBlocks } from "@/lib/strategy-blocks";

interface StrategyBlockSearchMenuProps {
  onSelect: (blockId: string) => void;
  onClose: () => void;
  manuallyHiddenBlockIds: string[];
}

export default function StrategyBlockSearchMenu({ onSelect, onClose, manuallyHiddenBlockIds }: StrategyBlockSearchMenuProps) {
  const [searchTerm, setSearchTerm] = useState("");

  const filteredBlocks = useMemo(() => {
    const term = searchTerm.toLowerCase();
    return Object.values(signalBlocks)
      .filter((block) => block.hidden || manuallyHiddenBlockIds.includes(block.id))
      .filter(
        (block) =>
          block.name.toLowerCase().includes(term) ||
          block.description.toLowerCase().includes(term)
      );
  }, [searchTerm]);

  const categoryLabels: Record<string, string> = {
    indicator: "시그널",
    flow: "시그널",
    risk: "리스크",
    ml: "AI",
    filter: "필터",
  };

  return (
    <div 
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div 
        className="w-full max-w-xl bg-[#161616] border border-gray-800 rounded-2xl shadow-[0_30px_60px_rgba(0,0,0,0.6)] flex flex-col max-h-[80vh] animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 border-b border-gray-800 flex items-center justify-between bg-[#1a1a1a] rounded-t-2xl">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <MagnifyingGlassIcon className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h3 className="text-base font-black text-white uppercase tracking-wider">블록 검색</h3>
              <p className="text-[10px] text-gray-500 font-medium">전략에 사용될 지표나 조건을 검색하세요</p>
            </div>
          </div>
          <button 
            onClick={onClose} 
            className="p-2 text-gray-500 hover:text-white hover:bg-white/5 rounded-full transition-all"
          >
            <XMarkIcon className="w-6 h-6" />
          </button>
        </div>
        
        <div className="p-4 bg-[#161616] border-b border-gray-800/20">
          <div className="relative group">
            <MagnifyingGlassIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500 transition-colors group-focus-within:text-blue-400" />
            <input
              autoFocus
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="무엇을 찾으시나요? (예: RSI, 이동평균, 외국인 매수 등)"
              className="w-full bg-[#151515] border border-gray-800 rounded-xl pl-12 pr-4 py-4 text-sm text-white placeholder:text-gray-600 focus:outline-none focus:border-blue-500/50 focus:ring-4 focus:ring-blue-500/5 transition-all"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1.5 custom-scrollbar min-h-[300px] bg-[#161616]">
          {filteredBlocks.length > 0 ? (
            filteredBlocks.map((block) => (
              <button
                key={block.id}
                onClick={() => onSelect(block.id)}
                className="w-full text-left p-4 rounded-xl hover:bg-white/5 group transition-all border border-transparent hover:border-gray-800/50 flex items-start gap-4"
              >
                <div className="mt-1 p-2.5 rounded-lg bg-gray-800/30 text-gray-500 group-hover:text-blue-400 group-hover:bg-blue-500/10 transition-all shrink-0">
                  {block.category === "indicator" || block.category === "flow" ? (
                    <SparklesIcon className="w-4 h-4" />
                  ) : block.category === "filter" ? (
                    <AdjustmentsHorizontalIcon className="w-4 h-4" />
                  ) : block.category === "risk" ? (
                    <ShieldExclamationIcon className="w-4 h-4" />
                  ) : block.category === "ml" ? (
                    <CpuChipIcon className="w-4 h-4" />
                  ) : (
                    <MagnifyingGlassIcon className="w-4 h-4 opacity-50" />
                  )}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm font-bold text-gray-200 group-hover:text-white transition-colors">
                      {block.name}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-tight ${
                      block.category === 'indicator' || block.category === 'flow' ? 'bg-red-500/10 text-red-400' :
                      block.category === 'filter' ? 'bg-blue-500/10 text-blue-400' :
                      block.category === 'risk' ? 'bg-orange-500/10 text-orange-400' :
                      block.category === 'ml' ? 'bg-emerald-500/10 text-emerald-400' :
                      'bg-gray-800 text-gray-400'
                    }`}>
                      {categoryLabels[block.category] || block.category}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 group-hover:text-gray-400 leading-relaxed font-medium">
                    {block.description}
                  </p>
                </div>
              </button>
            ))
          ) : (
            <div className="py-16 text-center">
              <div className="w-16 h-16 bg-gray-800/20 rounded-full flex items-center justify-center mx-auto mb-4 border border-gray-800/50">
                <MagnifyingGlassIcon className="w-8 h-8 text-gray-700" />
              </div>
              <p className="text-sm text-gray-500 font-bold">검색 결과가 없습니다.</p>
              <p className="text-xs text-gray-600 mt-1">다른 검색어를 입력해 보세요.</p>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-800 bg-[#1a1a1a] rounded-b-2xl flex items-center justify-between">
          <div className="flex items-center gap-4">
             <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-red-400" />
                <span className="text-[10px] text-gray-500 font-bold tracking-tight">시그널</span>
             </div>
             <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-blue-400" />
                <span className="text-[10px] text-gray-500 font-bold tracking-tight">필터</span>
             </div>
             <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-orange-400" />
                <span className="text-[10px] text-gray-500 font-bold tracking-tight">리스크</span>
             </div>
             <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-[10px] text-gray-500 font-bold tracking-tight">AI</span>
             </div>
          </div>
          <p className="text-[10px] text-gray-600 font-black italic tracking-tight">
            블록을 클릭하면 보관함에 추가됩니다.
          </p>
        </div>
      </div>
    </div>
  );
}
