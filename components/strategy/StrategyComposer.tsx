"use client";

import { useState, useEffect } from "react";
import {
  ArrowRightIcon,
  ArrowLeftIcon,
  XMarkIcon,
  PlusIcon,
  TrashIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  PlayCircleIcon,
  SparklesIcon,
  AdjustmentsHorizontalIcon,
  ShieldExclamationIcon,
  ArrowPathIcon,
} from "@heroicons/react/24/outline";
import { StrategyDSL, SignalBlock, Condition } from "@/types/strategy";
import { signalBlocks } from "@/lib/strategy-blocks";
import { strategyGroups, StrategyDefinition } from "@/lib/strategy-groups";
import ConditionBlockEditor from "./ConditionBlockEditor";
import RiskManagementEditor from "./RiskManagementEditor";

interface StrategyComposerProps {
  currentStep: number;
  onStepChange: (step: 1 | 2 | 3) => void;
  onSave: (strategy: StrategyDSL) => void;
  onCancel: () => void;
  initialStrategy?: StrategyDSL | null;
}

type LibraryBlock = {
  id: string;
  name: string;
  description: string;
  category: "indicator" | "flow" | "risk" | "ml" | "position" | "portfolio";
  defaultParams: Record<string, any>;
  paramSchema: SignalBlock["paramSchema"];
};

export default function StrategyComposer({
  currentStep,
  onStepChange,
  onSave,
  onCancel,
  initialStrategy,
}: StrategyComposerProps) {
  // Step 1: Basic Info
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState<string | null>(null);
  const [templateParams, setTemplateParams] = useState<Record<string, number | string>>({});

  // Flattened strategy templates from backtest strategy groups
  const templateStrategies: StrategyDefinition[] = strategyGroups.flatMap((group) =>
    group.strategies.map((s) => s)
  );

  const positionBlocks: LibraryBlock[] = [
    {
      id: "equal_weight",
      name: "동일 비중",
      description: "포지션 비중을 동일하게 배분",
      category: "position",
      defaultParams: {},
      paramSchema: {},
    },
    {
      id: "vol_target",
      name: "변동성 타겟팅",
      description: "목표 변동성에 맞춰 포지션 크기를 조절",
      category: "position",
      defaultParams: {},
      paramSchema: {},
    },
    {
      id: "leverage_toggle",
      name: "레버리지",
      description: "전략 레버리지 설정",
      category: "position",
      defaultParams: {},
      paramSchema: {},
    },
  ];

  const portfolioBlocks: LibraryBlock[] = [
    {
      id: "rebalance_monthly",
      name: "월간 리밸런싱",
      description: "매월 말 리밸런싱",
      category: "portfolio",
      defaultParams: {},
      paramSchema: {},
    },
    {
      id: "max_holdings",
      name: "보유 종목 수 제한",
      description: "포트폴리오의 최대 종목 수 설정",
      category: "portfolio",
      defaultParams: {},
      paramSchema: {},
    },
    {
      id: "universe_filter",
      name: "유니버스 필터",
      description: "섹터/팩터 기반 유니버스 필터링",
      category: "portfolio",
      defaultParams: {},
      paramSchema: {},
    },
  ];

  const libraryBlocks: any[] = [
    ...Object.values(signalBlocks),
    ...positionBlocks,
    ...portfolioBlocks,
  ];

  // Step 2: Conditions
  const [entryConditions, setEntryConditions] = useState<Condition[]>([]);
  const [entryLogic, setEntryLogic] = useState<"AND" | "OR" | "WEIGHTED_SUM">("AND");
  const [exitConditions, setExitConditions] = useState<Condition[]>([]);
  const [exitLogic, setExitLogic] = useState<"AND" | "OR">("OR");
  const [selectedBlock, setSelectedBlock] = useState<LibraryBlock | null>(null);
  const [editingCondition, setEditingCondition] = useState<Condition | null>(null);
  const [placement, setPlacement] = useState<"entry" | "exit">("entry");
  const [blockFilter, setBlockFilter] = useState<
    "all" | "indicator" | "flow" | "risk" | "ml" | "position" | "portfolio"
  >("all");
  const [positionRules, setPositionRules] = useState<
    Array<{ id: string; name: string; description: string }>
  >([]);
  const [portfolioRules, setPortfolioRules] = useState<
    Array<{ id: string; name: string; description: string }>
  >([]);
  const [previewStatus, setPreviewStatus] = useState<"idle" | "instant" | "fast" | "full">("idle");
  const [previewLog, setPreviewLog] = useState<string[]>([]);
  const [fusionPair, setFusionPair] = useState<{ a: string | null; b: string | null }>({
    a: null,
    b: null,
  });
  const [fusionLog, setFusionLog] = useState<string[]>([]);
  const [validatorMessages, setValidatorMessages] = useState<string[]>([
    "엔트리와 엑시트에 최소 1개 블록이 필요합니다.",
  ]);
  const selectedTemplateDef = template
    ? templateStrategies.find((s) => s.id === template) || null
    : null;

  // Step 3: Risk Management
  const [riskManagement, setRiskManagement] = useState({
    position_size_pct: 5,
    max_positions: 10,
    max_daily_loss_pct: 5,
    max_total_exposure_pct: 50,
  });

  // Initialize from template or existing strategy
  useEffect(() => {
    if (initialStrategy) {
      setName(initialStrategy.name);
      setDescription(initialStrategy.description);
      setEntryConditions(initialStrategy.entry.conditions);
      setEntryLogic(initialStrategy.entry.logic as any);
      setExitConditions(initialStrategy.exit.conditions);
      setExitLogic(initialStrategy.exit.logic as any);
      setRiskManagement(initialStrategy.risk as any);
    }
  }, [initialStrategy]);

  // When user selects a template from backtest strategy groups
  const handleSelectTemplate = (strategyDef: StrategyDefinition) => {
    setTemplate(strategyDef.id);
    const defaults = strategyDef.params.reduce<Record<string, number | string>>(
      (acc, p) => {
        acc[p.key] = p.default;
        return acc;
      },
      {}
    );
    setTemplateParams(defaults);
    // If user has not typed anything yet, prefill name/description from template
    if (!name.trim()) {
      setName(strategyDef.name);
    }
    if (!description.trim()) {
      setDescription(strategyDef.description);
    }
  };

  // Add condition or meta block into the canvas
  const handleAddBlock = (block: LibraryBlock, target?: "entry" | "exit") => {
    if (block.category === "position") {
      setPositionRules([...positionRules, { id: block.id, name: block.name, description: block.description }]);
      setSelectedBlock(null);
      return;
    }

    if (block.category === "portfolio") {
      setPortfolioRules([
        ...portfolioRules,
        { id: block.id, name: block.name, description: block.description },
      ]);
      setSelectedBlock(null);
      return;
    }

    const conditionType: Condition["type"] =
      block.category === "risk"
        ? "risk"
        : block.category === "flow"
        ? "flow"
        : block.category === "ml"
        ? "ml"
        : "indicator";

    const newCondition: Condition = {
      type: conditionType,
      id: block.id,
      params: { ...block.defaultParams },
      weight: block.category === "indicator" || block.category === "flow" ? 1 : undefined,
    };

    const destination: "entry" | "exit" =
      block.category === "risk" ? "exit" : target || placement;

    if (destination === "entry") {
      setEntryConditions([...entryConditions, newCondition]);
    } else {
      setExitConditions([...exitConditions, newCondition]);
    }

    setSelectedBlock(null);
    setEditingCondition(newCondition);
  };

  // Update condition
  const handleUpdateCondition = (updated: Condition) => {
    if (entryConditions.some((c) => c === editingCondition)) {
      setEntryConditions(
        entryConditions.map((c) => (c === editingCondition ? updated : c))
      );
    } else {
      setExitConditions(
        exitConditions.map((c) => (c === editingCondition ? updated : c))
      );
    }
    setEditingCondition(null);
  };

  // Remove condition
  const handleRemoveCondition = (condition: Condition) => {
    setEntryConditions(entryConditions.filter((c) => c !== condition));
    setExitConditions(exitConditions.filter((c) => c !== condition));
    if (editingCondition === condition) {
      setEditingCondition(null);
    }
  };

  const moveCondition = (target: "entry" | "exit", index: number, direction: -1 | 1) => {
    const list = target === "entry" ? [...entryConditions] : [...exitConditions];
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= list.length) return;
    const [removed] = list.splice(index, 1);
    list.splice(newIndex, 0, removed);
    if (target === "entry") {
      setEntryConditions(list);
    } else {
      setExitConditions(list);
    }
  };

  const handlePreviewRun = (mode: "instant" | "fast" | "full") => {
    setPreviewStatus(mode);
    const label =
      mode === "instant" ? "즉시 미리보기" : mode === "fast" ? "빠른 백테스트" : "전체 백테스트";
    setPreviewLog((prev) => [`[${label}] 실행`, ...prev].slice(0, 8));
    const timeout = mode === "instant" ? 600 : mode === "fast" ? 2000 : 4000;
    setTimeout(() => {
      setPreviewStatus("idle");
      setPreviewLog((prev) => [`[${label}] 완료`, ...prev].slice(0, 8));
    }, timeout);
  };

  // Save strategy
  const handleSave = () => {
    if (!name.trim()) {
      alert("전략 이름을 입력하세요");
      return;
    }

    const strategy: StrategyDSL = {
      id: initialStrategy?.id || `strategy_${Date.now()}`,
      name: name.trim(),
      description: description.trim(),
      version: "1.0.0",
      entry: {
        logic: entryLogic,
        conditions: entryConditions,
      },
      exit: {
        logic: exitLogic,
        conditions: exitConditions,
      },
      risk: riskManagement as any,
      universe: initialStrategy?.universe || {
        id: "all",
        filters: {}
      },
      created_at: initialStrategy?.created_at || new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    onSave(strategy);
  };

  // Validation
  const canProceedToStep2 = name.trim().length > 0;
  const canProceedToStep3 = entryConditions.length > 0 && exitConditions.length > 0;
  const canSave = canProceedToStep3;

  const filteredBlocks = libraryBlocks.filter((block) => {
    if (blockFilter === "all") return true;
    return block.category === blockFilter;
  });

  const validatorStatus =
    validatorMessages.length === 1 && validatorMessages[0] === "모든 검사 통과"
      ? "ok"
      : "warn";

  useEffect(() => {
    const nextMessages: string[] = [];
    if (entryConditions.length === 0) nextMessages.push("매수 조건을 하나 이상 추가하세요.");
    if (exitConditions.length === 0) nextMessages.push("매도/리스크 조건을 하나 이상 추가하세요.");
    if (positionRules.length === 0) nextMessages.push("포지션 규칙을 지정하면 실행이 명확해집니다.");
    if (portfolioRules.length === 0) nextMessages.push("포트폴리오 규칙을 지정하면 검증이 용이합니다.");
    setValidatorMessages(nextMessages.length ? nextMessages : ["모든 검사 통과"]);
  }, [entryConditions, exitConditions, positionRules, portfolioRules]);

  return (
    <div className="glass-card p-6 md:p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className="text-[10px] font-bold text-blue-400 uppercase tracking-widest bg-blue-400/10 px-2 py-0.5 rounded">
              Expert Mode
            </span>
            <h2 className="text-2xl font-bold text-white tracking-tight">전략 컴포저</h2>
          </div>
          <p className="text-sm text-gray-400 font-medium">
            {currentStep === 1 && "기본 정보를 입력하여 새로운 전략의 기반을 다집니다."}
            {currentStep === 2 && "매매 신호 블록을 조합하여 고유한 알고리즘을 구축하세요."}
            {currentStep === 3 && "자본 보호를 위한 리스크 관리 매개변수를 설정합니다."}
          </p>
        </div>
        <button
          onClick={onCancel}
          className="p-2 text-gray-400 hover:text-white hover:bg-white/5 rounded-full transition-colors"
        >
          <XMarkIcon className="w-6 h-6" />
        </button>
      </div>

      {/* Progress Steps */}
      <div className="flex items-center justify-between mb-12">
        {[1, 2, 3].map((step) => (
          <div key={step} className="flex items-center flex-1">
            <div className="flex flex-col items-center group cursor-pointer" onClick={() => (currentStep > step || step <= currentStep + 1) && onStepChange(step as any)}>
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold transition-all duration-300 ${
                  currentStep === step
                    ? "bg-blue-600 text-white shadow-[0_0_20px_rgba(59,130,246,0.4)] scale-110"
                    : currentStep > step
                    ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                    : "bg-white/5 text-gray-500 border border-white/5"
                }`}
              >
                {currentStep > step ? "✓" : step}
              </div>
              <div
                className={`mt-2 text-[11px] font-bold uppercase tracking-wider ${
                  currentStep >= step ? "text-blue-400" : "text-gray-600"
                }`}
              >
                {step === 1 && "Basic Info"}
                {step === 2 && "Blocks"}
                {step === 3 && "Risk Settings"}
              </div>
            </div>
            {step < 3 && (
              <div
                className={`flex-1 h-[2px] mx-6 -mt-6 transition-colors duration-500 ${
                  currentStep > step ? "bg-blue-600/50" : "bg-white/5"
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step 1: Basic Info */}
      {currentStep === 1 && (
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              전략 이름 *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 고수익 모멘텀 전략"
              className="w-full px-4 py-2 bg-[#0f0f0f] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              전략 설명
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="이 전략의 목적과 특징을 설명하세요"
              rows={4}
              className="w-full px-4 py-2 bg-[#0f0f0f] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              템플릿 선택 (선택사항)
            </label>
            <div className="space-y-4">
              <div className="text-xs text-gray-500">
                전략 그룹별 드롭다운에서 하나의 템플릿을 선택해 시작할 수 있습니다.
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {strategyGroups.map((group) => {
                  const selectedInGroup = group.strategies.some(
                    (s) => s.id === template
                  );
                  const selectedStrategy =
                    selectedInGroup && template
                      ? group.strategies.find((s) => s.id === template)
                      : undefined;

                  return (
                    <div
                      key={group.id}
                      className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-3 space-y-2"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{group.icon}</span>
                        <div>
                          <div className="text-sm font-semibold text-white">
                            {group.name}
                          </div>
                          <div className="text-xs text-gray-500 line-clamp-1">
                            {group.description}
                          </div>
                        </div>
                      </div>
                      <div className="relative">
                        <select
                          value={selectedInGroup && template ? template : ""}
                          onChange={(e) => {
                            const value = e.target.value;
                            if (!value) {
                              setTemplate(null);
                              return;
                            }
                            const selected = group.strategies.find(
                              (s) => s.id === value
                            );
                            if (selected) {
                              handleSelectTemplate(selected);
                            }
                          }}
                          className="w-full appearance-none pl-3 pr-12 py-2 bg-[#050505] border border-gray-700 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                        >
                          <option value="">
                            {group.name} 템플릿 선택 안 함
                          </option>
                          {group.strategies.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name}
                            </option>
                          ))}
                        </select>
                        <ChevronDownIcon className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                      </div>
                      {selectedStrategy && (
                        <div className="text-[11px] text-gray-400 line-clamp-2">
                          {selectedStrategy.description}
                        </div>
                      )}
                      {selectedTemplateDef && selectedTemplateDef.id === selectedStrategy?.id && (
                        <div className="mt-3 space-y-2 rounded-lg border border-gray-800 bg-[#0c0c0c] p-3">
                          <div className="text-xs font-semibold text-white mb-1">
                            템플릿 파라미터 조정
                          </div>
                          <div className="space-y-2">
                            {selectedTemplateDef.params.map((param) => (
                              <div key={param.key} className="space-y-1">
                                <div className="flex items-center justify-between text-[11px] text-gray-400">
                                  <span>{param.label}</span>
                                  <span className="font-mono text-gray-300">
                                    {templateParams[param.key] ?? param.default}
                                  </span>
                                </div>
                                {param.type === "select" && param.options ? (
                                  <select
                                    value={
                                      (templateParams[param.key] as string | number | undefined) ??
                                      param.default
                                    }
                                    onChange={(e) =>
                                      setTemplateParams({
                                        ...templateParams,
                                        [param.key]: e.target.value,
                                      })
                                    }
                                    className="w-full px-3 py-2 bg-[#050505] border border-gray-700 rounded text-xs text-white focus:outline-none focus:border-blue-500"
                                  >
                                    {param.options.map((opt) => (
                                      <option key={opt.value} value={opt.value}>
                                        {opt.label}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <input
                                    type="number"
                                    min={param.min}
                                    max={param.max}
                                    step={param.step || 1}
                                    value={
                                      (templateParams[param.key] as number | string | undefined) ??
                                      param.default
                                    }
                                    onChange={(e) =>
                                      setTemplateParams({
                                        ...templateParams,
                                        [param.key]: parseFloat(e.target.value),
                                      })
                                    }
                                    className="w-full px-3 py-2 bg-[#050505] border border-gray-700 rounded text-xs text-white focus:outline-none focus:border-blue-500"
                                  />
                                )}
                                {param.tooltip && (
                                  <div className="text-[10px] text-gray-500">{param.tooltip}</div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Step 2: Block-based Composer */}
      {currentStep === 2 && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr_340px] gap-4">
            {/* Left: Block Library */}
            <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">블록 라이브러리</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    템플릿·신호·리스크·포트폴리오 블록을 추가하세요.
                  </p>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-gray-400 bg-[#1a1a1a] px-2 py-1 rounded">
                  <AdjustmentsHorizontalIcon className="w-4 h-4" />
                  <span>{placement === "entry" ? "매수" : "매도"}</span>
                  <button
                    onClick={() => setPlacement(placement === "entry" ? "exit" : "entry")}
                    className="text-blue-400 hover:text-blue-300"
                  >
                    전환
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {[
                  { key: "all", label: "전체" },
                  { key: "indicator", label: "신호" },
                  { key: "flow", label: "수급" },
                  { key: "risk", label: "리스크" },
                  { key: "ml", label: "ML" },
                  { key: "position", label: "포지션" },
                  { key: "portfolio", label: "포트폴리오" },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() =>
                      setBlockFilter(
                        tab.key as
                          | "all"
                          | "indicator"
                          | "flow"
                          | "risk"
                          | "ml"
                          | "position"
                          | "portfolio"
                      )
                    }
                    className={`px-3 py-1 rounded-full text-xs border ${
                      blockFilter === tab.key
                        ? "bg-blue-600 border-blue-500 text-white"
                        : "bg-[#1a1a1a] border-gray-700 text-gray-300 hover:border-gray-500"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <div className="space-y-2 max-h-[620px] overflow-y-auto pr-1">
                {filteredBlocks.map((block) => (
                  <div
                    key={block.id}
                    className={`p-3 rounded-lg border ${
                      selectedBlock?.id === block.id
                        ? "border-blue-500 bg-[#1d2435]"
                        : "border-gray-800 bg-[#0f0f0f] hover:border-gray-700"
                    } transition`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-semibold text-white">{block.name}</div>
                        <div className="text-xs text-gray-400 mt-1">{block.description}</div>
                      </div>
                      <button
                        onClick={() => {
                          setSelectedBlock(block);
                          handleAddBlock(block, placement);
                        }}
                        className="shrink-0 px-2 py-1 text-[11px] bg-blue-600 text-white rounded hover:bg-blue-500"
                      >
                        추가
                      </button>
                    </div>
                    <div className="mt-2 flex items-center gap-2 text-[11px] text-gray-500">
                      <span className="px-2 py-0.5 rounded bg-[#1a1a1a] border border-gray-800">
                        {block.category}
                      </span>
                      {block.category === "risk" && (
                        <span className="text-yellow-400">exit로 자동 배치</span>
                      )}
                    </div>
                  </div>
                ))}
                {filteredBlocks.length === 0 && (
                  <div className="text-xs text-gray-500 py-6 text-center">해당 카테고리 블록이 없습니다.</div>
                )}
              </div>
            </div>

            {/* Center: Canvas */}
            <div className="space-y-4">
              <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-white">전략 캔버스</h3>
                    <span
                      className={`px-2 py-1 rounded-full text-[11px] ${
                        validatorStatus === "ok"
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-600/50"
                          : "bg-amber-500/10 text-amber-300 border border-amber-600/40"
                      }`}
                    >
                      Validator {validatorStatus === "ok" ? "OK" : "확인 필요"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-gray-400">
                    <SparklesIcon className="w-4 h-4 text-blue-400" />
                    <span>AND/OR 조합 · 순서 변경 · 가중치</span>
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
                  <div className="bg-[#0f0f0f] border border-gray-800 rounded-lg p-3 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold text-white">매수 (Entry)</div>
                      <select
                        value={entryLogic}
                        onChange={(e) =>
                          setEntryLogic(e.target.value as "AND" | "OR" | "WEIGHTED_SUM")
                        }
                        className="px-3 py-1 bg-[#1a1a1a] border border-gray-700 rounded text-xs text-white"
                      >
                        <option value="AND">AND</option>
                        <option value="OR">OR</option>
                        <option value="WEIGHTED_SUM">가중합</option>
                      </select>
                    </div>
                    <div className="space-y-2">
                      {entryConditions.length === 0 && (
                        <div className="text-xs text-gray-500 py-6 text-center">
                          블록을 추가하세요.
                        </div>
                      )}
                      {entryConditions.map((condition, index) => {
                        const block = signalBlocks[condition.id];
                        return (
                          <div
                            key={`${condition.id}-${index}`}
                            className="p-3 bg-[#161616] rounded-lg border border-gray-800"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="text-sm font-semibold text-white">
                                  {block?.name || condition.id}
                                </div>
                                <div className="text-[11px] text-gray-500 mt-1">
                                  {Object.entries(condition.params)
                                    .map(([k, v]) => `${k}: ${v}`)
                                    .join(", ")}
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() => moveCondition("entry", index, -1)}
                                  className="text-gray-500 hover:text-white text-xs"
                                >
                                  ↑
                                </button>
                                <button
                                  onClick={() => moveCondition("entry", index, 1)}
                                  className="text-gray-500 hover:text-white text-xs"
                                >
                                  ↓
                                </button>
                                <button
                                  onClick={() => setEditingCondition(condition)}
                                  className="px-2 py-1 text-[11px] bg-blue-600 text-white rounded hover:bg-blue-500"
                                >
                                  편집
                                </button>
                                <button
                                  onClick={() => handleRemoveCondition(condition)}
                                  className="text-red-400 hover:text-red-300"
                                >
                                  <TrashIcon className="w-4 h-4" />
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="bg-[#0f0f0f] border border-gray-800 rounded-lg p-3 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold text-white">매도·리스크 (Exit)</div>
                      <select
                        value={exitLogic}
                        onChange={(e) => setExitLogic(e.target.value as "AND" | "OR")}
                        className="px-3 py-1 bg-[#1a1a1a] border border-gray-700 rounded text-xs text-white"
                      >
                        <option value="OR">OR</option>
                        <option value="AND">AND</option>
                      </select>
                    </div>
                    <div className="space-y-2">
                      {exitConditions.length === 0 && (
                        <div className="text-xs text-gray-500 py-6 text-center">
                          리스크/익절/손절 블록을 추가하세요.
                        </div>
                      )}
                      {exitConditions.map((condition, index) => {
                        const block = signalBlocks[condition.id];
                        return (
                          <div
                            key={`${condition.id}-${index}`}
                            className="p-3 bg-[#161616] rounded-lg border border-gray-800"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="text-sm font-semibold text-white">
                                  {block?.name || condition.id}
                                </div>
                                <div className="text-[11px] text-gray-500 mt-1">
                                  {Object.entries(condition.params)
                                    .map(([k, v]) => `${k}: ${v}`)
                                    .join(", ")}
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() => moveCondition("exit", index, -1)}
                                  className="text-gray-500 hover:text-white text-xs"
                                >
                                  ↑
                                </button>
                                <button
                                  onClick={() => moveCondition("exit", index, 1)}
                                  className="text-gray-500 hover:text-white text-xs"
                                >
                                  ↓
                                </button>
                                <button
                                  onClick={() => setEditingCondition(condition)}
                                  className="px-2 py-1 text-[11px] bg-blue-600 text-white rounded hover:bg-blue-500"
                                >
                                  편집
                                </button>
                                <button
                                  onClick={() => handleRemoveCondition(condition)}
                                  className="text-red-400 hover:text-red-300"
                                >
                                  <TrashIcon className="w-4 h-4" />
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-3">
                  <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold text-white">포지션 블록</div>
                      <span className="text-[11px] text-gray-500">{positionRules.length}개</span>
                    </div>
                    {positionRules.length === 0 && (
                      <div className="text-xs text-gray-500 py-4 text-center">
                        포지션 비중/레버리지 규칙을 추가하세요.
                      </div>
                    )}
                    {positionRules.map((rule) => (
                      <div
                        key={rule.id}
                        className="flex items-center justify-between bg-[#161616] border border-gray-800 rounded-lg px-3 py-2 text-sm text-white"
                      >
                        <div>
                          <div className="font-semibold">{rule.name}</div>
                          <div className="text-[11px] text-gray-500">{rule.description}</div>
                        </div>
                        <button
                          onClick={() =>
                            setPositionRules(positionRules.filter((r) => r.id !== rule.id))
                          }
                          className="text-red-400 hover:text-red-300"
                        >
                          <TrashIcon className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold text-white">포트폴리오 블록</div>
                      <span className="text-[11px] text-gray-500">{portfolioRules.length}개</span>
                    </div>
                    {portfolioRules.length === 0 && (
                      <div className="text-xs text-gray-500 py-4 text-center">
                        리밸런싱/유니버스 규칙을 추가하세요.
                      </div>
                    )}
                    {portfolioRules.map((rule) => (
                      <div
                        key={rule.id}
                        className="flex items-center justify-between bg-[#161616] border border-gray-800 rounded-lg px-3 py-2 text-sm text-white"
                      >
                        <div>
                          <div className="font-semibold">{rule.name}</div>
                          <div className="text-[11px] text-gray-500">{rule.description}</div>
                        </div>
                        <button
                          onClick={() =>
                            setPortfolioRules(portfolioRules.filter((r) => r.id !== rule.id))
                          }
                          className="text-red-400 hover:text-red-300"
                        >
                          <TrashIcon className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-3">
                  <div className="flex items-center gap-2 text-[11px] text-gray-400 flex-wrap">
                    <ShieldExclamationIcon className="w-4 h-4 text-amber-400" />
                    {validatorMessages.map((msg, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-1 rounded bg-[#1c1c1c] border border-gray-800 text-gray-300"
                      >
                        {msg}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Strategy Fusion */}
              <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-white">전략 퓨전 (Strategy Fusion)</h3>
                    <p className="text-xs text-gray-500 mt-1">
                      템플릿 두 개를 합치고 중복 조건을 제거합니다.
                    </p>
                  </div>
                  <SparklesIcon className="w-5 h-5 text-blue-400" />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <select
                    value={fusionPair.a || ""}
                    onChange={(e) => setFusionPair({ ...fusionPair, a: e.target.value || null })}
                    className="px-3 py-2 bg-[#0f0f0f] border border-gray-800 rounded text-sm text-white"
                  >
                    <option value="">템플릿 A 선택</option>
                    {templateStrategies.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={fusionPair.b || ""}
                    onChange={(e) => setFusionPair({ ...fusionPair, b: e.target.value || null })}
                    className="px-3 py-2 bg-[#0f0f0f] border border-gray-800 rounded text-sm text-white"
                  >
                    <option value="">템플릿 B 선택</option>
                    {templateStrategies.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={() => {
                      if (!fusionPair.a || !fusionPair.b) {
                        setFusionLog(["두 템플릿을 모두 선택하세요."]);
                        return;
                      }
                      const dedupedEntry = entryConditions.filter(
                        (c, idx) =>
                          entryConditions.findIndex(
                            (inner) => inner.id === c.id && inner.type === c.type
                          ) === idx
                      );
                      const dedupedExit = exitConditions.filter(
                        (c, idx) =>
                          exitConditions.findIndex(
                            (inner) => inner.id === c.id && inner.type === c.type
                          ) === idx
                      );
                      setEntryConditions(dedupedEntry);
                      setExitConditions(dedupedExit);
                      setFusionLog([
                        `Fusion 완료: ${fusionPair.a} + ${fusionPair.b}`,
                        "중복 조건이 제거되었습니다.",
                      ]);
                    }}
                    className="w-full md:w-auto px-3 py-2 bg-blue-600 text-white rounded text-sm font-semibold hover:bg-blue-500 flex items-center justify-center gap-2"
                  >
                    <ArrowPathIcon className="w-4 h-4" />
                    자동 합치기
                  </button>
                </div>
                {fusionLog.length > 0 && (
                  <div className="text-xs text-gray-400 space-y-1">
                    {fusionLog.map((log, idx) => (
                      <div key={idx}>• {log}</div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Right: Parameter/Preview */}
            <div className="space-y-4">
              <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-white">미리보기 & 백테스트</h3>
                    <p className="text-xs text-gray-500 mt-1">
                      즉시 미리보기 → 빠른/전체 백테스트를 실행하세요.
                    </p>
                  </div>
                  <PlayCircleIcon className="w-6 h-6 text-blue-400" />
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => handlePreviewRun("instant")}
                    className={`px-3 py-2 rounded text-sm font-semibold border ${
                      previewStatus === "instant"
                        ? "bg-blue-600 border-blue-500 text-white"
                        : "bg-[#0f0f0f] border-gray-700 text-white hover:border-blue-500"
                    }`}
                  >
                    즉시 미리보기 (0.5s)
                  </button>
                  <button
                    onClick={() => handlePreviewRun("fast")}
                    className={`px-3 py-2 rounded text-sm font-semibold border ${
                      previewStatus === "fast"
                        ? "bg-blue-600 border-blue-500 text-white"
                        : "bg-[#0f0f0f] border-gray-700 text-white hover:border-blue-500"
                    }`}
                  >
                    빠른 백테스트 (3~5s)
                  </button>
                  <button
                    onClick={() => handlePreviewRun("full")}
                    className={`px-3 py-2 rounded text-sm font-semibold border ${
                      previewStatus === "full"
                        ? "bg-blue-600 border-blue-500 text-white"
                        : "bg-[#0f0f0f] border-gray-700 text-white hover:border-blue-500"
                    }`}
                  >
                    전체 백테스트 (10s+)
                  </button>
                </div>
                <div className="bg-gradient-to-br from-blue-900/20 via-indigo-900/10 to-transparent border border-gray-800 rounded-lg p-3 h-36 flex items-center justify-center text-gray-500 text-xs">
                  시뮬레이션 결과가 여기에 표시됩니다. (미니 차트 자리)
                </div>
                <div className="text-xs text-gray-400 space-y-1 max-h-32 overflow-y-auto">
                  {previewLog.length === 0 && <div>아직 실행한 기록이 없습니다.</div>}
                  {previewLog.map((log, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />
                      <span>{log}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <SparklesIcon className="w-5 h-5 text-emerald-400" />
                  <h4 className="text-sm font-semibold text-white">실시간 시그널 로그</h4>
                </div>
                <div className="text-xs text-gray-400 space-y-1">
                  {(previewLog.slice(0, 5).length === 0 ? ["미리보기 실행 후 로그가 표시됩니다."] : previewLog.slice(0, 5)).map((item, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Risk Management */}
      {currentStep === 3 && (
        <RiskManagementEditor
          riskManagement={riskManagement}
          onChange={setRiskManagement}
        />
      )}

      {/* Condition Editor Modal */}
      {editingCondition && (
        <ConditionBlockEditor
          condition={editingCondition}
          onSave={handleUpdateCondition}
          onCancel={() => setEditingCondition(null)}
        />
      )}

      {/* Navigation Buttons */}
      <div className="flex items-center justify-between mt-12 pt-8 border-t border-white/5">
        <button
          onClick={() => {
            if (currentStep > 1) {
              onStepChange((currentStep - 1) as 1 | 2 | 3);
            } else {
              onCancel();
            }
          }}
          className="px-6 py-2.5 bg-white/5 text-gray-400 rounded-xl text-sm font-bold hover:bg-white/10 hover:text-white transition-all flex items-center gap-2"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          {currentStep === 1 ? "취소" : "이전"}
        </button>

        <div className="flex items-center gap-4">
          {currentStep < 3 ? (
            <button
              onClick={() => {
                if (currentStep === 1 && canProceedToStep2) {
                  onStepChange(2);
                } else if (currentStep === 2 && canProceedToStep3) {
                  onStepChange(3);
                }
              }}
              disabled={
                (currentStep === 1 && !canProceedToStep2) ||
                (currentStep === 2 && !canProceedToStep3)
              }
              className="px-8 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-bold hover:bg-blue-500 hover:shadow-[0_0_20px_rgba(59,130,246,0.3)] disabled:bg-gray-800 disabled:text-gray-600 disabled:cursor-not-allowed transition-all flex items-center gap-2"
            >
              다음 단계
              <ArrowRightIcon className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleSave}
              disabled={!canSave}
              className="px-8 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-bold hover:bg-blue-500 hover:shadow-[0_0_20px_rgba(59,130,246,0.3)] disabled:bg-gray-800 disabled:text-gray-600 disabled:cursor-not-allowed transition-all flex items-center gap-2"
            >
              <CheckCircleIcon className="w-5 h-5" />
              전략 생성 및 저장
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
