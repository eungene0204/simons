"use client";

import { Fragment, useMemo, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  CaretDown,
  CaretUp,
  Info,
  Plus,
  MagnifyingGlass,
  ArrowRight,
  ArrowLeft,
  Cube,
  Sliders,
  Sparkle,
  ShieldWarning,
  Cpu,
  ChartBar,
  ArrowsClockwise,
  Bank,
  ChartPie,
  DotsThreeOutline,
  HandPointing,
  SquaresFour,
  List,
  Globe,
  Database,
  FramerLogo,
} from "phosphor-react";
import { CanvasBlock, LogicOperator } from "@/types/strategy";
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
  openSignalGroups,
  setOpenSignalGroups,
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
  const paramPopupRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setOpenSignalGroups([]);
      }
      
      const target = event.target as Element;
      const isCanvasBlock = target.closest?.('[data-canvas-block="true"]');
      if (
        paramPopupRef.current && 
        !paramPopupRef.current.contains(target) &&
        !isCanvasBlock
      ) {
        setSelectedBlock(null);
      }
    };

    if (openSignalGroups.length > 0 || selectedBlock) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [openSignalGroups, setOpenSignalGroups, selectedBlock, setSelectedBlock]);

  const blocksPerRow = canvasWidth > 1200 ? 8 : canvasWidth > 900 ? 6 : canvasWidth > 600 ? 4 : Math.max(1, Math.floor((canvasWidth - 30) / 150));
  const totalGridWidth = blocksPerRow * 150 - 30;
  const sidePadding = Math.max(15, (canvasWidth - totalGridWidth) / 2);

  const groupedSignalLibrary = useMemo(() => {
    return {
      filter: {
        key: "filter",
        label: "종목 필터",
        icon: Sliders,
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
        label: "매매 시그널",
        icon: Sparkle,
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
        label: "리스크",
        icon: ShieldWarning,
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
        label: "AI 모델",
        icon: Cpu,
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

  const entryBlocksCount = canvasBlocks.filter(b => b.type === 'entry').length;
  const exitBlocksCount = canvasBlocks.filter(b => b.type === 'exit').length;

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-[#0a0a0a] font-sans">
      {/* Top Header Section - Tiled Header */}
      <div className="flex shrink-0 items-center justify-between bg-[#111111] border-b border-white/5 px-8 py-5 shadow-xl relative z-40">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-[rgb(59,134,247)]/10 rounded-xl flex items-center justify-center border border-[rgb(59,134,247)]/20 shadow-[0_0_15px_rgba(59,134,247,0.1)]">
            <Cpu size={28} className="text-[rgb(59,134,247)]" />
          </div>
          <div>
            <h3 className="text-2xl font-black text-white tracking-tight">매매 로직 설계</h3>
            <p className="text-xs text-white/40 mt-1 font-black uppercase tracking-[0.2em]">
              매매 전략 로직을 설계하세요
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          {/* Entry Logic Switcher */}
          <div className="flex items-center gap-3 bg-black/20 rounded-xl p-1.5 border border-white/5">
            <span className="text-[11px] font-black text-red-500/80 uppercase tracking-widest px-2">진입</span>
            <div className="flex bg-[#161616] rounded-lg p-0.5 border border-white/5 shadow-inner">
              <button 
                onClick={() => setEntryLogic("AND")} 
                className={`px-4 py-1.5 text-xs font-black rounded-md transition-all duration-300 ${entryLogic === "AND" ? "bg-[rgb(55,122,244)] text-white shadow-lg" : "text-white/30 hover:text-white/60"}`}
              >
                AND
              </button>
              <button 
                onClick={() => setEntryLogic("OR")} 
                className={`px-4 py-1.5 text-xs font-black rounded-md transition-all duration-300 ${entryLogic === "OR" ? "bg-[rgb(55,122,244)] text-white shadow-lg" : "text-white/30 hover:text-white/60"}`}
              >
                OR
              </button>
            </div>
          </div>

          {/* Exit Logic Switcher */}
          <div className="flex items-center gap-3 bg-black/20 rounded-xl p-1.5 border border-white/5">
            <span className="text-[11px] font-black text-blue-500/80 uppercase tracking-widest px-2">청산</span>
            <div className="flex bg-[#161616] rounded-lg p-0.5 border border-white/5 shadow-inner">
              <button 
                onClick={() => setExitLogic("AND")} 
                className={`px-4 py-1.5 text-xs font-black rounded-md transition-all duration-300 ${exitLogic === "AND" ? "bg-[rgb(55,122,244)] text-white shadow-lg" : "text-white/30 hover:text-white/60"}`}
              >
                AND
              </button>
              <button 
                onClick={() => setExitLogic("OR")} 
                className={`px-4 py-1.5 text-xs font-black rounded-md transition-all duration-300 ${exitLogic === "OR" ? "bg-[rgb(55,122,244)] text-white shadow-lg" : "text-white/30 hover:text-white/60"}`}
              >
                OR
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Tiled Grid */}
      <div className="flex-1 grid grid-cols-12 gap-0 min-h-0 overflow-hidden">
        
        {/* Left Side: Library (col-span-2) */}
        <div className="col-span-2 bg-[#0d0d0d] border-r border-white/5 flex flex-col shadow-2xl relative z-30">
          <div className="p-5 border-b border-white/5 bg-white/[0.01]">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3.5">
                <SquaresFour size={32} className="text-[rgb(59,134,247)]" />
                <h3 className="text-xl font-black text-white/90 uppercase tracking-tight">라이브러리</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsLibraryManagementOpen(true)}
                className="p-1.5 bg-black/40 border border-white/5 rounded-xl text-white/20 hover:text-white hover:bg-black/60 transition-all"
              >
                <DotsThreeOutline size={20} />
              </button>
            </div>

            <button
              type="button"
              onClick={() => setIsSearchMenuOpen(!isSearchMenuOpen)}
              className={`w-full flex items-center gap-3 px-3 py-3.5 rounded-2xl transition-all border ${
                isSearchMenuOpen
                  ? "bg-white text-black border-transparent shadow-[0_0_30px_rgba(255,255,255,0.15)]"
                  : "bg-black/40 text-white/40 hover:text-white hover:bg-black/60 border-white/5"
              }`}
            >
              <MagnifyingGlass size={20} />
              <span className="text-[11px] font-black uppercase tracking-widest leading-none pt-0.5">블록 검색...</span>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto custom-scrollbar p-2.5 space-y-1">
            {customCategoryOrder.map((key) => {
              const group = (groupedSignalLibrary as any)[key];
              if (!group) return null;
              const filteredBlocks = group.blocks;
              const isOpen = openSignalGroups.includes(group.key);
              
              return (
                <div key={group.key} className="space-y-0.5">
                  <button
                    type="button"
                    onClick={() => setOpenSignalGroups((prev) => 
                      prev.includes(group.key) ? [] : [group.key]
                    )}
                    className={`w-full flex items-center justify-between px-3 py-3.5 rounded-xl transition-all duration-300 ${
                      isOpen ? "bg-white/[0.05] text-white" : "text-white/20 hover:text-white/40 hover:bg-white/[0.02]"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                       <group.icon className={`w-5 h-5 ${isOpen ? "text-[rgb(59,134,247)]" : "text-white/10"}`} />
                       <span className="text-sm font-black tracking-tight">{group.label}</span>
                    </div>
                    <CaretDown size={16} className={`transition-transform duration-300 ${isOpen ? "rotate-180 text-white" : "text-white/10"}`} />
                  </button>

                  <AnimatePresence>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden bg-black/10 rounded-xl mb-1"
                      >
                        <div className="p-1 space-y-1">
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
                                className="group p-3 bg-white/[0.02] hover:bg-[rgb(59,134,247)] rounded-xl text-sm font-black text-white/30 hover:text-white cursor-move transition-all flex items-center justify-between border border-transparent hover:border-white/10"
                              >
                                <span className="truncate pr-2 tracking-tight">{block.name}</span>
                                <Info 
                                  size={16}
                                  className="text-white/5 group-hover:text-white/40 cursor-help"
                                  onMouseEnter={(e) => setHoveredInfo({ id: block.id, rect: e.currentTarget.getBoundingClientRect() })}
                                  onMouseLeave={() => setHoveredInfo(null)}
                                />
                              </div>
                            );
                          })}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        </div>

        {/* Center: Canvas (col-span-8) */}
        <div className="col-span-8 bg-[#0a0a0a] border-r border-white/5 overflow-hidden relative shadow-inner flex flex-col transition-all duration-500 z-20">
          {/* Grid Background */}
          <div className="absolute inset-0 pointer-events-none opacity-[0.03]" 
               style={{ 
                 backgroundImage: `radial-gradient(circle at 1.5px 1.5px, #fff 1.5px, transparent 0)`,
                 backgroundSize: "32px 32px" 
               }} />

          <div 
            ref={canvasRef}
            className="flex-1 relative min-h-0"
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
            {canvasBlocks.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-[1]">
                <div className="text-center space-y-6">
                  <div className="w-20 h-20 bg-white/[0.02] rounded-3xl border border-white/5 flex items-center justify-center mx-auto shadow-inner backdrop-blur-sm">
                    <Plus size={32} className="text-white/5" />
                  </div>
                  <div>
                    <h4 className="text-white/20 font-black uppercase tracking-[0.3em] text-xs mb-2">전략 초기화</h4>
                    <p className="text-[11px] text-white/10 font-black uppercase tracking-widest max-w-[240px]">
                      라이브러리에서 블록을 드래그하여 <br /> 로직을 정의하세요
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="absolute inset-0 overflow-auto custom-scrollbar">
              <div className="w-full h-full relative" style={{ minWidth: canvasWidth, minHeight: Math.ceil(canvasBlocks.length / blocksPerRow) * 150 + 100 }}>
                {/* SVG Connections Layer */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
                  <defs>
                    <filter id="glow-red" x="-20%" y="-20%" width="140%" height="140%">
                      <feGaussianBlur stdDeviation="3" result="blur" />
                      <feComposite in="SourceGraphic" in2="blur" operator="over" />
                    </filter>
                    <filter id="glow-blue" x="-20%" y="-20%" width="140%" height="140%">
                      <feGaussianBlur stdDeviation="3" result="blur" />
                      <feComposite in="SourceGraphic" in2="blur" operator="over" />
                    </filter>
                  </defs>
                  {canvasBlocks.map((block, index) => {
                    if (index === canvasBlocks.length - 1) return null;
                    const nextBlock = canvasBlocks[index + 1];
                    const isEntryOrFilter = (b: CanvasBlock) => b.type === "entry" || b.type === "filter";
                    const isExit = (b: CanvasBlock) => b.type === "exit";
                    
                    let shouldConnect = false;
                    let color = "#4B5563";
                    let filterUrl = "";

                    if (isEntryOrFilter(block) && isEntryOrFilter(nextBlock)) {
                      shouldConnect = entryLogic === "AND";
                      color = "#EF4444";
                      filterUrl = "url(#glow-red)";
                    } else if (isExit(block) && isExit(nextBlock)) {
                      shouldConnect = exitLogic === "AND";
                      color = "#3B82F6";
                      filterUrl = "url(#glow-blue)";
                    }

                    if (!shouldConnect) return null;

                    const col = index % blocksPerRow;
                    const row = Math.floor(index / blocksPerRow);
                    const nextCol = (index + 1) % blocksPerRow;
                    const nextRow = Math.floor((index + 1) / blocksPerRow);
                    const startX = sidePadding + col * 150 + 120;
                    const startY = 80 + row * 140 + 35;
                    let endX, endY;
                    const isNewRow = nextRow > row;
                    if (isNewRow) {
                      endX = sidePadding + nextCol * 150 + 60;
                      endY = 80 + nextRow * 140;
                    } else {
                      endX = sidePadding + nextCol * 150;
                      endY = 80 + nextRow * 140 + 35;
                    }
                    const dx = endX - startX;
                    let pathD;
                    if (isNewRow) {
                      const gutterY = startY + (endY - startY) / 2;
                      pathD = `M ${startX} ${startY} C ${startX + 40} ${startY}, ${startX + 40} ${gutterY}, ${startX} ${gutterY} L ${endX + 40} ${gutterY} C ${endX} ${gutterY}, ${endX} ${gutterY}, ${endX} ${endY}`;
                    } else {
                      const offset = Math.min(Math.max(dx * 0.4, 30), 50);
                      pathD = `M ${startX} ${startY} C ${startX + offset} ${startY} ${endX - offset} ${endY} ${endX} ${endY}`;
                    }

                    return (
                      <g key={`flow-${block.id}-${nextBlock.id}`}>
                        <path d={pathD} stroke={color} strokeWidth="6" fill="none" className="opacity-[0.05]" filter={filterUrl} />
                        <path d={pathD} stroke={color} strokeWidth="2" fill="none" className="opacity-30" />
                        <path d={pathD} stroke={color} strokeWidth="2" fill="none" strokeDasharray="6,14" className="opacity-50 animate-dash" />
                      </g>
                    );
                  })}
                </svg>

                {/* Blocks Layer */}
                {canvasBlocks.map((block, index) => {
                  const colIdx = index % blocksPerRow;
                  const rowIdx = Math.floor(index / blocksPerRow);
                  const xOffset = sidePadding + colIdx * 150;
                  const yOffset = 80 + rowIdx * 140;
                  const isSelected = selectedBlock?.id === block.id;

                  let typeColor = "rgb(100,155,107)";
                  let typeLabel = "필터";
                  if (block.type === "entry") {
                    typeColor = "#EF4444";
                    typeLabel = "매수";
                  } else if (block.type === "exit") {
                    typeColor = "#3B82F6";
                    typeLabel = "매도";
                  }

                  return (
                    <motion.div
                      key={block.id}
                      initial={{ scale: 0.8, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      onClick={() => {
                        setSelectedBlock(block);
                        setActiveParamTab('block');
                      }}
                      className={`absolute p-6 rounded-2xl transition-all duration-400 border backdrop-blur-xl group cursor-pointer ${
                        isSelected 
                        ? "bg-white/[0.08] border-white/20 ring-2 ring-[rgb(59,134,247)]/40 shadow-2xl z-20 scale-105" 
                        : "bg-white/[0.04] border-white/5 hover:border-white/10 hover:bg-white/[0.06] shadow-lg z-10"
                      }`}
                      style={{ 
                        left: `${xOffset}px`, 
                        top: `${yOffset}px`, 
                        width: "140px",
                        boxShadow: isSelected ? `0 20px 40px -10px rgba(0,0,0,0.5), 0 0 20px -5px ${typeColor}40` : ""
                      }}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full shadow-lg" style={{ backgroundColor: typeColor }} />
                          <span className="text-[11px] font-black uppercase tracking-widest" style={{ color: typeColor }}>
                            {typeLabel}
                          </span>
                        </div>
                      </div>
                      <div className={`text-[15px] font-black tracking-tight leading-tight ${isSelected ? "text-white" : "text-white/60 group-hover:text-white/90"}`}>
                        {signalBlocks[block.blockId]?.name || block.blockId}
                      </div>

                      <button 
                        onClick={(e) => { 
                          e.stopPropagation(); 
                          setCanvasBlocks(canvasBlocks.filter(b => b.id !== block.id)); 
                          if (selectedBlock?.id === block.id) setSelectedBlock(null); 
                        }} 
                        className="absolute -top-3 -right-3 w-8 h-8 bg-black/80 border border-white/10 text-white/40 rounded-full opacity-0 group-hover:opacity-100 transition-all hover:text-white hover:bg-red-500 hover:border-transparent flex items-center justify-center shadow-xl backdrop-blur-sm"
                      >
                        <X size={20} />
                      </button>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Right Side: Shared Panel (col-span-2) */}
        <div className="col-span-2 bg-[#0d0d0d] flex flex-col shadow-2xl relative z-30 overflow-hidden">
          <div className="flex-1 flex flex-col min-h-0">
            <AnimatePresence mode="wait">
              {selectedBlock ? (
                /* Parameter Editor View */
                <motion.div
                  key="params"
                  initial={{ x: 20, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: 20, opacity: 0 }}
                  className="flex-1 flex flex-col min-h-0"
                >
                  <div className="p-5 border-b border-white/5 bg-white/[0.01]">
                    <div className="flex items-center justify-between mb-5">
                      <div className="flex items-center gap-3.5">
                        <Sliders size={32} className="text-[rgb(59,134,247)]" />
                        <h3 className="text-xl font-black text-white/90 uppercase tracking-tight">속성</h3>
                      </div>
                      <button 
                        onClick={() => setSelectedBlock(null)}
                        className="p-1.5 hover:bg-white/5 rounded-xl transition-colors text-white/20 hover:text-white"
                      >
                        <X size={20} />
                      </button>
                    </div>

                    <div className="bg-black/40 rounded-2xl p-4 border border-white/5 shadow-inner">
                      <h4 className="text-sm font-black text-white mb-2 uppercase tracking-tight">{signalBlocks[selectedBlock.blockId]?.name}</h4>
                      <p className="text-[11px] text-white/20 font-medium leading-relaxed">파라미터를 설정하세요.</p>
                    </div>
                  </div>

                  <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-6">
                    {(() => {
                      const blockDef = signalBlocks[selectedBlock.blockId];
                      if (!blockDef || !blockDef.paramSchema) return <div className="text-sm text-white/20 text-center italic">설정 가능한 파라미터가 없습니다</div>;

                      return Object.entries(blockDef.paramSchema).map(([key, param]) => {
                        const value = selectedBlock.params[key] ?? blockDef.defaultParams[key];
                        return (
                          <div key={key} className="space-y-3 group">
                            <div className="flex items-center justify-between px-1">
                              <label className="text-[11px] font-black text-white/30 uppercase tracking-[0.15em]">{param.label}</label>
                              <span className="text-sm font-black text-[rgb(59,134,247)] tabular-nums">{value}{param.suffix}</span>
                            </div>
                            
                            <div className="flex items-center px-3 py-3.5 bg-black/40 border border-white/5 rounded-xl group-hover:border-white/10 transition-all shadow-inner">
                              <input
                                type="text"
                                value={value === 0 ? "" : value}
                                placeholder="0"
                                onChange={(e) => {
                                  const rawValue = e.target.value;
                                  const val = rawValue === "" ? 0 : isNaN(parseFloat(rawValue)) ? 0 : parseFloat(rawValue);
                                  const newParams = { ...selectedBlock.params, [key]: val };
                                  setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams } : b));
                                  setSelectedBlock({ ...selectedBlock, params: newParams });
                                }}
                                className="flex-1 bg-transparent text-sm font-black text-white outline-none tabular-nums placeholder:text-white/[0.05]"
                              />
                              {param.suffix && (
                                <span className="text-xs font-black text-white/20 uppercase tracking-widest">{param.suffix}</span>
                              )}
                            </div>
                          </div>
                        );
                      });
                    })()}
                  </div>

                  <div className="p-5 bg-white/[0.01] border-t border-white/5 space-y-3">
                    <button 
                      onClick={() => setSelectedBlock(null)}
                      className="w-full py-4 rounded-xl bg-[rgb(59,134,247)] text-white text-xs font-black uppercase tracking-widest hover:bg-[#4B9FFF] transition-all shadow-xl shadow-blue-500/10 active:scale-[0.98]"
                    >
                      변경사항 적용
                    </button>
                    <button 
                      onClick={() => {
                        setCanvasBlocks(canvasBlocks.filter(b => b.id !== selectedBlock?.id));
                        setSelectedBlock(null);
                      }}
                      className="w-full py-4 rounded-xl text-white/20 text-xs font-black uppercase tracking-widest hover:text-red-500 hover:bg-red-500/5 transition-all"
                    >
                      블록 삭제
                    </button>
                  </div>
                </motion.div>
              ) : (
                /* Logic Summary View - Redesigned to match Step 1 */
                <motion.div
                  key="summary"
                  initial={{ x: -20, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: -20, opacity: 0 }}
                  className="flex-1 flex flex-col min-h-0 p-8"
                >
                  <div className="flex items-center gap-3 mb-10">
                    <ChartBar size={24} className="text-blue-500" />
                    <h3 className="text-base font-black text-white/60 uppercase tracking-widest">매매 로직 요약</h3>
                  </div>

                  <div className="space-y-8 flex-1 overflow-y-auto custom-scrollbar">
                    {/* Total Blocks Section */}
                    <div>
                      <div className="flex items-center gap-2 mb-3">
                        <SquaresFour size={20} className="text-blue-500" />
                        <span className="text-sm font-black text-white/40 uppercase tracking-widest">전체 블록 수</span>
                      </div>
                      <span className="text-2xl font-black text-white block pl-8 tracking-tight">{canvasBlocks.length}개</span>
                    </div>

                    {/* Entry Strategy Section */}
                    <div>
                      <div className="flex items-center gap-2 mb-3">
                        <ArrowsClockwise size={20} className="text-blue-500" />
                        <span className="text-sm font-black text-white/40 uppercase tracking-widest">진입 조건</span>
                      </div>
                      <div className="flex items-center gap-3 pl-8">
                        <span className="text-2xl font-black text-white tracking-tight">{entryBlocksCount}개</span>
                        <span className="px-2 py-0.5 border-2 border-blue-500/30 bg-blue-500/10 text-blue-400 text-[10px] font-black rounded-lg">{entryLogic}</span>
                      </div>
                    </div>

                    {/* Exit Strategy Section */}
                    <div>
                      <div className="flex items-center gap-2 mb-3">
                        <ArrowsClockwise size={20} className="text-blue-500 rotate-180" />
                        <span className="text-sm font-black text-white/40 uppercase tracking-widest">청산 조건</span>
                      </div>
                      <div className="flex items-center gap-3 pl-8">
                        <span className="text-2xl font-black text-white tracking-tight">{exitBlocksCount}개</span>
                        <span className="px-2 py-0.5 border-2 border-blue-500/30 bg-blue-500/10 text-blue-400 text-[10px] font-black rounded-lg">{exitLogic}</span>
                      </div>
                    </div>
                  </div>

                  <div className="pt-8 border-t border-white/5 flex gap-3 mt-auto">
                    <button 
                      onClick={onPrev} 
                      className="px-5 py-4 bg-black/40 hover:bg-black/60 text-white rounded-xl text-base font-black transition-all border border-white/5 active:scale-95 shadow-lg"
                    >
                      <ArrowLeft size={20} />
                    </button>
                    <button 
                      onClick={onNext} 
                      className="flex-1 group px-4 py-4 bg-blue-500 hover:bg-blue-400 text-white rounded-xl text-sm font-black uppercase tracking-widest transition-all flex items-center justify-between shadow-[0_10px_30px_rgba(59,130,246,0.1)] active:scale-[0.98]"
                    >
                      <span>포지션 설계</span>
                      <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* Overlays / Popovers */}
      {hoveredEditIcon && (
        <div className="fixed z-[1000] pointer-events-none" style={{ left: hoveredEditIcon.rect.left + (hoveredEditIcon.rect.width / 2), top: hoveredEditIcon.rect.top - 8, transform: 'translate(-50%, -100%)' }}>
          <div className="px-4 py-2 bg-[#0a0a0a] rounded-lg shadow-xl animate-in fade-in zoom-in-95 slide-in-from-bottom-2 duration-200">
            <p className="text-xs text-white/40 font-black uppercase tracking-widest whitespace-nowrap">{hoveredEditIcon.label}</p>
          </div>
        </div>
      )}

      {hoveredInfo && (
        <div className="fixed z-[1000] pointer-events-none" style={{ left: hoveredInfo.rect.right + 12, top: hoveredInfo.rect.top + (hoveredInfo.rect.height / 2), transform: 'translateY(-50%)' }}>
          <div className="w-80 p-6 bg-[#161616] rounded-2xl shadow-2xl border border-white/10 backdrop-blur-3xl">
            <p className="text-sm text-white/75 font-bold leading-relaxed">{signalBlocks[hoveredInfo.id]?.description || "설명이 제공되지 않았습니다."}</p>
          </div>
        </div>
      )}

      {hoveredParam && (
        <div className="fixed z-[1000] pointer-events-none" style={{ left: hoveredParam.rect.left - 270, top: hoveredParam.rect.top + (hoveredParam.rect.height / 2), transform: 'translateY(-50%)' }}>
          <div className="w-72 p-6 bg-[#161616] rounded-2xl shadow-2xl border border-white/10 backdrop-blur-2xl">
            <div className="text-[11px] text-[rgb(59, 134, 247)] font-bold uppercase tracking-widest mb-2 opacity-50">{hoveredParam.label}</div>
            <p className="text-sm text-white/75 font-bold leading-relaxed">{hoveredParam.tooltip}</p>
          </div>
        </div>
      )}

      {isLibraryManagementOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md" onClick={() => setIsLibraryManagementOpen(false)}>
          <div className="w-full max-w-4xl h-[650px] bg-[#161616]/90 rounded-3xl shadow-2xl flex flex-col backdrop-blur-2xl overflow-hidden border border-white/10" onClick={(e) => e.stopPropagation()}>
            <div className="p-8 flex items-center justify-between border-b border-white/5">
              <div className="flex items-center gap-4">
                 <div className="w-12 h-12 bg-white/5 rounded-xl flex items-center justify-center">
                    <SquaresFour size={28} className="text-[rgb(59,134,247)]" />
                 </div>
                 <h3 className="text-2xl font-black text-white uppercase tracking-tight">보관함 관리</h3>
              </div>
              <button 
                onClick={() => setIsLibraryManagementOpen(false)}
                className="w-12 h-12 bg-white/5 rounded-xl flex items-center justify-center text-white/40 hover:text-white hover:bg-white/10 transition-all"
              >
                <X size={24} />
              </button>
            </div>
            <div className="flex-1 flex overflow-hidden">
               {/* Categories Panel */}
               <div className="w-72 bg-black/20 border-r border-white/5 flex flex-col p-4 space-y-2">
                 {customCategoryOrder.map((key) => {
                   const group = (groupedSignalLibrary as any)[key];
                   if (!group) return null;
                   return (
                     <button 
                       key={key} 
                       onClick={() => setActiveMgmtCategory(key)}
                       className={`w-full flex items-center gap-4 px-5 py-4 rounded-xl transition-all ${
                          activeMgmtCategory === key ? "bg-[rgb(59, 134, 247)] text-white shadow-lg" : "text-white/30 hover:bg-white/5"
                       }`}
                     >
                       <group.icon className="w-6 h-6 shrink-0" />
                       <span className="text-xs font-black uppercase tracking-widest truncate">{group.label}</span>
                     </button>
                   );
                 })}
               </div>
               
               {/* Items Grid */}
               <div className="flex-1 p-8 overflow-y-auto custom-scrollbar bg-black/10">
                 {activeMgmtCategory && (
                    <div className="grid grid-cols-2 gap-5">
                      {(groupedSignalLibrary as any)[activeMgmtCategory].blocks.map((block: any) => (
                         <div key={block.id} className="flex items-center justify-between p-5 bg-white/[0.03] border border-white/5 rounded-2xl">
                           <span className="text-sm font-black text-white/70">{block.name}</span>
                           <button 
                              onClick={(e) => handleRemoveBlockFromBin(block.id, e)}
                              className="w-10 h-10 rounded-lg bg-red-500/10 text-red-500/40 hover:text-red-500 hover:bg-red-500/20 transition-all flex items-center justify-center"
                           >
                              <X size={20} />
                           </button>
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
