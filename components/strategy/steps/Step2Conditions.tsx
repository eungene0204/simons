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
  Question,
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

  const blocksPerRow = canvasWidth > 1200 ? 6 : canvasWidth > 900 ? 4 : canvasWidth > 600 ? 3 : Math.max(1, Math.floor((canvasWidth - 40) / 220));
  const totalGridWidth = blocksPerRow * 220 - 60;
  const sidePadding = Math.max(20, (canvasWidth - totalGridWidth) / 2);

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
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-[#0a0a0a] font-sans relative">
      {/* Main Tiled Grid */}
      <div className="flex-1 grid grid-cols-12 gap-0 min-h-0 overflow-hidden">
        
        {/* Left Side: Library (col-span-3) */}
        <div className="col-span-3 bg-[#0d0d0d] border-r border-white/5 flex flex-col shadow-2xl relative z-30">
          <div className="p-5 border-b border-white/5 bg-white/[0.01]">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3.5">
                <h3 className="text-xl font-black text-white/90 uppercase tracking-tight">블록 라이브러리</h3>
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
              <span className="text-sm font-black uppercase tracking-widest leading-none pt-0.5">블록 검색...</span>
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
                      isOpen ? "bg-white/[0.05] text-white/70" : "text-white/70 hover:text-white hover:bg-white/[0.02]"
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
                                className="group p-3 bg-white/[0.02] hover:bg-[rgb(59,134,247)] rounded-xl text-sm font-black text-white cursor-move transition-all flex items-center justify-between border border-transparent hover:border-white/10"
                              >
                                <span className="truncate pr-2 tracking-tight">{block.name}</span>
                                <Info 
                                  size={16}
                                  className="text-white/40 group-hover:text-white/80 cursor-help"
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

        {/* Center: Canvas (col-span-9) */}
        <div className="col-span-9 bg-[#0a0a0a] overflow-hidden relative shadow-inner flex flex-col transition-all duration-500 z-20 pt-8">
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
              <div className="w-full h-full relative" style={{ minWidth: canvasWidth, minHeight: Math.ceil(canvasBlocks.length / blocksPerRow) * 200 + 120 }}>
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

                    // Connect only if: same signal type AND both blocks use AND logic
                    const sameType = block.type === nextBlock.type;
                    const bothAnd = (block.logic ?? "AND") === "AND" && (nextBlock.logic ?? "AND") === "AND";
                    if (!sameType || !bothAnd) return null;

                    let color = "#6B7280";
                    let filterUrl = "";
                    if (block.type === "entry") { color = "#EF4444"; filterUrl = "url(#glow-red)"; }
                    else if (block.type === "exit") { color = "#3B82F6"; filterUrl = "url(#glow-blue)"; }
                    else if (block.type === "filter") { color = "#22C55E"; filterUrl = ""; }

                    const col = index % blocksPerRow;
                    const row = Math.floor(index / blocksPerRow);
                    const nextCol = (index + 1) % blocksPerRow;
                    const nextRow = Math.floor((index + 1) / blocksPerRow);
                    const startX = sidePadding + col * 220 + 150;
                    const startY = 100 + row * 200 + 45;
                    let endX, endY;
                    const isNewRow = nextRow > row;
                    if (isNewRow) {
                      endX = sidePadding + nextCol * 220 + 80;
                      endY = 100 + nextRow * 200;
                    } else {
                      endX = sidePadding + nextCol * 220;
                      endY = 100 + nextRow * 200 + 45;
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
                  const xOffset = sidePadding + colIdx * 220;
                  const yOffset = 100 + rowIdx * 200;
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
                        width: "160px",
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
      </div>

      {/* Floating: Block Param Editor */}
      <AnimatePresence>
        {selectedBlock && (
          <motion.div
            ref={paramPopupRef}
            key="params"
            initial={{ x: 20, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 20, opacity: 0 }}
            className="absolute top-4 right-4 w-72 bg-[#0d0d0d] border border-white/10 rounded-2xl shadow-2xl flex flex-col z-50 overflow-hidden"
          >
            <div className="p-5 border-b border-white/5 bg-white/[0.01]">
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3.5">
                  <Sliders size={24} className="text-[rgb(59,134,247)]" />
                  <h3 className="text-sm font-black text-white/90 uppercase tracking-tight">속성</h3>
                </div>
                <button 
                  onClick={() => setSelectedBlock(null)}
                  className="p-1.5 hover:bg-white/5 rounded-xl transition-colors text-white/20 hover:text-white"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="bg-black/40 rounded-2xl p-4 border border-white/5 shadow-inner">
                <h4 className="text-sm font-black text-white mb-2 uppercase tracking-tight">{signalBlocks[selectedBlock.blockId]?.name}</h4>
                {signalBlocks[selectedBlock.blockId]?.description ? (
                  <p className="text-[11px] text-white/50 font-medium leading-relaxed">{signalBlocks[selectedBlock.blockId].description}</p>
                ) : (
                  <p className="text-[11px] text-white/20 font-medium leading-relaxed">파라미터를 설정하세요.</p>
                )}
              </div>

              {/* Per-block AND/OR logic selector */}
              <div className="mt-4 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-black text-white/40 uppercase tracking-widest">로직 종류</span>
                  <Question
                    size={14}
                    className="text-white/30 hover:text-blue-400 cursor-help transition-colors"
                    onMouseEnter={(e) => setHoveredParam({
                      label: "로직 종류",
                      tooltip: "AND: 전략 내 모든 블록의 조건이 동시에 충족될 때만 매매 신호가 발생합니다. 조건이 더 까다롭지만 신뢰도가 높습니다.\nOR: 이 블록 하나의 조건만 충족되어도 바로 매매 신호가 발생합니다. 더 자주 매매가 이루어집니다.",
                      rect: e.currentTarget.getBoundingClientRect()
                    })}
                    onMouseLeave={() => setHoveredParam(null)}
                  />
                </div>
                <div className="flex bg-black/40 rounded-lg p-0.5 border border-white/5">
                  {(["AND", "OR"] as const).map((op) => (
                    <button
                      key={op}
                      onClick={() => {
                        const updated = canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, logic: op } : b);
                        setCanvasBlocks(updated);
                        setSelectedBlock({ ...selectedBlock, logic: op });
                      }}
                      className={`px-4 py-1.5 text-xs font-black rounded-md transition-all duration-200 ${
                        (selectedBlock.logic ?? "AND") === op
                          ? "bg-[rgb(59,134,247)] text-white shadow"
                          : "text-white/30 hover:text-white/60"
                      }`}
                    >
                      {op}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="overflow-y-auto custom-scrollbar p-5 space-y-6 max-h-80">
              {(() => {
                const blockDef = signalBlocks[selectedBlock.blockId];
                if (!blockDef || !blockDef.paramSchema) return <div className="text-sm text-white/20 text-center italic">설정 가능한 파라미터가 없습니다</div>;

                return Object.entries(blockDef.paramSchema).map(([key, param]) => {
                  const value = selectedBlock.params[key] ?? blockDef.defaultParams[key];
                  return (
                    <div key={key} className="space-y-2.5 group">
                      <div className="flex items-center justify-between px-1">
                        <div className="flex items-center gap-1.5">
                          <label className="text-sm font-black text-white/50 uppercase tracking-[0.15em]">{param.label}</label>
                          {param.tooltip && (
                            <div className="relative">
                              <Question
                                size={13}
                                className="text-white/30 hover:text-blue-400 cursor-help transition-colors"
                                onMouseEnter={(e) => setHoveredParam({ label: param.label, tooltip: param.tooltip!, rect: e.currentTarget.getBoundingClientRect() })}
                                onMouseLeave={() => setHoveredParam(null)}
                              />
                            </div>
                          )}
                        </div>
                        {param.type !== "select" && (
                          <span className="text-sm font-black text-[rgb(59,134,247)] tabular-nums">{value}{param.suffix}</span>
                        )}
                      </div>

                      {param.type === "select" && param.options ? (
                        <select
                          value={value}
                          onChange={(e) => {
                            const newVal = e.target.value;
                            const newParams = { ...selectedBlock.params, [key]: newVal };
                            // If signalType changes, also update the block's type
                            const newType = key === "signalType"
                              ? (newVal === "buy" ? "entry" : newVal === "sell" ? "exit" : selectedBlock.type)
                              : selectedBlock.type;
                            setCanvasBlocks(canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: newParams, type: newType } : b));
                            setSelectedBlock({ ...selectedBlock, params: newParams, type: newType });
                          }}
                          className="w-full px-3 py-3 bg-black/40 border border-white/5 rounded-xl text-sm font-black text-white outline-none appearance-none cursor-pointer hover:border-white/10 transition-all"
                          style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='rgba(255,255,255,0.3)' stroke-width='3'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 12px center' }}
                        >
                          {param.options.map((opt: any) => (
                            <option key={opt.value} value={opt.value} style={{ background: '#0d0d0d', color: 'white' }}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      ) : (
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
                      )}
                    </div>
                  );
                });
              })()}
            </div>

            <div className="p-5 bg-white/[0.01] border-t border-white/5 space-y-3">
              <button 
                onClick={() => setSelectedBlock(null)}
                className="w-full py-3 rounded-xl bg-[rgb(59,134,247)] text-white text-xs font-black uppercase tracking-widest hover:bg-[#4B9FFF] transition-all shadow-xl shadow-blue-500/10 active:scale-[0.98]"
              >
                확인
              </button>
              <button 
                onClick={() => {
                  const blockDef = signalBlocks[selectedBlock.blockId];
                  if (!blockDef) return;
                  const resetParams = { ...blockDef.defaultParams };
                  const updated = canvasBlocks.map(b => b.id === selectedBlock.id ? { ...b, params: resetParams, logic: undefined } : b);
                  setCanvasBlocks(updated);
                  setSelectedBlock({ ...selectedBlock, params: resetParams, logic: undefined });
                }}
                className="w-full py-3 rounded-xl text-white/20 text-xs font-black uppercase tracking-widest hover:text-orange-400 hover:bg-orange-500/5 transition-all"
              >
                초기화
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Floating: Nav Buttons */}
      <div className="absolute bottom-6 right-6 flex gap-3 z-40">
        <button 
          onClick={onPrev} 
          className="px-5 py-3 bg-black/60 hover:bg-black/80 text-white rounded-xl text-base font-black transition-all border border-white/10 active:scale-95 shadow-lg backdrop-blur-sm"
        >
          <ArrowLeft size={20} />
        </button>
        <button 
          onClick={onNext} 
          className="group px-6 py-3 bg-blue-500 hover:bg-blue-400 text-white rounded-xl text-sm font-black uppercase tracking-widest transition-all flex items-center gap-3 shadow-[0_10px_30px_rgba(59,130,246,0.3)] active:scale-[0.98]"
        >
          <span>포지션 설계</span>
          <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
        </button>
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
            <p className="text-sm text-white/75 font-bold leading-relaxed whitespace-pre-line">{hoveredParam.tooltip}</p>
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
