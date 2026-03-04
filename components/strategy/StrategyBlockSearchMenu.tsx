"use client";

import { useState, useMemo } from "react";
import { 
  MagnifyingGlass, 
  X,
  Sparkle,
  Sliders,
  ShieldWarning,
  Cpu
} from "phosphor-react";
import { signalBlocks } from "@/lib/strategy-blocks";

interface StrategyBlockSearchMenuProps {
  onSelect: (blockIds: string[]) => void;
  onClose: () => void;
  manuallyHiddenBlockIds: string[];
}

export default function StrategyBlockSearchMenu({ onSelect, onClose, manuallyHiddenBlockIds }: StrategyBlockSearchMenuProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const filteredBlocks = useMemo(() => {
    const term = searchTerm.toLowerCase();
    return Object.values(signalBlocks)
      .filter((block) => block.hidden || manuallyHiddenBlockIds.includes(block.id))
      .filter(
        (block) =>
          block.name.toLowerCase().includes(term) ||
          block.description.toLowerCase().includes(term)
      );
  }, [searchTerm, manuallyHiddenBlockIds]);

  const toggleBlock = (id: string) => {
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const categoryLabels: Record<string, string> = {
    indicator: "매매 시그널",
    flow: "매매 시그널",
    risk: "리스크",
    ml: "AI",
    filter: "종목 필터",
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
              <MagnifyingGlass className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h3 className="text-base font-black text-white uppercase tracking-wider">블록 검색</h3>
              <p className="text-[10px] text-gray-500 font-medium">전략에 사용될 지표나 조건을 검색할 수 있습니다 (복수 선택 가능)</p>
            </div>
          </div>
          <button 
            onClick={onClose} 
            className="p-2 text-gray-500 hover:text-white hover:bg-white/5 rounded-full transition-all"
          >
            <X className="w-6 h-6" />
          </button>
        </div>
        
        <div className="p-4 bg-[#161616] border-b border-gray-800/20">
          <div className="relative group">
            <MagnifyingGlass className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500 transition-colors group-focus-within:text-blue-400" />
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
            filteredBlocks.map((block) => {
              const isSelected = selectedIds.includes(block.id);
              return (
                <div
                  key={block.id}
                  onClick={() => toggleBlock(block.id)}
                  className={`w-full text-left p-4 rounded-xl transition-all border flex items-start gap-4 cursor-pointer group ${
                    isSelected 
                      ? "bg-blue-600/10 border-blue-500/30" 
                      : "hover:bg-white/5 border-transparent hover:border-gray-800/50"
                  }`}
                >
                  <div className="mt-1 flex items-center justify-center">
                    <div className={`w-5 h-5 rounded-md border-2 transition-all flex items-center justify-center ${
                      isSelected 
                        ? "bg-blue-600 border-blue-600 shadow-[0_0_10px_rgba(37,99,235,0.4)]" 
                        : "border-gray-700 group-hover:border-gray-500"
                    }`}>
                      {isSelected && <X className="w-3.5 h-3.5 text-white stroke-[3px]" />}
                    </div>
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className={`text-sm font-bold transition-colors ${isSelected ? "text-blue-400" : "text-gray-200 group-hover:text-white"}`}>
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
                </div>
              );
            })
          ) : (
            <div className="py-16 text-center">
              <div className="w-16 h-16 bg-gray-800/20 rounded-full flex items-center justify-center mx-auto mb-4 border border-gray-800/50">
                <MagnifyingGlass className="w-8 h-8 text-gray-700" />
              </div>
              <p className="text-sm text-gray-500 font-bold">검색 결과가 없습니다.</p>
              <p className="text-xs text-gray-600 mt-1">다른 검색어를 입력해 보세요.</p>
            </div>
          )}
        </div>

        {selectedIds.length > 0 && (
          <div className="p-4 border-t border-gray-800 bg-[#1a1a1a] rounded-b-2xl flex items-center justify-center">
            <button
              onClick={() => onSelect(selectedIds)}
              className="px-10 py-3 bg-blue-600 hover:bg-blue-500 text-white text-sm font-black rounded-xl transition-all shadow-lg shadow-blue-600/20 flex items-center gap-2 animate-in fade-in slide-in-from-bottom-2 duration-300"
            >
              <span>{selectedIds.length}개의 블록 추가하기</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
