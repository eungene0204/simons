"use client";

import { Fragment } from "react";
import {
  XMarkIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  InformationCircleIcon,
  PlusIcon,
  MagnifyingGlassIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
  CubeIcon,
  AdjustmentsHorizontalIcon,
  SparklesIcon,
  ShieldExclamationIcon,
  CpuChipIcon,
  ChartBarIcon,
  ArrowPathIcon,
  BanknotesIcon,
  ChartPieIcon,
  EllipsisHorizontalIcon,
  CursorArrowRaysIcon,
  Squares2X2Icon
} from "@heroicons/react/24/outline";
import { CanvasBlock, LogicOperator, ConditionType } from "@/types/strategy";
import { signalBlocks } from "@/lib/strategy-blocks";
import StrategyBlockSearchMenu from "../StrategyBlockSearchMenu";

interface Step2ConditionsProps {
  canvasBlocks: CanvasBlock[];
  setCanvasBlocks: React.Dispatch<React.SetStateAction<CanvasBlock[]>>;
  selectedBlock: CanvasBlock | null;
  setSelectedBlock: React.Dispatch<React.SetStateAction<CanvasBlock | null>>;
  activeParamTab: 'block' | 'global';
  setActiveParamTab: React.Dispatch<React.SetStateAction<'block' | 'global'>>;
  entryLogic: LogicOperator;
  setEntryLogic: React.Dispatch<React.SetStateAction<LogicOperator>>;
  exitLogic: LogicOperator;
  setExitLogic: React.Dispatch<React.SetStateAction<LogicOperator>>;
  unlockedBlockIds: string[];
  setUnlockedBlockIds: React.Dispatch<React.SetStateAction<string[]>>;
  manuallyHiddenBlockIds: string[];
  setManuallyHiddenBlockIds: React.Dispatch<React.SetStateAction<string[]>>;
  customBlockOrder: Record<string, string[]>;
  setCustomBlockOrder: React.Dispatch<React.SetStateAction<Record<string, string[]>>>;
  customCategoryOrder: string[];
  setCustomCategoryOrder: React.Dispatch<React.SetStateAction<string[]>>;
  hoveredInfo: { id: string, rect: DOMRect } | null;
  setHoveredInfo: React.Dispatch<React.SetStateAction<{ id: string, rect: DOMRect } | null>>;
  hoveredParam: { label: string, tooltip: string, rect: DOMRect } | null;
  setHoveredParam: React.Dispatch<React.SetStateAction<{ label: string, tooltip: string, rect: DOMRect } | null>>;
  hoveredEditIcon: { label: string, rect: DOMRect } | null;
  setHoveredEditIcon: React.Dispatch<React.SetStateAction<{ label: string, rect: DOMRect } | null>>;
  isSearchMenuOpen: boolean;
  setIsSearchMenuOpen: React.Dispatch<React.SetStateAction<boolean>>;
  isLibraryManagementOpen: boolean;
  setIsLibraryManagementOpen: React.Dispatch<React.SetStateAction<boolean>>;
  activeMgmtCategory: string;
  setActiveMgmtCategory: React.Dispatch<React.SetStateAction<string>>;
  draggedModalItemIndex: number | null;
  setDraggedModalItemIndex: React.Dispatch<React.SetStateAction<number | null>>;
  draggedCategoryIndex: number | null;
  setDraggedCategoryIndex: React.Dispatch<React.SetStateAction<number | null>>;
  openSignalGroups: string[];
  setOpenSignalGroups: React.Dispatch<React.SetStateAction<string[]>>;
  savedFeedback: string | null;
  setSavedFeedback: React.Dispatch<React.SetStateAction<string | null>>;
  canvasRef: React.RefObject<HTMLDivElement>;
  canvasWidth: number;
  onNext: () => void;
  onPrev: () => void;
  handleAddBlock: (blockId: string, blockType?: string) => void;
  handleRemoveBlockFromBin: (blockId: string, e: React.MouseEvent) => void;
}

export default function Step2Conditions({
  canvasBlocks,
  setCanvasBlocks,
  selectedBlock,
  setSelectedBlock,
  activeParamTab,
  setActiveParamTab,
  entryLogic,
  setEntryLogic,
  exitLogic,
  setExitLogic,
  unlockedBlockIds,
  setUnlockedBlockIds,
  manuallyHiddenBlockIds,
  setManuallyHiddenBlockIds,
  customBlockOrder,
  setCustomBlockOrder,
  customCategoryOrder,
  setCustomCategoryOrder,
  hoveredInfo,
  setHoveredInfo,
  hoveredParam,
  setHoveredParam,
  hoveredEditIcon,
  setHoveredEditIcon,
  isSearchMenuOpen,
  setIsSearchMenuOpen,
  isLibraryManagementOpen,
  setIsLibraryManagementOpen,
  activeMgmtCategory,
  setActiveMgmtCategory,
  draggedModalItemIndex,
  setDraggedModalItemIndex,
  draggedCategoryIndex,
  setDraggedCategoryIndex,
  openSignalGroups,
  setOpenSignalGroups,
  savedFeedback,
  setSavedFeedback,
  canvasRef,
  canvasWidth,
  onNext,
  onPrev,
  handleAddBlock,
  handleRemoveBlockFromBin,
}: Step2ConditionsProps) {
  // Original calculations moved here for internal sizing
  const blocksPerRow = canvasWidth > 720 ? 4 : Math.max(1, Math.floor((canvasWidth - 30) / 185));
  const totalGridWidth = blocksPerRow * 185 - 65;
  const sidePadding = Math.max(15, (canvasWidth - totalGridWidth) / 2);
  const numRows = Math.ceil(canvasBlocks.length / blocksPerRow);
  const canvasMinHeight = Math.max(600, 100 + numRows * 135 + 100);

  const handleModalItemDragStart = (index: number) => {
    setDraggedModalItemIndex(index);
  };

  const handleModalItemDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleModalItemDrop = (category: string, targetIndex: number, blocks: any[]) => {
    if (draggedModalItemIndex === null) return;
    const newBlocks = [...blocks];
    const item = newBlocks.splice(draggedModalItemIndex, 1)[0];
    newBlocks.splice(targetIndex, 0, item);
    const newBlockIds = newBlocks.map(b => b.id);
    setCustomBlockOrder(prev => ({ ...prev, [category]: newBlockIds }));
    setDraggedModalItemIndex(null);
  };

  const groupedSignalLibrary = {
    filter: {
      key: "filter",
      label: "종목 필터 블록",
      icon: AdjustmentsHorizontalIcon,
      blocks: Object.values(signalBlocks).filter(
        (b) => b.category === "filter" && 
               (!b.hidden || unlockedBlockIds.includes(b.id)) && 
               !manuallyHiddenBlockIds.includes(b.id)
      ).sort((a, b) => {
        const order = customBlockOrder["filter"] || [];
        const indexA = order.indexOf(a.id);
        const indexB = order.indexOf(b.id);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
      }).map((b) => ({
        id: b.id,
        name: b.name,
        description: b.description,
        blockType: "factor_filters" as const,
      })),
    },
    indicator: {
      key: "indicator",
      label: "매매 시그널 블록",
      icon: SparklesIcon,
      blocks: Object.values(signalBlocks).filter(
        (b) => (b.category === "indicator" || b.category === "flow") && 
               (!b.hidden || unlockedBlockIds.includes(b.id)) && 
               !manuallyHiddenBlockIds.includes(b.id)
      ).sort((a, b) => {
        const order = customBlockOrder["indicator"] || [];
        const indexA = order.indexOf(a.id);
        const indexB = order.indexOf(b.id);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
      }).map((b) => ({
        id: b.id,
        name: b.name,
        description: b.description,
        blockType: b.category,
      })),
    },
    risk: {
      key: "risk",
      label: "리스크 블록",
      icon: ShieldExclamationIcon,
      blocks: Object.values(signalBlocks).filter(
        (b) => b.category === "risk" && 
               (!b.hidden || unlockedBlockIds.includes(b.id)) && 
               !manuallyHiddenBlockIds.includes(b.id)
      ).sort((a, b) => {
        const order = customBlockOrder["risk"] || [];
        const indexA = order.indexOf(a.id);
        const indexB = order.indexOf(b.id);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
      }).map((b) => ({
        id: b.id,
        name: b.name,
        description: b.description,
        blockType: "risk_rules" as const,
      })),
    },
    ml: {
      key: "ml",
      label: "AI 블록",
      icon: CpuChipIcon,
      blocks: Object.values(signalBlocks).filter(
        (b) => b.category === "ml" && 
               (!b.hidden || unlockedBlockIds.includes(b.id)) && 
               !manuallyHiddenBlockIds.includes(b.id)
      ).sort((a, b) => {
        const order = customBlockOrder["ml"] || [];
        const indexA = order.indexOf(a.id);
        const indexB = order.indexOf(b.id);
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
      }).map((b) => ({
        id: b.id,
        name: b.name,
        description: b.description,
        blockType: "ml" as const,
      })),
    },
  } as const;

  return (
    <>
      {/* Left Sidebar */}
      <div className="w-48 bg-[#0f0f0f] relative z-50 flex flex-col shrink-0">
        <div className="flex-1 px-4 py-3 space-y-3">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-black text-white uppercase tracking-wider">조건 블록함</h3>
            <button
              type="button"
              onClick={() => setIsLibraryManagementOpen(true)}
              className="p-1 px-1.5 bg-[#1a1a1a] border border-gray-800 rounded-md text-gray-400 hover:text-white hover:border-gray-600 transition-all flex items-center gap-1 group/mgmt"
            >
              <EllipsisHorizontalIcon className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-3">
            {customCategoryOrder.map((key) => {
              const group = (groupedSignalLibrary as any)[key];
              if (!group) return null;
              const filteredBlocks = group.blocks;
              
              return (
                <Fragment key={group.key}>
                  <div className="rounded-lg bg-[#151515] border border-gray-800/20">
                    <button
                      type="button"
                      onClick={() => setOpenSignalGroups((prev) => 
                        prev.includes(group.key) 
                          ? prev.filter(k => k !== group.key) 
                          : [...prev, group.key]
                      )}
                      className="w-full flex items-center justify-between px-3 py-2.5 text-xs font-black text-gray-400 hover:text-white hover:bg-[#181818] transition-all group/header"
                    >
                      <span className="flex items-center gap-2">
                        <group.icon className="w-4 h-4" />
                        <span>{group.label}</span>
                      </span>
                      <div className="flex items-center gap-1">
                        <ChevronDownIcon className={`w-3.5 h-3.5 transition-transform ${openSignalGroups.includes(group.key) ? "rotate-180" : ""}`} />
                      </div>
                    </button>
                    {openSignalGroups.includes(group.key) && (
                      <div className="px-2 pt-1 pb-3 space-y-1 bg-[#151515]">
                        {filteredBlocks.length === 0 && <div className="text-[10px] text-gray-600 px-3 py-2 italic text-center">결과 없음</div>}
                        {filteredBlocks.map((block: any) => {
                          const blockDef = signalBlocks[block.id];
                          return (
                            <div
                              key={block.id}
                              draggable
                              onDragStart={(e) => {
                                e.dataTransfer.setData("blockId", block.id);
                                e.dataTransfer.setData("blockType", blockDef?.category || "");
                              }}
                              className="group p-2.5 bg-[#1a1a1a] border border-gray-800/50 rounded-lg text-xs font-bold text-gray-400 hover:text-white hover:border-blue-500/30 hover:bg-blue-500/5 cursor-move transition-all flex items-center justify-between"
                            >
                              <span className="truncate pr-2">{block.name}</span>
                              <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                <div 
                                  className="relative p-1"
                                  onMouseEnter={(e) => setHoveredInfo({ id: block.id, rect: e.currentTarget.getBoundingClientRect() })}
                                  onMouseLeave={() => setHoveredInfo(null)}
                                >
                                  <InformationCircleIcon className={`w-4 h-4 transition-colors cursor-help ${hoveredInfo?.id === block.id ? "text-blue-400" : "text-gray-400 hover:text-blue-400"}`} />
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </Fragment>
              );
            })}
          </div>

          <div className="py-3 border-t border-gray-800/30">
            <button
              type="button"
              onClick={() => setIsSearchMenuOpen(!isSearchMenuOpen)}
              className={`w-full flex items-center justify-center gap-2.5 py-3.5 rounded-xl transition-all group ${
                isSearchMenuOpen
                  ? "bg-blue-600 text-white shadow-[0_8px_20px_rgba(37,99,235,0.3)]"
                  : "bg-[#161616] border border-gray-800/50 text-gray-500 hover:text-white hover:border-blue-500/30 hover:bg-blue-500/5"
              }`}
            >
              <MagnifyingGlassIcon className={`w-5 h-5 transition-transform duration-300 ${isSearchMenuOpen ? "rotate-90 text-white" : "text-gray-500 group-hover:text-blue-400"}`} />
              <span className="text-sm font-black uppercase tracking-widest">블록 검색</span>
            </button>
          </div>
        </div>

        <div className="border-t border-gray-800/30 bg-[#0f0f0f] px-3 pt-3 pb-6 flex items-center justify-center">
          <p className="text-[10px] text-gray-600 text-center leading-relaxed font-medium">
            찾고 계신 지표가 없나요? <br />
            <span className="text-blue-500/70 hover:text-blue-400 cursor-pointer underline decoration-dotted underline-offset-4 transition-colors">기능 요청하기</span>
          </p>
        </div>
      </div>

      {/* Center Canvas Area */}
      <div className="flex-1 bg-[#0f0f0f] relative overflow-hidden flex flex-col min-h-full">
        <div 
          ref={canvasRef}
          className="flex-1 relative border border-gray-800 rounded-3xl overflow-hidden mx-3 mb-6 bg-[#0a0a0a]/30"
          style={{ minHeight: canvasMinHeight }}
          onDragOver={(e) => { e.preventDefault(); }}
          onDrop={(e) => {
            e.preventDefault();
            const blockId = e.dataTransfer.getData("blockId");
            const blockType = e.dataTransfer.getData("blockType");
            if (blockId) {
              handleAddBlock(blockId, blockType);
            }
          }}
        >
          <div className="absolute inset-0 pointer-events-none opacity-20" style={{ backgroundImage: "radial-gradient(#4b5563 1px, transparent 1px)", backgroundSize: "20px 20px" }} />
          
          {canvasBlocks.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center p-12 text-center pointer-events-none">
              <div className="max-w-md space-y-4 animate-in fade-in zoom-in duration-700">
                <div className="w-20 h-20 bg-gray-800/20 rounded-full flex items-center justify-center mx-auto border border-gray-700/30 mb-6">
                  <PlusIcon className="w-10 h-10 text-gray-600" />
                </div>
                <h4 className="text-xl font-black text-gray-400">전략 구성을 시작해보세요</h4>
                <p className="text-sm text-gray-500 font-medium leading-relaxed">
                  왼쪽 도구함에서 원하는 지표나 조건을 드래그하여<br />
                  이곳에 놓아주세요. 나만의 매매 전략을 만들 수 있습니다.
                </p>
              </div>
            </div>
          )}

          <div className="absolute inset-0">
            <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
              <defs>
                <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="2" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
                <marker id="arrowhead-red" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                  <polygon points="0 0, 10 3.5, 0 7" fill="#EF4444" />
                </marker>
                <marker id="arrowhead-blue" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                  <polygon points="0 0, 10 3.5, 0 7" fill="#3B82F6" />
                </marker>
                <marker id="arrowhead-gray" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                  <polygon points="0 0, 10 3.5, 0 7" fill="#4B5563" />
                </marker>
              </defs>
              {canvasBlocks.map((block, index) => {
                if (index === canvasBlocks.length - 1) return null;
                const nextBlock = canvasBlocks[index + 1];
                const isEntryOrFilter = (b: CanvasBlock) => b.type === "entry" || b.type === "filter";
                const isExit = (b: CanvasBlock) => b.type === "exit";
                
                let shouldConnect = false;
                let color = "#4B5563";
                let markerId = "arrowhead-gray";

                if (isEntryOrFilter(block) && isEntryOrFilter(nextBlock)) {
                  shouldConnect = entryLogic === "AND";
                  color = "#EF4444";
                  markerId = "arrowhead-red";
                } else if (isExit(block) && isExit(nextBlock)) {
                  shouldConnect = exitLogic === "AND";
                  color = "#3B82F6";
                  markerId = "arrowhead-blue";
                }

                if (!shouldConnect) return null;

                const col = index % blocksPerRow;
                const row = Math.floor(index / blocksPerRow);
                const nextCol = (index + 1) % blocksPerRow;
                const nextRow = Math.floor((index + 1) / blocksPerRow);

                const startX = sidePadding + col * 185 + 120;
                const startY = 60 + row * 135 + 32;
                
                let endX, endY;
                const isNewRow = nextRow > row;

                if (isNewRow) {
                  endX = sidePadding + nextCol * 185 + 60;
                  endY = 60 + nextRow * 135;
                } else {
                  endX = sidePadding + nextCol * 185;
                  endY = 60 + nextRow * 135 + 32;
                }

                const dx = endX - startX;
                const dy = endY - startY;
                
                let pathD;
                if (isNewRow) {
                  const gutterY = startY + (endY - startY) / 2;
                  pathD = `M ${startX} ${startY} 
                           C ${startX + 30} ${startY}, ${startX + 30} ${gutterY}, ${startX} ${gutterY}
                           L ${endX + 30} ${gutterY}
                           C ${endX} ${gutterY}, ${endX} ${gutterY}, ${endX} ${endY}`;
                } else {
                  const offset = Math.min(Math.max(dx * 0.4, 20), 40);
                  const cp1x = startX + offset;
                  const cp1y = startY;
                  const cp2x = endX - offset;
                  const cp2y = endY;
                  pathD = `M ${startX} ${startY} C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${endX} ${endY}`;
                }

                return (
                  <g key={`flow-${block.id}-${nextBlock.id}`}>
                    <path d={pathD} stroke={color} strokeWidth="4" fill="none" className="opacity-10" filter="url(#glow)" />
                    <path d={pathD} stroke={color} strokeWidth="1.5" fill="none" className="opacity-40" />
                    <path d={pathD} stroke={color} strokeWidth="1.5" fill="none" strokeDasharray="4,12" className="opacity-60 animate-dash" />
                  </g>
                );
              })}
            </svg>
            {canvasBlocks.map((block, index) => {
              const colIdx = index % blocksPerRow;
              const rowIdx = Math.floor(index / blocksPerRow);
              const xOffset = sidePadding + colIdx * 185;
              const yOffset = 60 + rowIdx * 135;

              const typeStyles = 
                block.type === "entry" 
                  ? "border-red-500/30 bg-red-950/20 hover:bg-red-900/30 shadow-red-900/5" 
                  : block.type === "exit" 
                  ? "border-blue-500/30 bg-blue-950/20 hover:bg-blue-900/30 shadow-blue-900/5" 
                  : "border-[rgba(100,155,107,0.3)] bg-[rgba(100,155,107,0.1)] hover:bg-[rgba(100,155,107,0.2)] shadow-[rgba(100,155,107,0.05)]";

              const isSelected = selectedBlock?.id === block.id;

              return (
                <div
                  key={block.id}
                  onClick={() => {
                    setSelectedBlock(block);
                    setActiveParamTab('block');
                  }}
                  className={`absolute p-4 rounded-xl transition-all duration-300 border backdrop-blur-md group cursor-pointer ${typeStyles} ${
                    isSelected 
                      ? "ring-2 ring-blue-500/50 scale-105 z-10 shadow-2xl" 
                      : "hover:scale-105 z-1 shadow-lg"
                  }`}
                  style={{ left: `${xOffset}px`, top: `${yOffset}px`, width: "120px" }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${
                         block.type === "entry" ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]" : 
                         block.type === "exit" ? "bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]" : 
                         "bg-[rgb(100,155,107)] shadow-[0_0_8px_rgba(100,155,107,0.6)]"
                      }`} />
                      <span className={`text-[9px] font-bold px-1 rounded-sm ${
                        block.type === "entry" ? "bg-red-500/20 text-red-400" :
                        block.type === "exit" ? "bg-blue-500/20 text-blue-400" :
                        "bg-[rgba(100,155,107,0.2)] text-[rgb(100,155,107)]"
                      }`}>
                        {block.type === "entry" ? "매수" : block.type === "exit" ? "매도" : "필터"}
                      </span>
                    </div>
                  </div>
                  <div className="text-[12px] font-black text-white leading-tight tracking-tight">
                    {signalBlocks[block.blockId]?.name || block.blockId}
                  </div>
                  <button 
                    onClick={(e) => { 
                      e.stopPropagation(); 
                      setCanvasBlocks(canvasBlocks.filter(b => b.id !== block.id)); 
                      if (selectedBlock?.id === block.id) setSelectedBlock(null); 
                    }} 
                    className="absolute -top-2 -right-2 w-6 h-6 bg-[#1a1a1a] border border-gray-800 text-gray-500 rounded-lg opacity-0 group-hover:opacity-100 transition-all hover:text-white hover:bg-red-900/50 hover:border-red-500/50 flex items-center justify-center shadow-xl"
                  >
                    <XMarkIcon className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
        
        {/* Step Navigation Bar */}
        <div className="p-8 flex justify-end gap-3 mt-auto sticky bottom-0 bg-[#0f0f0f]/90 backdrop-blur-md z-20">
          <button onClick={onPrev} className="px-6 py-3 bg-[#1a1a1a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 transition-all flex items-center gap-2">
            <ArrowLeftIcon className="w-5 h-5" /> 이전 단계
          </button>
          <button onClick={onNext} className="px-8 py-3 bg-blue-600 text-white rounded-xl text-md font-black hover:bg-blue-500 transition-all flex items-center gap-3 shadow-xl shadow-blue-900/40">
            다음 단계 <ArrowRightIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Right Panel: Parameter Editor */}
      <div className="bg-[#0f0f0f] w-60 flex flex-col relative z-30">
        <div className="flex p-1 gap-1">
          <button
            onClick={() => setActiveParamTab('block')}
            className={`flex-1 py-2 text-sm font-black uppercase tracking-widest transition-all rounded-lg ${
              activeParamTab === 'block'
                ? "text-white bg-white/5"
                : "text-gray-600 hover:text-gray-400 hover:bg-gray-800/20"
            }`}
          >
            블록 설정
          </button>
          <button
            onClick={() => setActiveParamTab('global')}
            className={`flex-1 py-2 text-sm font-black uppercase tracking-widest transition-all rounded-lg ${
              activeParamTab === 'global'
                ? "text-white bg-white/5"
                : "text-gray-600 hover:text-gray-400 hover:bg-gray-800/20"
            }`}
          >
            전역 논리 설정
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-4 custom-scrollbar">
          {activeParamTab === 'block' ? (
            selectedBlock ? (
              <div className="space-y-4">
                <div className="p-3 bg-[#1a1a1a] rounded-lg border border-gray-800">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm text-white font-bold">{signalBlocks[selectedBlock.blockId]?.name || selectedBlock.blockId}</div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase tracking-tight ${selectedBlock.type === "entry" ? "bg-red-500/20 text-red-400" : selectedBlock.type === "exit" ? "bg-blue-500/20 text-blue-400" : "bg-purple-500/20 text-purple-400"}`}>
                      {selectedBlock.type === "entry" ? "매수" : selectedBlock.type === "exit" ? "매도" : "필터"}
                    </span>
                  </div>
                  <p className="text-[12px] text-gray-400 leading-relaxed tabular-nums">{signalBlocks[selectedBlock.blockId]?.description || "시그널을 발생시킵니다."}</p>
                </div>
                <div className="space-y-3">
                  {(() => {
                    const blockDef = signalBlocks[selectedBlock.blockId];
                    if (!blockDef || !blockDef.paramSchema) return <div className="text-xs text-gray-500">파라미터가 없습니다.</div>;

                    const getVal = (k: string) => selectedBlock.params[k] ?? blockDef.defaultParams[k];

                    if (selectedBlock.blockId === "investor_net_buy") {
                      const renderInput = (key: string) => {
                        const param = blockDef.paramSchema![key];
                        const val = getVal(key);
                        return (
                          <div key={key} className="space-y-1.5 flex-1">
                            <label className="text-xs text-gray-500 font-black uppercase tracking-tight">{param.label}</label>
                            <div className="flex items-center gap-2 bg-[#1a1a1a] border border-gray-800/50 rounded-lg px-3 py-2.5 hover:border-gray-700 focus-within:border-blue-500/40 transition-all">
                              <input 
                                type="text"
                                value={val === 0 ? "" : val}
                                placeholder="0"
                                onChange={(e) => {
                                  const raw = e.target.value;
                                  const v = raw === "" ? 0 : isNaN(parseFloat(raw)) ? 0 : parseFloat(raw);
                                  const newParams = { ...selectedBlock.params, [key]: v };
                                  setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams } : b));
                                  setSelectedBlock({ ...selectedBlock, params: newParams });
                                }}
                                className="bg-transparent text-xs font-black text-white w-full outline-none tabular-nums"
                              />
                              {param.suffix && <span className="text-[10px] font-black text-gray-600 uppercase">{param.suffix}</span>}
                            </div>
                          </div>
                        );
                      };

                      const renderSelect = (key: string) => {
                        const param = blockDef.paramSchema![key];
                        const val = getVal(key);
                        return (
                          <div key={key} className="space-y-1.5 flex-1">
                            <label className="text-xs text-gray-500 font-black uppercase tracking-tight">{param.label}</label>
                            <div className="relative group/select">
                              <select 
                                value={val} 
                                onChange={(e) => { 
                                  const rawVal = e.target.value;
                                  const v = isNaN(parseFloat(rawVal)) ? rawVal : parseFloat(rawVal);
                                  let newParams = { ...selectedBlock.params, [key]: v };
                                  let newType = selectedBlock.type;

                                  if (key === "investorType") {
                                    const newInvType = v as string;
                                    const memory = { ...(selectedBlock.params._investorMemory || {}) };
                                    if (memory[newInvType]) {
                                      newParams = { ...newParams, period: memory[newInvType].period, minAmount: memory[newInvType].minAmount, _investorMemory: memory };
                                    }
                                  }
                                  if (key === "signalType") newType = v === "buy" ? "entry" : "exit";

                                  setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams, type: newType } : b)); 
                                  setSelectedBlock({ ...selectedBlock, params: newParams, type: newType }); 
                                }} 
                                className="w-full appearance-none pl-3 pr-10 py-2.5 bg-[#1a1a1a] border border-gray-800/50 rounded-lg text-xs font-black text-white hover:bg-[#181818] hover:border-gray-700 transition-all cursor-pointer outline-none"
                              >
                                {param.options?.map((opt: any) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                              </select>
                              <ChevronDownIcon className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500 pointer-events-none" />
                            </div>
                          </div>
                        );
                      };

                      return (
                        <div className="space-y-4">
                          <div className="p-3 bg-[#1a1a1a]/50 border border-gray-800/50 rounded-xl space-y-4">
                            {renderSelect("investorType")}
                            <div className="flex gap-3">
                              {renderInput("period")}
                              {renderInput("minAmount")}
                            </div>
                            <button 
                              onClick={() => {
                                const invType = selectedBlock.params.investorType || "institutional";
                                const memory = { ...(selectedBlock.params._investorMemory || {}) };
                                memory[invType] = { period: getVal("period"), minAmount: getVal("minAmount") };
                                const newParams = { ...selectedBlock.params, _investorMemory: memory };
                                setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams } : b));
                                setSelectedBlock({ ...selectedBlock, params: newParams });
                              }}
                              className="w-full py-2.5 bg-blue-600/10 border border-blue-600/40 rounded-lg text-xs font-black text-blue-400 hover:bg-blue-600/20 hover:border-blue-600/60 transition-all flex items-center justify-center gap-1.5 group/savebtn shadow-lg shadow-blue-900/10"
                            >
                              설정 저장
                            </button>
                          </div>
                          <div>{renderSelect("signalType")}</div>
                        </div>
                      );
                    }

                    return Object.entries(blockDef.paramSchema).map(([key, param]) => {
                      const currentValue = selectedBlock.params[key] ?? blockDef.defaultParams[key];
                      return (
                        <div key={key}>
                          <div className="flex items-center gap-1.5 mb-1.5 relative group/tooltip-row">
                            <label className="text-xs text-gray-500 font-black uppercase tracking-tight">{param.label}</label>
                            {param.tooltip && (
                              <div 
                                className="p-1 -m-1"
                                onMouseEnter={(e) => setHoveredParam({ label: param.label, tooltip: param.tooltip!, rect: e.currentTarget.getBoundingClientRect() })}
                                onMouseLeave={() => setHoveredParam(null)}
                              >
                                <InformationCircleIcon className="w-3.5 h-3.5 text-gray-700 hover:text-blue-500 transition-colors cursor-help" />
                              </div>
                            )}
                          </div>
                          {param.type === "select" && param.options ? (
                            <div className="relative group/select">
                              <select 
                                value={currentValue} 
                                onChange={(e) => { 
                                  const rawVal = e.target.value;
                                  const val = isNaN(parseFloat(rawVal)) ? rawVal : parseFloat(rawVal);
                                  let newParams = { ...selectedBlock.params, [key]: val };
                                  let newType = selectedBlock.type;
                                  if (key === "signalType") {
                                    if (val === "buy") newType = "entry";
                                    else if (val === "sell") newType = "exit";
                                  }
                                  setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams, type: newType } : b)); 
                                  setSelectedBlock({ ...selectedBlock, params: newParams, type: newType }); 
                                }} 
                                className={`w-full appearance-none pl-3 ${param.suffix ? "pr-16" : "pr-10"} py-2.5 bg-[#1a1a1a] border border-gray-800/50 rounded-lg text-xs font-black text-white hover:bg-[#151515] hover:border-gray-700 transition-all cursor-pointer outline-none`}
                              >
                                {param.options.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                              </select>
                              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5 pointer-events-none">
                                {param.suffix && <span className="text-xs font-black text-gray-600 uppercase pr-1 border-r border-gray-800/50 mr-1">{param.suffix}</span>}
                                <ChevronDownIcon className="w-3.5 h-3.5 text-gray-500" />
                              </div>
                            </div>
                          ) : param.type === "boolean" ? (
                            <button 
                              onClick={() => {
                                const newVal = !currentValue;
                                const newParams = { ...selectedBlock.params, [key]: newVal };
                                setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams } : b)); 
                                setSelectedBlock({ ...selectedBlock, params: newParams }); 
                              }}
                              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg border transition-all ${currentValue ? "bg-blue-600/10 border-blue-600/50 text-blue-400" : "bg-[#1a1a1a] border-gray-800/50 text-gray-500 hover:border-gray-700"}`}
                            >
                              <span className="text-xs font-black">{param.label}</span>
                              <div className={`w-8 h-4 rounded-full relative transition-colors ${currentValue ? "bg-blue-600" : "bg-gray-800"}`}>
                                <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${currentValue ? "right-0.5" : "left-0.5"}`} />
                              </div>
                            </button>
                          ) : (
                             <div className="bg-[#1a1a1a] border border-gray-800/50 rounded-lg p-3 group/input hover:border-gray-700 transition-all">
                              <div className="flex justify-between items-center mb-3 px-1">
                                <span className="text-xs font-black text-white tabular-nums">{currentValue}</span>
                                {param.suffix && <span className="text-xs font-black text-gray-500 uppercase">{param.suffix}</span>}
                              </div>
                              <div className="px-1 space-y-1.5">
                                <input 
                                  type="range"
                                  min={param.min ?? 0}
                                  max={param.max ?? 100}
                                  step={param.step ?? 1}
                                  value={currentValue !== "" ? currentValue : 0}
                                  onChange={(e) => {
                                    const val = parseFloat(e.target.value);
                                    const newParams = { ...selectedBlock.params, [key]: val }; 
                                    setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams } : b)); 
                                    setSelectedBlock({ ...selectedBlock, params: newParams }); 
                                  }}
                                  className="w-full h-1.5 bg-gray-800/50 rounded-lg appearance-none cursor-pointer accent-blue-500 hover:accent-blue-400 transition-all opacity-70 hover:opacity-100"
                                />
                                <div className="flex justify-between items-center opacity-40 group-hover/input:opacity-60 transition-opacity">
                                  <span className="text-[9px] font-black text-gray-500 tabular-nums">{param.min ?? 0}</span>
                                  <span className="text-[9px] font-black text-gray-500 tabular-nums">{param.max ?? 100}</span>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    });
                  })()}
                  <div className="pt-2 border-t border-gray-800/30">
                    <button 
                      onClick={() => {
                        if (!selectedBlock) return;
                        const blockDef = signalBlocks[selectedBlock.blockId];
                        if (blockDef) {
                          const newParams = { ...blockDef.defaultParams };
                          let newType = selectedBlock.type;
                          if (newParams.signalType) {
                            newType = newParams.signalType === "buy" ? "entry" : newParams.signalType === "sell" ? "exit" : "filter";
                          }
                          const updatedBlocks = canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams, type: newType } : b);
                          setCanvasBlocks(updatedBlocks); 
                        }
                      }}
                      className="w-full py-2 bg-[#1a1a1a] border border-gray-800 rounded-lg text-xs font-bold text-gray-400 hover:text-white hover:bg-gray-800 hover:border-gray-700 transition-all flex items-center justify-center gap-1.5"
                    >
                      <ArrowPathIcon className="w-3 h-3" />
                      기본값 복원
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center pt-24 text-center p-6 space-y-5 opacity-30">
                <div className="w-20 h-20 rounded-full bg-gray-800/20 border border-gray-700/30 flex items-center justify-center">
                  <CursorArrowRaysIcon className="w-10 h-10 text-gray-600" />
                </div>
                <div className="space-y-2">
                  <h4 className="text-sm font-black text-gray-400">블록 선택 안 됨</h4>
                  <p className="text-xs text-gray-600 font-bold leading-relaxed">수정할 블록을 캔버스에서 <br /> 선택해 주세요.</p>
                </div>
              </div>
            )
          ) : (
            <div className="space-y-6">
              <div className="bg-[#1a1a1a]/50 rounded-xl p-5 border border-gray-800">
                <label className="flex items-center gap-2 text-sm font-bold text-red-400 mb-3 uppercase tracking-wider">매수 결합</label>
                <div className="flex bg-[#151515] rounded-lg p-1 mb-3">
                  <button onClick={() => setEntryLogic("AND")} className={`flex-1 py-1.5 text-xs font-bold rounded ${entryLogic === "AND" ? "bg-red-600 text-white" : "text-gray-500"}`}>AND</button>
                  <button onClick={() => setEntryLogic("OR")} className={`flex-1 py-1.5 text-xs font-bold rounded ${entryLogic === "OR" ? "bg-red-600 text-white" : "text-gray-500"}`}>OR</button>
                </div>
                <p className="text-[11px] text-gray-400 font-medium">{entryLogic === "AND" ? "모든 조건 충족 시 신호 발생" : "하나라도 충족 시 신호 발생"}</p>
              </div>
              <div className="bg-[#1a1a1a]/50 rounded-xl p-5 border border-gray-800">
                <label className="flex items-center gap-2 text-sm font-bold text-blue-400 mb-3 uppercase tracking-wider">매도 결합</label>
                <div className="flex bg-[#151515] rounded-lg p-1 mb-3">
                  <button onClick={() => setExitLogic("AND")} className={`flex-1 py-1.5 text-xs font-bold rounded ${exitLogic === "AND" ? "bg-blue-600 text-white" : "text-gray-500"}`}>AND</button>
                  <button onClick={() => setExitLogic("OR")} className={`flex-1 py-1.5 text-xs font-bold rounded ${exitLogic === "OR" ? "bg-blue-600 text-white" : "text-gray-500"}`}>OR</button>
                </div>
                <p className="text-[11px] text-gray-400 font-medium">{exitLogic === "AND" ? "모든 조건 충족 시 신호 발생" : "하나라도 충족 시 신호 발생"}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Tooltip Overlays */}
      {hoveredEditIcon && (
        <div className="fixed z-[9999] pointer-events-none" style={{ left: hoveredEditIcon.rect.left + (hoveredEditIcon.rect.width / 2), top: hoveredEditIcon.rect.bottom + 8, transform: 'translateX(-50%)' }}>
          <div className="px-3 py-1.5 bg-[#0a0a0a] border border-gray-800 rounded-lg shadow-xl animate-in fade-in zoom-in-95 slide-in-from-top-2 duration-200">
            <p className="text-[11px] text-gray-300 font-bold whitespace-nowrap">{hoveredEditIcon.label}</p>
          </div>
        </div>
      )}

      {hoveredInfo && (
        <div className="fixed z-[9999] pointer-events-none" style={{ left: hoveredInfo.rect.right + 12, top: hoveredInfo.rect.top + (hoveredInfo.rect.height / 2), transform: 'translateY(-50%)' }}>
          <div className="w-80 p-5 bg-[#161616] border border-gray-800 rounded-3xl shadow-2xl animate-in fade-in zoom-in-95 slide-in-from-left-2 duration-200">
            <p className="text-[13px] text-gray-300 font-bold leading-[1.7]">{signalBlocks[hoveredInfo.id]?.description || "설명 없음"}</p>
            <div className="absolute top-1/2 -left-1.5 -translate-y-1/2 w-3 h-3 bg-[#161616] border-l border-b border-gray-800 rotate-45" />
          </div>
        </div>
      )}

      {hoveredParam && (
        <div className="fixed z-[9999] pointer-events-none" style={{ left: hoveredParam.rect.left - 270, top: hoveredParam.rect.top + (hoveredParam.rect.height / 2), transform: 'translateY(-50%)' }}>
          <div className="w-64 p-4 bg-[#161616] border border-gray-800 rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 slide-in-from-right-2 duration-200">
            <div className="text-[10px] text-blue-500 font-black uppercase tracking-widest mb-2 opacity-50">{hoveredParam.label}</div>
            <p className="text-[12px] text-gray-300 font-bold leading-[1.7]">{hoveredParam.tooltip}</p>
            <div className="absolute top-1/2 -translate-y-1/2 -right-1 w-2.5 h-2.5 bg-[#161616] border-t border-r border-gray-800 rotate-45" />
          </div>
        </div>
      )}

      {/* Modals */}
      {isLibraryManagementOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setIsLibraryManagementOpen(false)}>
          <div className="w-full max-w-4xl h-[750px] bg-[#161616] border border-gray-800 rounded-2xl shadow-2xl flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="p-5 border-b border-gray-800 flex items-center justify-between bg-[#1a1a1a] rounded-t-2xl">
              <h3 className="text-xl font-black text-white uppercase">보관함 관리</h3>
              <button onClick={() => setIsLibraryManagementOpen(false)}><XMarkIcon className="w-6 h-6 text-gray-500" /></button>
            </div>
            <div className="flex-1 flex overflow-hidden">
              <div className="w-64 border-r border-gray-800 bg-[#1a1a1a]/30 flex flex-col p-3 space-y-1">
                {customCategoryOrder.map((key) => {
                  const group = (groupedSignalLibrary as any)[key];
                  if (!group) return null;
                  return (
                    <div 
                      key={key} 
                      className={`flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer ${activeMgmtCategory === key ? "bg-blue-600/10 border border-blue-500/30" : "hover:bg-white/5"}`}
                      onClick={() => setActiveMgmtCategory(key)}
                    >
                      <group.icon className={`w-4 h-4 ${activeMgmtCategory === key ? "text-blue-400" : "text-gray-600"}`} />
                      <span className={`text-sm font-black uppercase truncate ${activeMgmtCategory === key ? "text-blue-400" : "text-gray-500"}`}>{group.label}</span>
                    </div>
                  );
                })}
              </div>
              <div className="flex-1 p-6 overflow-y-auto custom-scrollbar">
                {activeMgmtCategory && (
                  <div className="grid grid-cols-1 gap-2.5">
                    {(groupedSignalLibrary as any)[activeMgmtCategory].blocks.map((block: any) => (
                      <div key={block.id} className="flex items-center justify-between p-4 bg-[#1a1a1a] border border-gray-800 rounded-xl hover:border-blue-500/20">
                        <span className="text-gray-200 font-bold">{block.name}</span>
                        <button onClick={(e) => handleRemoveBlockFromBin(block.id, e)} className="text-gray-600 hover:text-red-400 transition-colors"><XMarkIcon className="w-5 h-5" /></button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {isSearchMenuOpen && (
        <StrategyBlockSearchMenu
          manuallyHiddenBlockIds={manuallyHiddenBlockIds}
          onSelect={(blockIds) => {
            const newAdditions = blockIds.filter(id => !unlockedBlockIds.includes(id) && !manuallyHiddenBlockIds.includes(id));
            const restored = blockIds.filter(id => manuallyHiddenBlockIds.includes(id));
            if (restored.length > 0) setManuallyHiddenBlockIds(prev => prev.filter(id => !restored.includes(id)));
            if (newAdditions.length > 0) setUnlockedBlockIds(prev => [...prev, ...newAdditions]);
            setIsSearchMenuOpen(false);
          }}
          onClose={() => setIsSearchMenuOpen(false)}
        />
      )}
    </>
  );
}
