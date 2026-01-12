"use client";

import { Fragment, useMemo, useEffect, useRef } from "react";
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
  Squares2X2Icon,
  Bars3Icon,
  ChevronUpDownIcon,
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
  reorderDragItem: { type: 'category' | 'block', id: string, index: number, categoryId?: string } | null;
  setReorderDragItem: React.Dispatch<React.SetStateAction<{ type: 'category' | 'block', id: string, index: number, categoryId?: string } | null>>;
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
  reorderDragItem,
  setReorderDragItem,
  canvasRef,
  canvasWidth,
  onNext,
  onPrev,
  handleAddBlock,
  handleRemoveBlockFromBin,
}: Step2ConditionsProps) {
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setOpenSignalGroups([]);
      }
    };

    if (openSignalGroups.length > 0) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [openSignalGroups, setOpenSignalGroups]);

  const blocksPerRow = canvasWidth > 900 ? 6 : canvasWidth > 600 ? 4 : Math.max(1, Math.floor((canvasWidth - 30) / 150));
  const totalGridWidth = blocksPerRow * 150 - 30;
  const sidePadding = Math.max(15, (canvasWidth - totalGridWidth) / 2);

  const groupedSignalLibrary = useMemo(() => {
    return {
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
  }, [unlockedBlockIds, manuallyHiddenBlockIds, customBlockOrder]);

  const handleReorderDragStart = (e: React.DragEvent, item: { type: 'category' | 'block', id: string, index: number, categoryId?: string }) => {
    e.stopPropagation();
    setReorderDragItem(item);
    e.dataTransfer.effectAllowed = "move";

    const target = e.currentTarget as HTMLElement;
    let rowElement: HTMLElement | null = null;

    if (item.type === 'category') {
      rowElement = target.parentElement;
    } else {
      const innerRow = target.parentElement?.parentElement;
      rowElement = innerRow || null;
    }
    
    if (rowElement) {
      const rect = rowElement.getBoundingClientRect();
      const offsetX = e.clientX - rect.left;
      const offsetY = e.clientY - rect.top;
      e.dataTransfer.setDragImage(rowElement, offsetX, offsetY);
    }
  };

  const handleReorderDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleReorderDrop = (e: React.DragEvent, targetItem: { type: 'category' | 'block', id: string, index: number, categoryId?: string }) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!reorderDragItem) return;
    if (reorderDragItem.type !== targetItem.type) return;
    if (reorderDragItem.type === 'block' && reorderDragItem.categoryId !== targetItem.categoryId) return;

    if (reorderDragItem.type === 'category') {
      const newOrder = [...customCategoryOrder];
      const oldIndex = newOrder.indexOf(reorderDragItem.id);
      const newIndex = newOrder.indexOf(targetItem.id);
      if (oldIndex === -1 || newIndex === -1) return;
      newOrder.splice(oldIndex, 1);
      newOrder.splice(newIndex, 0, reorderDragItem.id);
      setCustomCategoryOrder(newOrder);
    } else if (reorderDragItem.type === 'block' && reorderDragItem.categoryId) {
       const categoryId = reorderDragItem.categoryId;
       const currentOrder = groupedSignalLibrary[categoryId as keyof typeof groupedSignalLibrary].blocks.map((b: any) => b.id);
       const newOrder = [...currentOrder];
       const oldIndex = newOrder.indexOf(reorderDragItem.id);
       const newIndex = newOrder.indexOf(targetItem.id);
       if (oldIndex !== -1 && newIndex !== -1) {
         newOrder.splice(oldIndex, 1);
         newOrder.splice(newIndex, 0, reorderDragItem.id);
         setCustomBlockOrder(prev => ({ ...prev, [categoryId]: newOrder }));
       }
    }
    setReorderDragItem(null);
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-[#0f0f0f]">
      <div className="flex-1 flex min-h-0 overflow-hidden bg-[#0f0f0f] max-h-[640px]">
        {/* Left Sidebar */}
        <div className="w-52 bg-[#0c0c0c] backdrop-blur-2xl flex flex-col shrink-0 relative z-20 rounded-[32px] ml-4 h-full overflow-hidden">
          <div className="flex-1 px-4 py-6 space-y-4">
            <div className="flex items-center justify-between mb-2 px-1">
              <div className="flex items-center gap-2">
                <Squares2X2Icon className="w-4 h-4 text-[rgb(59, 134, 247)]" />
                <h3 className="text-xs font-black text-white/60 uppercase tracking-widest">지표 라이브러리</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsLibraryManagementOpen(true)}
                className="p-1.5 bg-white/5 rounded-lg text-gray-500 hover:text-white hover:bg-white/10 transition-all group/mgmt"
              >
                <EllipsisHorizontalIcon className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              {customCategoryOrder.map((key) => {
                const group = (groupedSignalLibrary as any)[key];
                if (!group) return null;
                const filteredBlocks = group.blocks;
                const isOpen = openSignalGroups.includes(group.key);
                
                return (
                  <div key={group.key} className="relative">
                    <button
                      type="button"
                      onClick={() => setOpenSignalGroups((prev) => 
                        prev.includes(group.key) ? [] : [group.key]
                      )}
                      className={`w-full flex items-center justify-between px-4 py-4 text-sm font-black transition-all group/header rounded-xl ${
                        isOpen ? "text-white bg-white/5" : "text-white/40 hover:text-white/60 hover:bg-white/5"
                      }`}
                    >
                      <span className="tracking-tight">{group.label}</span>
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${isOpen ? "bg-white/10 text-white" : "text-white/20 group-hover:text-white/40"}`}>
                        <ChevronUpDownIcon className="w-4 h-4" />
                      </div>
                    </button>

                    {isOpen && (
                      <div 
                        ref={popoverRef}
                        className="absolute inset-x-0 top-0 bg-[#161616] backdrop-blur-3xl rounded-[24px] border border-white/10 shadow-[0_25px_60px_rgba(0,0,0,0.8)] z-[100] p-3 animate-in fade-in zoom-in-95 duration-200"
                      >
                        <div className="space-y-1.5 max-h-[420px] overflow-y-auto custom-scrollbar pr-1">
                          {filteredBlocks.length === 0 && <div className="text-xs text-gray-700 px-3 py-4 italic text-center">Empty Category</div>}
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
                                className="group p-3.5 bg-white/5 rounded-2xl text-xs font-black text-white/40 hover:text-white hover:bg-[rgb(59, 134, 247)] cursor-move transition-all flex items-center justify-between shadow-sm border border-transparent hover:border-white/10"
                              >
                                <span className="truncate pr-2 tracking-tight">{block.name}</span>
                                <InformationCircleIcon 
                                  className="w-3.5 h-3.5 text-white/10 group-hover:text-white/40 cursor-help"
                                  onMouseEnter={(e) => setHoveredInfo({ id: block.id, rect: e.currentTarget.getBoundingClientRect() })}
                                  onMouseLeave={() => setHoveredInfo(null)}
                                />
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="py-4">
              <button
                type="button"
                onClick={() => setIsSearchMenuOpen(!isSearchMenuOpen)}
                className={`w-full flex items-center justify-center gap-3 py-4 rounded-[20px] transition-all ${
                  isSearchMenuOpen
                    ? "bg-white text-black shadow-[0_0_25px_rgba(255,255,255,0.2)]"
                    : "bg-white/5 text-white/40 hover:text-white hover:bg-white/10"
                }`}
              >
                <MagnifyingGlassIcon className="w-5 h-5" />
                <span className="text-xs font-black uppercase tracking-widest">블록 검색</span>
              </button>
            </div>
          </div>
          <div className="bg-[#0c0c0c] px-4 pt-4 pb-8 flex items-center justify-center">
            <p className="text-xs text-white/20 text-center leading-relaxed font-black uppercase tracking-tight">
              찾고 계신 지표가 없나요? <br />
              <span className="text-[rgb(59, 134, 247)] hover:text-[#0A84FF] cursor-pointer underline decoration-dotted underline-offset-4 transition-colors">지표 기능 제안하기</span>
            </p>
          </div>
        </div>

        {/* Center Canvas Area */}
        <div className="flex-1 bg-transparent relative overflow-hidden flex flex-col h-full">
          <div 
            ref={canvasRef}
            className="flex-1 relative border border-white/10 rounded-[32px] overflow-hidden mx-4 h-full bg-black/20 backdrop-blur-2xl shadow-2xl"
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
            <div className="absolute inset-0 pointer-events-none" 
                 style={{ 
                   backgroundImage: `radial-gradient(circle at 1px 1px, rgba(255,255,255,0.05) 1px, transparent 0)`,
                   backgroundSize: "24px 24px" 
                 }} />
            
            {canvasBlocks.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center p-12 text-center pointer-events-none z-10">
                <div className="max-w-md space-y-6 animate-in fade-in zoom-in slide-in-from-bottom-8 duration-1000">
                  <div className="w-24 h-24 bg-white/5 rounded-[32px] flex items-center justify-center mx-auto border border-white/10 mb-6 backdrop-blur-xl">
                    <PlusIcon className="w-10 h-10 text-white/20" />
                  </div>
                  <h4 className="text-xl font-black text-white/40 tracking-tight uppercase">조건 설계 캔버스</h4>
                  <p className="text-sm text-white/20 font-black uppercase tracking-tight leading-relaxed max-w-[240px] mx-auto">
                    왼쪽 라이브러리에서 블록을 드래그하여 <br /> 매수/매도 로직을 완성하세요.
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
                  const startX = sidePadding + col * 150 + 120;
                  const startY = 60 + row * 135 + 32;
                  let endX, endY;
                  const isNewRow = nextRow > row;
                  if (isNewRow) {
                    endX = sidePadding + nextCol * 150 + 60;
                    endY = 60 + nextRow * 135;
                  } else {
                    endX = sidePadding + nextCol * 150;
                    endY = 60 + nextRow * 135 + 32;
                  }
                  const dx = endX - startX;
                  let pathD;
                  if (isNewRow) {
                    const gutterY = startY + (endY - startY) / 2;
                    pathD = `M ${startX} ${startY} C ${startX + 30} ${startY}, ${startX + 30} ${gutterY}, ${startX} ${gutterY} L ${endX + 30} ${gutterY} C ${endX} ${gutterY}, ${endX} ${gutterY}, ${endX} ${endY}`;
                  } else {
                    const offset = Math.min(Math.max(dx * 0.4, 20), 40);
                    pathD = `M ${startX} ${startY} C ${startX + offset} ${startY} ${endX - offset} ${endY} ${endX} ${endY}`;
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
                const xOffset = sidePadding + colIdx * 150;
                const yOffset = 60 + rowIdx * 135;
                const typeStyles = block.type === "entry" ? "border-red-500/30 bg-red-950/20 hover:bg-red-900/30 shadow-red-900/5" : block.type === "exit" ? "border-blue-500/30 bg-blue-950/20 hover:bg-blue-900/30 shadow-blue-900/5" : "border-[rgba(100,155,107,0.3)] bg-[rgba(100,155,107,0.1)] hover:bg-[rgba(100,155,107,0.2)] shadow-[rgba(100,155,107,0.05)]";
                const isSelected = selectedBlock?.id === block.id;

                return (
                  <div
                    key={block.id}
                    onClick={() => {
                      setSelectedBlock(block);
                      setActiveParamTab('block');
                    }}
                    className={`absolute p-4 rounded-xl transition-all duration-300 border backdrop-blur-md group cursor-pointer ${typeStyles} ${isSelected ? "ring-2 ring-blue-500/50 scale-105 z-10 shadow-2xl" : "hover:scale-105 z-1 shadow-lg"}`}
                    style={{ left: `${xOffset}px`, top: `${yOffset}px`, width: "120px" }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${block.type === "entry" ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]" : block.type === "exit" ? "bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)]" : "bg-[#649b6b] shadow-[0_0_8px_rgba(100,155,107,0.5)]"}`} />
                        <span className={`text-[10px] font-bold uppercase tracking-tight ${block.type === "entry" ? "text-red-400" : block.type === "exit" ? "text-blue-400" : "text-[#649b6b]"}`}>
                          {block.type === "entry" ? "매수" : block.type === "exit" ? "매도" : "필터"}
                        </span>
                      </div>
                    </div>
                    <div className={`text-xs font-bold tracking-tight ${isSelected ? "text-white" : "text-white/75 group-hover:text-white"}`}>
                      {signalBlocks[block.blockId]?.name || block.blockId}
                    </div>
                    <button 
                      onClick={(e) => { 
                        e.stopPropagation(); 
                        setCanvasBlocks(canvasBlocks.filter(b => b.id !== block.id)); 
                        if (selectedBlock?.id === block.id) setSelectedBlock(null); 
                      }} 
                      className="absolute -top-2 -right-2 w-7 h-7 bg-black border border-white/10 text-[#a0a0a0] rounded-full opacity-0 group-hover:opacity-100 transition-all hover:text-white hover:bg-[#FF3B30] hover:border-[#FF3B30] flex items-center justify-center shadow-xl"
                    >
                      <XMarkIcon className="w-4 h-4" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Panel: Single Box Tabbed Layout */}
        <div className="w-64 bg-black/20 backdrop-blur-2xl rounded-[40px] flex flex-col relative z-20 mr-4 h-full overflow-hidden">
          {/* Tab Headers */}
          <div className="px-2 py-2 bg-[#0c0c0c] flex gap-1">
            <button
              onClick={(e) => { e.stopPropagation(); setActiveParamTab('block'); }}
              className={`flex-1 py-3 text-xs font-black uppercase tracking-widest transition-all rounded-full ${
                activeParamTab === 'block'
                  ? "text-white bg-white/5 shadow-inner"
                  : "text-[#a0a0a0] hover:text-white/40"
              }`}
            >
              블록 설정
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setActiveParamTab('global'); }}
              className={`flex-1 py-3 text-xs font-black uppercase tracking-widest transition-all rounded-full ${
                activeParamTab === 'global'
                  ? "text-white bg-white/5 shadow-inner"
                  : "text-[#a0a0a0] hover:text-white/40"
              }`}
            >
              매매 로직
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 custom-scrollbar">
            {activeParamTab === 'block' ? (
              selectedBlock ? (
                <div className="space-y-6 px-2">
                  <div className="p-2.5 bg-white/5 rounded-lg mb-1">
                    <div className="text-[10px] font-bold text-[rgb(59, 134, 247)] uppercase tracking-widest mb-0.5">Block Info</div>
                    <div className="text-sm text-[#dfdfdf] font-bold tracking-tight">{signalBlocks[selectedBlock.blockId]?.name || selectedBlock.blockId}</div>
                    <p className="text-[11px] text-[#a0a0a0] mt-0.5 font-medium leading-tight">{signalBlocks[selectedBlock.blockId]?.description || "시그널을 발생시킵니다."}</p>
                  </div>
                  {(() => {
                    const block = selectedBlock!; 
                    const blockDef = signalBlocks[block.blockId];
                    if (!blockDef || !blockDef.paramSchema) return <div className="text-xs text-white/20 p-4">파라미터가 없습니다.</div>;
                    const getVal = (k: string) => block.params[k] ?? blockDef.defaultParams[k];

                    if (block.blockId === "investor_net_buy") {
                      const renderInput = (key: string) => {
                        const param = blockDef.paramSchema![key];
                        const val = getVal(key);
                        return (
                          <div key={key} className="space-y-1 flex-1">
                            <label className="text-[10px] text-white/40 font-bold uppercase tracking-widest ml-1">{param.label}</label>
                            <div className="flex items-center gap-2 bg-white/5 rounded-lg px-3 py-1.5 focus-within:ring-1 focus-within:ring-[rgb(59, 134, 247)]/50 transition-all group/input">
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
                                className="bg-transparent text-xs font-bold text-white w-full outline-none tabular-nums placeholder-white/10"
                              />
                              {param.suffix && <span className="text-sm font-bold text-white/20 uppercase tracking-tight">{param.suffix}</span>}
                            </div>
                          </div>
                        );
                      };

                      const renderSelect = (key: string) => {
                        const param = blockDef.paramSchema![key];
                        const val = getVal(key);
                        return (
                          <div key={key} className="space-y-1 flex-1">
                            <label className="text-[10px] text-white/40 font-bold uppercase tracking-widest ml-1">{param.label}</label>
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
                                className="w-full appearance-none pl-3 pr-8 py-1.5 bg-white/5 rounded-lg text-xs font-bold text-white hover:bg-white/10 transition-all cursor-pointer outline-none"
                              >
                                {param.options?.map((opt: any) => <option key={opt.value} value={opt.value} className="bg-[#1a1a1a]">{opt.label}</option>)}
                              </select>
                              <ChevronDownIcon className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/20 pointer-events-none group-hover/select:text-white/40 transition-colors" />
                            </div>
                          </div>
                        );
                      };

                      return (
                        <div className="space-y-4">
                          <div className="p-4 bg-white/5 rounded-3xl space-y-5">
                            {renderSelect("investorType")}
                            <div className="flex gap-4">
                              {renderInput("period")}
                              {renderInput("minAmount")}
                            </div>
                            <button 
                              onClick={() => {
                                const invType = block.params.investorType || "institutional";
                                const memory = { ...(block.params._investorMemory || {}) };
                                memory[invType] = { period: getVal("period"), minAmount: getVal("minAmount") };
                                const newParams = { ...block.params, _investorMemory: memory };
                                setCanvasBlocks(canvasBlocks.map(b => b.id === block.id ? { ...b, params: newParams } : b));
                                setSelectedBlock({ ...block, params: newParams });
                              }}
                              className="w-full py-1.5 bg-white text-black rounded-lg text-[10px] font-black hover:bg-white/90 transition-all flex items-center justify-center gap-1.5 shadow-sm active:scale-95"
                            >
                              설정값 기억하기
                            </button>
                          </div>
                          <div className="px-1">{renderSelect("signalType")}</div>
                        </div>
                      );
                    }

                    return Object.entries(blockDef.paramSchema).map(([key, param]) => {
                      const currentValue = block.params[key] ?? blockDef.defaultParams[key];
                      return (
                        <div key={key} className="space-y-1">
                          <div className="flex items-center gap-1.5 mb-px relative group/tooltip-row">
                            <label className="text-[10px] text-white/40 font-bold uppercase tracking-widest ml-1">{param.label}</label>
                            {param.tooltip && (
                              <div 
                                className="p-1 -m-1"
                                onMouseEnter={(e) => setHoveredParam({ label: param.label, tooltip: param.tooltip!, rect: e.currentTarget.getBoundingClientRect() })}
                                onMouseLeave={() => setHoveredParam(null)}
                              >
                                <InformationCircleIcon className="w-3.5 h-3.5 text-white/10 hover:text-white transition-colors cursor-help" />
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
                                  let newParams = { ...block.params, [key]: val };
                                  let newType = block.type;
                                  if (key === "signalType") {
                                    if (val === "buy") newType = "entry";
                                    else if (val === "sell") newType = "exit";
                                  }
                                  setCanvasBlocks(canvasBlocks.map(b => b.id === block.id ? { ...b, params: newParams, type: newType } : b)); 
                                  setSelectedBlock({ ...block, params: newParams, type: newType }); 
                                }} 
                                className={`w-full appearance-none pl-3 ${param.suffix ? "pr-16" : "pr-8"} py-1.5 bg-white/5 rounded-lg text-xs font-bold text-white hover:bg-white/10 transition-all cursor-pointer outline-none`}
                              >
                                {param.options.map(opt => <option key={opt.value} value={opt.value} className="bg-[#1a1a1a]">{opt.label}</option>)}
                              </select>
                              <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2 pointer-events-none">
                                {param.suffix && <span className="text-sm font-bold text-white/20 uppercase pr-2 mr-1">{param.suffix}</span>}
                                <ChevronDownIcon className="w-4 h-4 text-white/20" />
                              </div>
                            </div>
                          ) : param.type === "boolean" ? (
                            <button 
                              onClick={() => {
                                const newVal = !currentValue;
                                const newParams = { ...block.params, [key]: newVal };
                                setCanvasBlocks(canvasBlocks.map(b => b.id === block.id ? { ...b, params: newParams } : b)); 
                                setSelectedBlock({ ...block, params: newParams }); 
                              }}
                              className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg transition-all ${currentValue ? "bg-[rgb(59, 134, 247)]/10 text-[rgb(59, 134, 247)]" : "bg-white/5 text-white/40"}`}
                            >
                              <span className="text-[10px] font-black uppercase tracking-tight">{param.label}</span>
                              <div className={`w-8 h-4 rounded-full relative transition-all duration-300 ${currentValue ? "bg-[rgb(59, 134, 247)]" : "bg-white/10"}`}>
                                <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow-lg transition-transform duration-300`} style={{ transform: currentValue ? 'translateX(18px)' : 'translateX(2px)' }} />
                              </div>
                            </button>
                          ) : (
                            <div className="bg-white/5 rounded-[24px] p-4 group/input transition-all">
                              <div className="flex justify-between items-center mb-3 px-1">
                                <span className="text-lg font-bold text-white tabular-nums tracking-tight">{currentValue}</span>
                                {param.suffix && <span className="text-sm font-bold text-white/20 uppercase tracking-widest">{param.suffix}</span>}
                              </div>
                              <div className="px-1 space-y-2">
                                <input 
                                  type="range"
                                  min={param.min ?? 0}
                                  max={param.max ?? 100}
                                  step={param.step ?? 1}
                                  value={currentValue !== "" ? currentValue : 0}
                                  onChange={(e) => {
                                    const val = parseFloat(e.target.value);
                                    const newParams = { ...block.params, [key]: val }; 
                                    setCanvasBlocks(canvasBlocks.map(b => b.id === block.id ? { ...b, params: newParams } : b)); 
                                    setSelectedBlock({ ...block, params: newParams }); 
                                  }}
                                  className="w-full h-1 bg-white/10 rounded-full appearance-none cursor-pointer accent-[rgb(59, 134, 247)] hover:accent-[#0A84FF] transition-all"
                                />
                                <div className="flex justify-between items-center opacity-20 group-hover/input:opacity-40 transition-opacity">
                                  <span className="text-xs font-bold text-white tabular-nums">{param.min ?? 0}</span>
                                  <span className="text-xs font-bold text-white tabular-nums">{param.max ?? 100}</span>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    });
                  })()}
                  <div className="pt-4 mt-2">
                    <button 
                      onClick={() => {
                        const block = selectedBlock!;
                        const blockDef = signalBlocks[block.blockId];
                        if (blockDef) {
                          const newParams = { ...blockDef.defaultParams };
                          let newType = block.type;
                          if (newParams.signalType) {
                            newType = newParams.signalType === "buy" ? "entry" : newParams.signalType === "sell" ? "exit" : "filter";
                          }
                          const updatedBlocks = canvasBlocks.map(b => b.id === block.id ? { ...b, params: newParams, type: newType } : b);
                          setCanvasBlocks(updatedBlocks); 
                          setSelectedBlock({ ...block, params: newParams, type: newType });
                        }
                      }}
                      className="w-full py-3.5 bg-white/5 rounded-2xl text-sm font-bold text-white/40 hover:text-white hover:bg-white/10 transition-all flex items-center justify-center gap-2 uppercase tracking-widest active:scale-95"
                    >
                      <ArrowPathIcon className="w-3.5 h-3.5" />
                      초기값으로 복원
                    </button>
                  </div>
                </div>
              ) : (
                <div className="h-full flex flex-col items-center pt-24 text-center p-6 space-y-6">
                  <div className="w-20 h-20 rounded-[28px] bg-white/5 flex items-center justify-center backdrop-blur-xl border border-white/5">
                    <CursorArrowRaysIcon className="w-8 h-8 text-white/10" />
                  </div>
                  <div className="space-y-2">
                    <h4 className="text-sm font-bold text-[#dfdfdf] uppercase tracking-tight">블록 미선택</h4>
                    <p className="text-[11px] text-[#a0a0a0] font-bold uppercase tracking-tight leading-relaxed">캔버스에서 설정할 블록을 <br /> 선택해주세요.</p>
                  </div>
                </div>
              )
            ) : (
              <div className="flex-1 flex flex-col justify-center space-y-6 py-4">
                <div className="bg-white/5 rounded-[32px] p-8 backdrop-blur-sm border border-white/5 flex flex-col justify-center">
                  <div className="flex items-center gap-2 mb-6">
                    <div className="w-2 h-2 rounded-full bg-[#007AFF] shadow-[0_0_12px_rgba(0,122,255,0.8)]" />
                    <label className="text-[13px] font-black text-[#dfdfdf] uppercase tracking-widest">매수 결합 로직</label>
                  </div>
                  <div className="flex bg-black/40 rounded-[24px] p-2 mb-6">
                    <button onClick={() => setEntryLogic("AND")} className={`flex-1 py-4 text-[13px] font-black rounded-[18px] transition-all ${entryLogic === "AND" ? "bg-[rgb(55,122,244)] text-white shadow-[0_0_20px_rgba(55,122,244,0.4)] scale-[1.02]" : "text-[#a0a0a0] hover:text-white/60"}`}>AND</button>
                    <button onClick={() => setEntryLogic("OR")} className={`flex-1 py-4 text-[13px] font-black rounded-[18px] transition-all ${entryLogic === "OR" ? "bg-[rgb(55,122,244)] text-white shadow-[0_0_20px_rgba(55,122,244,0.4)] scale-[1.02]" : "text-[#a0a0a0] hover:text-white/60"}`}>OR</button>
                  </div>
                  <p className="text-[12px] text-[#a0a0a0] font-black uppercase tracking-tight leading-relaxed text-center px-2">{entryLogic === "AND" ? "모든 매수 블록의 조건이 동시에 충족되어야 합니다." : "매수 블록 중 하나만 충족되어도 신호가 발생합니다."}</p>
                </div>

                <div className="bg-white/5 rounded-[32px] p-8 backdrop-blur-sm border border-white/5 flex flex-col justify-center">
                  <div className="flex items-center gap-2 mb-6">
                    <div className="w-2 h-2 rounded-full bg-[#FF3B30] shadow-[0_0_15px_rgba(255,59,48,0.6)]" />
                    <label className="text-[13px] font-black text-[#dfdfdf] uppercase tracking-widest">매도 결합 로직</label>
                  </div>
                  <div className="flex bg-black/40 rounded-[24px] p-2 mb-6">
                    <button onClick={() => setExitLogic("AND")} className={`flex-1 py-4 text-[13px] font-black rounded-[18px] transition-all ${exitLogic === "AND" ? "bg-[rgb(55,122,244)] text-white shadow-[0_0_20px_rgba(55,122,244,0.4)] scale-[1.02]" : "text-[#a0a0a0] hover:text-white/60"}`}>AND</button>
                    <button onClick={() => setExitLogic("OR")} className={`flex-1 py-4 text-[13px] font-black rounded-[18px] transition-all ${exitLogic === "OR" ? "bg-[rgb(55,122,244)] text-white shadow-[0_0_20px_rgba(55,122,244,0.4)] scale-[1.02]" : "text-[#a0a0a0] hover:text-white/60"}`}>OR</button>
                  </div>
                  <p className="text-[12px] text-[#a0a0a0] font-black uppercase tracking-tight leading-relaxed text-center px-2">{exitLogic === "AND" ? "모든 매도 블록의 조건이 동시에 충족되어야 합니다." : "매도 블록 중 하나만 충족되어도 신호가 발생합니다."}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="h-8" />

      {/* macOS-style Bottom Toolbar */}
      <div className="sticky bottom-0 left-0 right-0 bg-[#0f0f0f] backdrop-blur-3xl px-8 py-5 z-[60]">
        <div className="max-w-full mx-auto flex items-center justify-between">
          <div className="flex items-center gap-12">
            <div className="flex items-center gap-6">
              <div className="w-16 h-16 bg-[rgb(59, 134, 247)] rounded-[24px] flex items-center justify-center shadow-[0_0_40px_rgba(0,122,255,0.4)]">
                <CpuChipIcon className="w-8 h-8 text-white" />
              </div>
              <div className="space-y-1">
                <h4 className="text-xl font-black text-[#dfdfdf] tracking-tight uppercase">로직 설계 요약</h4>
              </div>
            </div>
            
            <div className="h-12 w-px bg-white/5" />
            
            <div className="flex gap-12">
              <div className="flex flex-col">
                <span className="text-xs font-bold text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">총 블록</span>
                <span className="text-2xl font-bold text-[#dfdfdf] tabular-nums tracking-tight">{canvasBlocks.length}개</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-bold text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">매수 로직</span>
                <span className="text-2xl font-bold text-[#dfdfdf] tabular-nums tracking-tight">{entryLogic}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-bold text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">매도 로직</span>
                <span className="text-2xl font-bold text-[#dfdfdf] tabular-nums tracking-tight">{exitLogic}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button 
              onClick={onPrev} 
              className="px-8 py-5 bg-white/5 text-white/40 rounded-[24px] text-lg font-black hover:bg-white/10 hover:text-white transition-all flex items-center gap-4 active:scale-95"
            >
              <ArrowLeftIcon className="w-6 h-6" /> 이전
            </button>
            <button 
              onClick={onNext} 
              className="group px-12 py-5 bg-[#161616] text-white rounded-[24px] text-lg font-black hover:bg-[#1f1f1f] transition-all flex items-center gap-4 shadow-[0_20px_40px_rgba(0,0,0,0.3)] hover:scale-105 active:scale-95"
            >
              포지션 설계하기 <ArrowRightIcon className="w-6 h-6 group-hover:translate-x-2 transition-transform duration-500 text-white" />
            </button>
          </div>
        </div>
      </div>

      {hoveredEditIcon && (
        <div className="fixed z-[1000] pointer-events-none" style={{ left: hoveredEditIcon.rect.left + (hoveredEditIcon.rect.width / 2), top: hoveredEditIcon.rect.bottom + 8, transform: 'translateX(-50%)' }}>
          <div className="px-3 py-1.5 bg-[#0a0a0a] rounded-lg shadow-xl animate-in fade-in zoom-in-95 slide-in-from-top-2 duration-200">
            <p className="text-[11px] text-white/40 font-black uppercase tracking-widest whitespace-nowrap">{hoveredEditIcon.label}</p>
          </div>
        </div>
      )}

      {hoveredInfo && (
        <div className="fixed z-[1000] pointer-events-none" style={{ left: hoveredInfo.rect.right + 12, top: hoveredInfo.rect.top + (hoveredInfo.rect.height / 2), transform: 'translateY(-50%)' }}>
          <div className="w-80 p-5 bg-[#161616] rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 slide-in-from-left-2 duration-200 backdrop-blur-3xl border border-white/10">
            <p className="text-xs text-white/75 font-bold leading-relaxed">{signalBlocks[hoveredInfo.id]?.description || "설명 없음"}</p>
          </div>
        </div>
      )}

      {hoveredParam && (
        <div className="fixed z-[1000] pointer-events-none" style={{ left: hoveredParam.rect.left - 270, top: hoveredParam.rect.top + (hoveredParam.rect.height / 2), transform: 'translateY(-50%)' }}>
          <div className="w-64 p-5 bg-[#161616] rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 slide-in-from-right-2 duration-200 backdrop-blur-2xl border border-white/10">
            <div className="text-[10px] text-[rgb(59, 134, 247)] font-bold uppercase tracking-widest mb-2 opacity-50">{hoveredParam.label}</div>
            <p className="text-xs text-white/75 font-bold leading-relaxed">{hoveredParam.tooltip}</p>
          </div>
        </div>
      )}

      {isLibraryManagementOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md" onClick={() => setIsLibraryManagementOpen(false)}>
          <div className="w-full max-w-4xl h-[750px] bg-[#161616]/90 rounded-[40px] shadow-2xl flex flex-col backdrop-blur-2xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="p-8 flex items-center justify-between bg-black/20">
              <h3 className="text-2xl font-black text-white uppercase tracking-tight">보관함 관리</h3>
              <button 
                onClick={() => setIsLibraryManagementOpen(false)}
                className="w-12 h-12 bg-white/5 rounded-2xl flex items-center justify-center text-white/40 hover:text-white hover:bg-white/10 transition-all"
              >
                <XMarkIcon className="w-6 h-6" />
              </button>
            </div>
            <div className="flex-1 flex overflow-hidden">
              <div className="w-72 bg-black/20 flex flex-col p-4 space-y-2">
                {customCategoryOrder.map((key) => {
                  const group = (groupedSignalLibrary as any)[key];
                  if (!group) return null;
                  return (
                    <div 
                      key={key} 
                      onDragOver={handleReorderDragOver}
                      onDrop={(e) => handleReorderDrop(e, { type: 'category', id: key, index: customCategoryOrder.indexOf(key) })}
                      className={`flex items-center gap-3 px-4 py-3.5 rounded-2xl cursor-pointer transition-all ${
                         activeMgmtCategory === key ? "bg-[rgb(59, 134, 247)] shadow-[0_10px_20px_rgba(0,122,255,0.2)]" : "hover:bg-white/5"
                      } ${reorderDragItem?.type === 'category' && reorderDragItem.id === key ? 'opacity-30' : ''}`}
                      onClick={() => setActiveMgmtCategory(key)}
                    >
                      <div 
                        className={`mr-1 cursor-grab active:cursor-grabbing ${activeMgmtCategory === key ? "text-white/60" : "text-white/20"}`}
                        draggable
                        onDragStart={(e) => handleReorderDragStart(e, { type: 'category', id: key, index: customCategoryOrder.indexOf(key) })}
                      >
                        <Bars3Icon className="w-4 h-4" />
                      </div>
                      <group.icon className={`w-5 h-5 ${activeMgmtCategory === key ? "text-white" : "text-white/20"}`} />
                      <span className={`text-[13px] font-black uppercase truncate tracking-tight ${activeMgmtCategory === key ? "text-white" : "text-white/40"}`}>{group.label}</span>
                    </div>
                  );
                })}
              </div>
              <div className="flex-1 p-8 overflow-y-auto custom-scrollbar bg-black/10">
                {activeMgmtCategory && (
                  <div className="flex flex-col gap-3">
                    {(groupedSignalLibrary as any)[activeMgmtCategory].blocks.map((block: any) => (
                      <div
                        key={block.id}
                        className="pb-1"
                        onDragOver={handleReorderDragOver}
                        onDrop={(e) => handleReorderDrop(e, { type: 'block', id: block.id, index: -1, categoryId: activeMgmtCategory })}
                      >
                        <div 
                          className={`flex items-center justify-between p-5 bg-white/5 rounded-2xl transition-all shadow-sm ${
                            reorderDragItem?.type === 'block' && reorderDragItem.id === block.id ? 'opacity-30' : ''
                          }`}
                        >
                          <div className="flex items-center gap-4">
                            <div
                               className="cursor-grab active:cursor-grabbing text-white/20 hover:text-[rgb(59, 134, 247)]"
                               draggable
                               onDragStart={(e) => handleReorderDragStart(e, { type: 'block', id: block.id, index: -1, categoryId: activeMgmtCategory })}
                            >
                              <Bars3Icon className="w-5 h-5" />
                            </div>
                            <span className="text-white font-black tracking-tight">{block.name}</span>
                          </div>
                          <button 
                            onClick={(e) => handleRemoveBlockFromBin(block.id, e)} 
                            className="w-10 h-10 flex items-center justify-center bg-white/5 rounded-xl text-white/20 hover:text-[#FF3B30] hover:bg-[#FF3B30]/10 transition-all"
                          >
                            <XMarkIcon className="w-5 h-5" />
                          </button>
                        </div>
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
    </div>
  );
}
