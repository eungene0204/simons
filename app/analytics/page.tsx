"use client";

import { useState, useEffect, useMemo, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
  ChartBarIcon,
  PlusIcon,
  TrashIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
  ChevronDownIcon,
  InformationCircleIcon,
  BoltIcon,
  ArrowTrendingUpIcon,
  ArrowPathIcon,
  CpuChipIcon,
  SparklesIcon,
  MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";
import StrategyComposer from "@/components/strategy/StrategyComposer";
import StrategyComposerV2 from "@/components/strategy/StrategyComposerV2";
import StrategyFusionModal from "@/components/strategy/StrategyFusionModal";
import { StrategyDSL } from "@/types/strategy";


const formatPrice = (price: number) => {
  return new Intl.NumberFormat("ko-KR").format(price);
};

function AnalyticsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const symbol = searchParams.get("symbol") || "";
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(1);
  const [strategy, setStrategy] = useState<StrategyDSL | null>(null);
  const [savedStrategies, setSavedStrategies] = useState<StrategyDSL[]>([]);
  const [showComposer, setShowComposer] = useState(false);
  const [showFusionModal, setShowFusionModal] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedForFusion, setSelectedForFusion] = useState<Set<string>>(new Set());
  const [useV2Composer, setUseV2Composer] = useState(true); // Toggle for new UI
  const [composerKey, setComposerKey] = useState(0); // For forcing re-mount

  // Load saved strategies from the database
  useEffect(() => {
    const fetchStrategies = async () => {
      try {
        const response = await fetch('/api/strategy');
        if (response.ok) {
          const data = await response.json();
          setSavedStrategies(data);
        }
      } catch (e) {
        console.error("Failed to load saved strategies from API", e);
      }
    };
    fetchStrategies();
  }, []);

  // Save strategy
  const handleSaveStrategy = async (strategyData: StrategyDSL) => {
    try {
      const response = await fetch('/api/strategy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(strategyData)
      });
      if (response.ok) {
         const newStrategy = await response.json();
         // The settings contains the StrategyDSL, so we need to parse it for the list view
         const parsedStrategy = typeof newStrategy.settings === 'string' ? JSON.parse(newStrategy.settings) : newStrategy;
         setSavedStrategies(prev => [parsedStrategy, ...prev]);
         setStrategy(parsedStrategy);
         setShowComposer(false);
         setCurrentStep(1);
      }
    } catch (error) {
       console.error("Failed to save strategy", error);
    }
  };

  // Load strategy
  const handleLoadStrategy = (strategyId: string) => {
    const loaded = savedStrategies.find((s) => s.id === strategyId);
    if (loaded) {
      setStrategy(loaded);
      setShowComposer(true);
    }
  };

  // Delete strategy
  const handleDeleteStrategy = async (strategyId: string) => {
    try {
       const response = await fetch(`/api/strategy?id=${strategyId}`, {
         method: 'DELETE'
       });
       if (response.ok) {
         setSavedStrategies(prev => prev.filter((s) => s.id !== strategyId));
       }
    } catch (error) {
       console.error("Failed to delete strategy", error);
    }
  };

  const openComposer = () => {
    console.log("openComposer called");

    setShowComposer(true);
    setCurrentStep(1);
    setStrategy(null);
    setComposerKey(prev => prev + 1);

    setSelectionMode(false); // Reset selection mode
    // Ensure V2 is used
    setUseV2Composer(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };


  return (
    <DashboardLayout userName={"User"}>
      <div className="px-8 py-8 space-y-8 max-w-full mx-auto overflow-x-hidden w-full min-w-0">
        {/* Header */}
        <div className="flex-none flex items-center justify-between px-8">
          <div>
            <h1 className="text-2xl font-bold text-white mb-2">전략연구소</h1>
            <p className="text-sm text-gray-400">
              나만의 매매전략을 만들어보세요
            </p>
          </div>
            <div className="flex items-center gap-3">
              {savedStrategies.length >= 2 && (
                <>
                  {!selectionMode ? (
                    <button
                      onClick={() => {
                        setSelectionMode(true);
                        setSelectedForFusion(new Set());
                      }}
                      className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-600 flex items-center gap-2"
                    >
                      <SparklesIcon className="w-5 h-5" />
                      전략 선택하기
                    </button>
                  ) : (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          setSelectionMode(false);
                          setSelectedForFusion(new Set());
                        }}
                        className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-600"
                      >
                        취소
                      </button>
                      <button
                        onClick={() => {
                          if (selectedForFusion.size >= 2) {
                            setShowFusionModal(true);
                          } else {
                            alert("최소 2개 이상의 전략을 선택해주세요.");
                          }
                        }}
                        disabled={selectedForFusion.size < 2}
                        className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        <SparklesIcon className="w-5 h-5" />
                        전략 조합하기 ({selectedForFusion.size}개 선택됨)
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
        </div>

        {/* Strategy Composer or Backtest Panel */}
        {showComposer && (
          <>
            {useV2Composer ? (
              <StrategyComposerV2
                key={strategy ? `edit-${strategy.id}` : `new-${composerKey}`} // Force re-mount on strategy change or new strategy
                onSave={handleSaveStrategy}
                onCancel={() => {
                  setShowComposer(false);
                  setCurrentStep(1);
                  setStrategy(null);
                }}
                onQuickPreview={() => {
                  // Quick preview logic
                  console.log("Quick preview");
                }}

                initialStrategy={strategy}
              />
            ) : (
              <StrategyComposer
                currentStep={currentStep}
                onStepChange={setCurrentStep}
                onSave={handleSaveStrategy}
                onCancel={() => {
                  setShowComposer(false);
                  setCurrentStep(1);
                  setStrategy(null);
                }}
                initialStrategy={strategy}
              />
            )}
          </>
        )}
        {!showComposer && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 px-8">
              {savedStrategies.length === 0 ? (
                <div className="col-span-full">
                  <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-12 text-center">
                    <ChartBarIcon className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                    <h3 className="text-lg font-semibold text-white mb-2">
                      저장된 전략이 없습니다
                    </h3>
                    <p className="text-sm text-gray-400 mb-4">
                      새 전략을 만들어보세요
                    </p>
                    <button
                      onClick={openComposer}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-600 flex items-center gap-2 mx-auto"
                    >
                      <PlusIcon className="w-5 h-5" />새 전략 만들기
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div
                    className="bg-[#1a1a1a] rounded-lg border border-dashed border-gray-700 p-6 hover:border-blue-500 transition-all cursor-pointer flex flex-col justify-center items-center text-center"
                    onClick={openComposer}
                  >
                    <div className="w-12 h-12 rounded-full bg-blue-600/20 border border-blue-600/40 flex items-center justify-center mb-3">
                      <PlusIcon className="w-6 h-6 text-blue-400" />
                    </div>
                    <h3 className="text-base font-semibold text-white mb-1">
                      새 전략 만들기
                    </h3>
                    <p className="text-sm text-gray-400">
                      템플릿을 선택하거나 직접 조립해보세요.
                    </p>
                  </div>
                  {savedStrategies.map((s) => {
                    const isSelected = selectedForFusion.has(s.id);
                    return (
                      <div
                        key={s.id}
                        className={`bg-[#1a1a1a] rounded-lg border p-6 transition-all group ${
                          selectionMode
                            ? isSelected
                              ? "border-purple-500 bg-purple-500/10 cursor-pointer"
                              : "border-gray-800 hover:border-gray-700 cursor-pointer"
                            : "border-gray-800 hover:border-gray-700 cursor-pointer"
                        }`}
                        onClick={() => {
                          if (selectionMode) {
                            const newSet = new Set(selectedForFusion);
                            if (newSet.has(s.id)) {
                              newSet.delete(s.id);
                            } else {
                              newSet.add(s.id);
                            }
                            setSelectedForFusion(newSet);
                          } else {
                            handleLoadStrategy(s.id);
                          }
                        }}
                      >
                        <div className="flex items-start justify-between mb-3">
                          <div className="flex items-center gap-3 flex-1">
                            {selectionMode && (
                              <div
                                className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                                  isSelected
                                    ? "bg-purple-600 border-purple-600"
                                    : "border-gray-600"
                                }`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const newSet = new Set(selectedForFusion);
                                  if (newSet.has(s.id)) {
                                    newSet.delete(s.id);
                                  } else {
                                    newSet.add(s.id);
                                  }
                                  setSelectedForFusion(newSet);
                                }}
                              >
                                {isSelected && (
                                  <CheckCircleIcon className="w-4 h-4 text-white" />
                                )}
                              </div>
                            )}
                            <h3 className="text-base font-semibold text-white group-hover:text-blue-400 transition-colors">
                              {s.name || "이름 없는 전략"}
                            </h3>
                          </div>
                          {!selectionMode && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteStrategy(s.id);
                              }}
                              className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-600/20 rounded"
                            >
                              <TrashIcon className="w-4 h-4 text-red-400" />
                            </button>
                          )}
                        </div>
                        <p className="text-sm text-gray-400 mb-4 line-clamp-2">
                          {s.description || "설명이 없습니다"}
                        </p>
                        <div className="flex items-center justify-between text-xs text-gray-500">
                          <span>
                            {s.entry?.conditions?.length || 0}개 진입 조건
                          </span>
                          <span>
                            {new Date(
                              s.created_at || Date.now()
                            ).toLocaleDateString("ko-KR")}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
        )}
      </div>

      {/* Strategy Fusion Modal */}
      <StrategyFusionModal
        isOpen={showFusionModal}
        onClose={() => {
          setShowFusionModal(false);
          setSelectionMode(false);
          setSelectedForFusion(new Set());
        }}
        savedStrategies={savedStrategies}
        onSave={(strategy) => {
          handleSaveStrategy(strategy);
          setSelectionMode(false);
          setSelectedForFusion(new Set());
        }}
        initialSelectedIds={Array.from(selectedForFusion)}
      />
    </DashboardLayout>
  );
}

export default function AnalyticsPage() {
  return (
    <Suspense fallback={
      <DashboardLayout userName={"User"}>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
        </div>
      </DashboardLayout>
    }>
      <AnalyticsContent />
    </Suspense>
  );
}
