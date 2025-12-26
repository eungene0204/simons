"use client";

import { useState, useEffect } from "react";
import {
  XMarkIcon,
  SparklesIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ArrowRightIcon,
  PlayCircleIcon,
  AdjustmentsHorizontalIcon,
} from "@heroicons/react/24/outline";
import { StrategyDSL } from "@/types/strategy";
import {
  fuseStrategies,
  FusionMode,
  StrategyWeight,
  ConflictResolution,
  FusionConfig,
  FusionResult,
} from "@/lib/strategy-fusion";

interface StrategyFusionModalProps {
  isOpen: boolean;
  onClose: () => void;
  savedStrategies: StrategyDSL[];
  onSave: (strategy: StrategyDSL) => void;
  initialSelectedIds?: string[];
}

export default function StrategyFusionModal({
  isOpen,
  onClose,
  savedStrategies,
  onSave,
  initialSelectedIds = [],
}: StrategyFusionModalProps) {
  const [selectedStrategyIds, setSelectedStrategyIds] = useState<Set<string>>(
    new Set(initialSelectedIds)
  );
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [fusionMode, setFusionMode] = useState<FusionMode>("logic_merge");
  const [strategyWeights, setStrategyWeights] = useState<StrategyWeight[]>([]);
  const [conflictResolution, setConflictResolution] = useState<ConflictResolution>("neutral");
  const [priorityStrategyId, setPriorityStrategyId] = useState<string>("");
  const [fusionResult, setFusionResult] = useState<FusionResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Initialize weights when strategies are selected
  useEffect(() => {
    if (selectedStrategyIds.size > 0) {
      const equalWeight = Math.floor(100 / selectedStrategyIds.size);
      const weights: StrategyWeight[] = Array.from(selectedStrategyIds).map((id) => ({
        strategyId: id,
        weight: equalWeight,
        role: "signal" as const,
      }));
      setStrategyWeights(weights);
    }
  }, [selectedStrategyIds]);

  // Initialize with pre-selected strategies
  useEffect(() => {
    if (isOpen && initialSelectedIds.length > 0) {
      setSelectedStrategyIds(new Set(initialSelectedIds));
      setStep(2); // Skip to step 2 if strategies are pre-selected
    } else if (isOpen && initialSelectedIds.length === 0) {
      setSelectedStrategyIds(new Set());
      setStep(1);
    }
  }, [isOpen, initialSelectedIds]);

  const handleToggleStrategy = (strategyId: string) => {
    const newSet = new Set(selectedStrategyIds);
    if (newSet.has(strategyId)) {
      newSet.delete(strategyId);
    } else {
      newSet.add(strategyId);
    }
    setSelectedStrategyIds(newSet);
  };

  const handleWeightChange = (strategyId: string, weight: number) => {
    setStrategyWeights((prev) =>
      prev.map((w) => (w.strategyId === strategyId ? { ...w, weight } : w))
    );
  };

  const handleRoleChange = (strategyId: string, role: "signal" | "filter" | "distribution") => {
    setStrategyWeights((prev) =>
      prev.map((w) => (w.strategyId === strategyId ? { ...w, role } : w))
    );
    if (role === "filter") {
      setPriorityStrategyId(strategyId);
    } else if (priorityStrategyId === strategyId) {
      setPriorityStrategyId("");
    }
  };

  const handleGenerate = () => {
    if (selectedStrategyIds.size < 2) {
      alert("최소 2개 이상의 전략을 선택해주세요.");
      return;
    }

    const selectedStrategies = savedStrategies.filter((s) =>
      selectedStrategyIds.has(s.id)
    );

    const config: FusionConfig = {
      mode: fusionMode,
      weights: strategyWeights,
      conflictResolution,
      priorityStrategyId: priorityStrategyId || undefined,
    };

    try {
      const result = fuseStrategies(selectedStrategies, config);
      setFusionResult(result);
      setStep(4);
    } catch (error: any) {
      alert(error.message || "전략 조합 중 오류가 발생했습니다.");
    }
  };

  const handlePreview = async () => {
    setPreviewLoading(true);
    // Simulate preview (3-month simulation)
    await new Promise((resolve) => setTimeout(resolve, 2000));
    setPreviewLoading(false);
  };

  const handleSaveCombined = () => {
    if (fusionResult) {
      onSave(fusionResult.combinedStrategy);
      onClose();
      // Reset state
      setSelectedStrategyIds(new Set());
      setStep(1);
      setFusionResult(null);
    }
  };

  if (!isOpen) return null;

  const selectedStrategies = savedStrategies.filter((s) =>
    selectedStrategyIds.has(s.id)
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <div>
            <h2 className="text-xl font-semibold text-white mb-1">전략 조합하기</h2>
            <p className="text-sm text-gray-400">
              여러 전략을 선택하여 새로운 조합 전략을 만들어보세요
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <XMarkIcon className="w-6 h-6" />
          </button>
        </div>

        {/* Progress Steps */}
        <div className="px-6 py-4 border-b border-gray-800 bg-[#0f0f0f]">
          <div className="flex items-center justify-between">
            {[
              { num: 1, label: "전략 선택" },
              { num: 2, label: "조합 모드" },
              { num: 3, label: "가중치 설정" },
              { num: 4, label: "결과 확인" },
            ].map((s) => (
              <div key={s.num} className="flex items-center flex-1">
                <div className="flex items-center">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ${
                      step === s.num
                        ? "bg-blue-600 text-white"
                        : step > s.num
                        ? "bg-blue-600 text-white"
                        : "bg-gray-700 text-gray-400"
                    }`}
                  >
                    {step > s.num ? "✓" : s.num}
                  </div>
                  <span
                    className={`ml-2 text-sm ${
                      step >= s.num ? "text-white" : "text-gray-500"
                    }`}
                  >
                    {s.label}
                  </span>
                </div>
                {s.num < 4 && (
                  <div
                    className={`flex-1 h-0.5 mx-4 ${
                      step > s.num ? "bg-blue-600" : "bg-gray-700"
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Step 1: Strategy Selection */}
          {step === 1 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white">전략 선택</h3>
                <span className="text-sm text-gray-400">
                  {selectedStrategyIds.size}개 선택됨
                </span>
              </div>
              {savedStrategies.length === 0 ? (
                <div className="text-center py-12 text-gray-400">
                  저장된 전략이 없습니다. 먼저 전략을 만들어주세요.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {savedStrategies.map((strategy) => {
                    const isSelected = selectedStrategyIds.has(strategy.id);
                    return (
                      <div
                        key={strategy.id}
                        onClick={() => handleToggleStrategy(strategy.id)}
                        className={`p-4 rounded-lg border cursor-pointer transition-all ${
                          isSelected
                            ? "border-blue-500 bg-blue-500/10"
                            : "border-gray-800 bg-[#0f0f0f] hover:border-gray-700"
                        }`}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <h4 className="text-base font-semibold text-white">
                                {strategy.name}
                              </h4>
                              {isSelected && (
                                <CheckCircleIcon className="w-5 h-5 text-blue-400" />
                              )}
                            </div>
                            <p className="text-sm text-gray-400 mb-3 line-clamp-2">
                              {strategy.description}
                            </p>
                            <div className="flex items-center gap-4 text-xs text-gray-500">
                              <span>
                                진입: {strategy.entry?.conditions?.length || 0}개
                              </span>
                              <span>
                                청산: {strategy.exit?.conditions?.length || 0}개
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Step 2: Fusion Mode Selection */}
          {step === 2 && (
            <div className="space-y-6">
              <h3 className="text-lg font-semibold text-white mb-4">조합 모드 선택</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div
                  onClick={() => setFusionMode("logic_merge")}
                  className={`p-6 rounded-lg border cursor-pointer transition-all ${
                    fusionMode === "logic_merge"
                      ? "border-blue-500 bg-blue-500/10"
                      : "border-gray-800 bg-[#0f0f0f] hover:border-gray-700"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <SparklesIcon className="w-6 h-6 text-blue-400" />
                    <h4 className="text-base font-semibold text-white">룰 병합</h4>
                  </div>
                  <p className="text-sm text-gray-400 mb-4">
                    모든 전략의 룰을 하나의 전략으로 합칩니다. 중복 조건은 제거됩니다.
                  </p>
                  {fusionMode === "logic_merge" && (
                    <CheckCircleIcon className="w-5 h-5 text-blue-400" />
                  )}
                </div>

                <div
                  onClick={() => setFusionMode("signal_voting")}
                  className={`p-6 rounded-lg border cursor-pointer transition-all ${
                    fusionMode === "signal_voting"
                      ? "border-blue-500 bg-blue-500/10"
                      : "border-gray-800 bg-[#0f0f0f] hover:border-gray-700"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <AdjustmentsHorizontalIcon className="w-6 h-6 text-purple-400" />
                    <h4 className="text-base font-semibold text-white">시그널 투표</h4>
                  </div>
                  <p className="text-sm text-gray-400 mb-4">
                    각 전략의 시그널을 가중치에 따라 투표로 결합합니다.
                  </p>
                  {fusionMode === "signal_voting" && (
                    <CheckCircleIcon className="w-5 h-5 text-blue-400" />
                  )}
                </div>

                <div
                  onClick={() => setFusionMode("portfolio_blending")}
                  className={`p-6 rounded-lg border cursor-pointer transition-all ${
                    fusionMode === "portfolio_blending"
                      ? "border-blue-500 bg-blue-500/10"
                      : "border-gray-800 bg-[#0f0f0f] hover:border-gray-700"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <PlayCircleIcon className="w-6 h-6 text-green-400" />
                    <h4 className="text-base font-semibold text-white">포트폴리오 혼합</h4>
                  </div>
                  <p className="text-sm text-gray-400 mb-4">
                    각 전략의 결과물을 비중으로 조합하여 포트폴리오를 구성합니다.
                  </p>
                  {fusionMode === "portfolio_blending" && (
                    <CheckCircleIcon className="w-5 h-5 text-blue-400" />
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Weight Settings */}
          {step === 3 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-2">전략 가중치 설정</h3>
                <p className="text-sm text-gray-400">
                  각 전략의 가중치와 역할을 설정하세요
                </p>
              </div>

              <div className="space-y-4">
                {selectedStrategies.map((strategy) => {
                  const weightConfig = strategyWeights.find(
                    (w) => w.strategyId === strategy.id
                  );
                  const weight = weightConfig?.weight || 50;
                  const role = weightConfig?.role || "signal";

                  return (
                    <div
                      key={strategy.id}
                      className="p-4 rounded-lg border border-gray-800 bg-[#0f0f0f]"
                    >
                      <div className="flex items-center justify-between mb-4">
                        <div>
                          <h4 className="text-base font-semibold text-white">
                            {strategy.name}
                          </h4>
                          <p className="text-sm text-gray-400">{strategy.description}</p>
                        </div>
                        <span className="text-sm font-semibold text-blue-400">
                          {weight}%
                        </span>
                      </div>

                      <div className="space-y-4">
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <label className="text-sm text-gray-300">가중치</label>
                            <span className="text-xs text-gray-500">{weight}%</span>
                          </div>
                          <input
                            type="range"
                            min="0"
                            max="100"
                            value={weight}
                            onChange={(e) =>
                              handleWeightChange(strategy.id, parseInt(e.target.value))
                            }
                            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-600"
                          />
                        </div>

                        <div>
                          <label className="text-sm text-gray-300 mb-2 block">역할</label>
                          <div className="flex gap-2">
                            {(["signal", "filter", "distribution"] as const).map((r) => (
                              <button
                                key={r}
                                onClick={() => handleRoleChange(strategy.id, r)}
                                className={`px-3 py-1.5 rounded text-xs font-medium transition ${
                                  role === r
                                    ? "bg-blue-600 text-white"
                                    : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                                }`}
                              >
                                {r === "signal"
                                  ? "시그널"
                                  : r === "filter"
                                  ? "필터"
                                  : "분배"}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="p-4 rounded-lg border border-gray-800 bg-[#0f0f0f]">
                <label className="text-sm text-gray-300 mb-2 block">
                  충돌 해결 방식
                </label>
                <div className="flex gap-2">
                  {(
                    [
                      "conservative",
                      "neutral",
                      "aggressive",
                    ] as ConflictResolution[]
                  ).map((res) => (
                    <button
                      key={res}
                      onClick={() => setConflictResolution(res)}
                      className={`px-4 py-2 rounded text-sm font-medium transition ${
                        conflictResolution === res
                          ? "bg-blue-600 text-white"
                          : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                      }`}
                    >
                      {res === "conservative"
                        ? "보수적"
                        : res === "aggressive"
                        ? "공격적"
                        : "중립"}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Result Preview */}
          {step === 4 && fusionResult && (
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-white mb-2">조합된 전략</h3>
                <p className="text-sm text-gray-400">{fusionResult.aiComment}</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-lg border border-gray-800 bg-[#0f0f0f]">
                  <h4 className="text-sm font-semibold text-white mb-3">전략 로직</h4>
                  <div className="space-y-2 text-sm">
                    <div>
                      <span className="text-gray-400">진입 조건:</span>
                      <span className="text-white ml-2">
                        {fusionResult.combinedStrategy.entry.conditions.length}개
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">청산 조건:</span>
                      <span className="text-white ml-2">
                        {fusionResult.combinedStrategy.exit.conditions.length}개
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">진입 로직:</span>
                      <span className="text-white ml-2">
                        {fusionResult.combinedStrategy.entry.logic}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="p-4 rounded-lg border border-gray-800 bg-[#0f0f0f]">
                  <h4 className="text-sm font-semibold text-white mb-3">전략별 기여도</h4>
                  <div className="space-y-2">
                    {Object.entries(fusionResult.contributions).map(([id, contribution]) => {
                      const strategy = savedStrategies.find((s) => s.id === id);
                      return (
                        <div key={id} className="flex items-center justify-between">
                          <span className="text-sm text-gray-400">
                            {strategy?.name || id}
                          </span>
                          <span className="text-sm font-semibold text-blue-400">
                            {contribution.toFixed(1)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {fusionResult.conflicts.length > 0 && (
                <div className="p-4 rounded-lg border border-amber-800 bg-amber-900/10">
                  <div className="flex items-center gap-2 mb-2">
                    <ExclamationTriangleIcon className="w-5 h-5 text-amber-400" />
                    <h4 className="text-sm font-semibold text-amber-400">충돌 감지</h4>
                  </div>
                  <ul className="text-sm text-amber-300 space-y-1">
                    {fusionResult.conflicts.map((conflict, idx) => (
                      <li key={idx}>• {conflict}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="p-4 rounded-lg border border-gray-800 bg-[#0f0f0f]">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-sm font-semibold text-white">빠른 미리보기</h4>
                  <button
                    onClick={handlePreview}
                    disabled={previewLoading}
                    className="px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-500 disabled:opacity-50 flex items-center gap-2"
                  >
                    <PlayCircleIcon className="w-4 h-4" />
                    {previewLoading ? "실행 중..." : "최근 3개월 시뮬레이션"}
                  </button>
                </div>
                <div className="bg-gradient-to-br from-blue-900/20 via-indigo-900/10 to-transparent border border-gray-800 rounded-lg p-6 h-48 flex items-center justify-center text-gray-500 text-sm">
                  {previewLoading
                    ? "시뮬레이션 실행 중..."
                    : "미리보기를 실행하면 결과가 여기에 표시됩니다."}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-800">
          <button
            onClick={() => {
              if (step > 1) {
                setStep((step - 1) as 1 | 2 | 3 | 4);
              } else {
                onClose();
              }
            }}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-600"
          >
            {step === 1 ? "취소" : "이전"}
          </button>

          <div className="flex items-center gap-2">
            {step < 4 && (
              <button
                onClick={() => {
                  if (step === 1 && selectedStrategyIds.size >= 2) {
                    setStep(2);
                  } else if (step === 2) {
                    setStep(3);
                  } else if (step === 3) {
                    handleGenerate();
                  }
                }}
                disabled={
                  (step === 1 && selectedStrategyIds.size < 2) ||
                  (step === 2 && !fusionMode) ||
                  (step === 3 && strategyWeights.length === 0)
                }
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                다음
                <ArrowRightIcon className="w-4 h-4" />
              </button>
            )}
            {step === 4 && (
              <button
                onClick={handleSaveCombined}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-500 flex items-center gap-2"
              >
                <CheckCircleIcon className="w-5 h-5" />
                조합 전략 저장
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

