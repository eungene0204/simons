"use client";

import { useState, useEffect } from "react";
import { X, CaretDown, Robot } from "phosphor-react";
import {
  buildStrategySummaryChips,
  buildStrategySummaryFromDsl,
} from "@/lib/strategy-summary";
import type { StrategyDSL } from "@/types/strategy";

type Strategy = Pick<StrategyDSL, "id" | "name" | "description" | "universe" | "entry" | "exit" | "risk">;
const NO_STRATEGY_ID = "__none__";

interface CreateAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (name: string, amount: number, strategyId?: string, strategyName?: string, tradingMode?: "auto" | "manual") => void;
}

export default function CreateAccountModal({
  isOpen,
  onClose,
  onCreate,
}: CreateAccountModalProps) {
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [tradingMode, setTradingMode] = useState<"auto" | "manual">("manual");
  const [isPromptVisible, setIsPromptVisible] = useState(false);
  const [availableCash, setAvailableCash] = useState<number | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setLoadingStrategies(true);
    fetch("/api/strategy")
      .then((res) => res.ok ? res.json() : [])
      .then((data: Strategy[]) => setStrategies(data))
      .catch(() => setStrategies([]))
      .finally(() => setLoadingStrategies(false));

    fetch("/api/user/assets")
      .then((res) => res.ok ? res.json() : null)
      .then((data) => setAvailableCash(data?.availableCash ?? null))
      .catch(() => setAvailableCash(null));
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    setIsPromptVisible(false);
  }, [isOpen, selectedStrategyId]);

  if (!isOpen) return null;

  const isNoStrategySelected = selectedStrategyId === NO_STRATEGY_ID;
  const selectedStrategy = strategies.find((s) => s.id === selectedStrategyId);
  const selectedSummary = buildStrategySummaryFromDsl(selectedStrategy as unknown as StrategyDSL);
  const summaryChips = buildStrategySummaryChips(selectedSummary);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!name.trim()) {
      setError("계좌 이름을 입력해주세요.");
      return;
    }

    const amountNum = parseFloat(amount.replace(/,/g, ""));
    if (isNaN(amountNum)) {
      setError("투자금액을 올바르게 입력해주세요.");
      return;
    }

    const amountInWon = amountNum * 10000;

    if (amountNum < 100) {
      setError("최소 투자금액은 100만원입니다.");
      return;
    }

    if (availableCash !== null && amountInWon > availableCash) {
      setError("투자가능 금액을 초과했습니다.");
      return;
    }

    if (!selectedStrategyId) {
      setError("전략을 선택해주세요.");
      return;
    }

    onCreate(
      name.trim(),
      amountInWon,
      isNoStrategySelected ? undefined : selectedStrategyId,
      isNoStrategySelected ? undefined : selectedStrategy?.name,
      isNoStrategySelected ? "manual" : tradingMode
    );
    setName("");
    setAmount("");
    setSelectedStrategyId("");
    setTradingMode("manual");
    setIsPromptVisible(false);
    onClose();
  };

  const handleAmountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/[^0-9]/g, "");
    setAmount(value);
  };

  const formatAmount = (value: string) => {
    if (!value) return "";
    return parseInt(value).toLocaleString("ko-KR");
  };

  return (
    <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-50">
      <div className="bg-[#111111] border border-white/[0.08] rounded-lg shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between p-4 border-b border-white/[0.08]">
          <h2 className="text-lg font-semibold text-white">
            가상계좌 만들기
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              계좌 이름
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-white/[0.08] rounded-lg bg-[#171717] text-white placeholder:text-gray-600 focus:outline-none focus:border-white/[0.2]"
              placeholder="예: 저PBR 전략, 모멘텀 전략, 가치주 전략..."
              maxLength={20}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              투자금액 (단위: 만원)
            </label>
            <div className="relative">
              <input
                type="text"
                value={formatAmount(amount)}
                onChange={handleAmountChange}
                className={`w-full px-3 py-2 border rounded-lg bg-[#171717] text-white placeholder:text-gray-600 focus:outline-none ${
                  availableCash !== null && amount && parseInt(amount) * 10000 > availableCash
                    ? "border-red-500/60 focus:border-red-500"
                    : "border-white/[0.08] focus:border-white/[0.2]"
                }`}
                placeholder="100"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                만원
              </span>
            </div>
            <div className="mt-1 flex items-center justify-between">
              <p className={`text-xs ${availableCash !== null && amount && parseInt(amount) * 10000 > availableCash ? "text-red-400" : "text-gray-500"}`}>
                {availableCash !== null && amount && parseInt(amount) * 10000 > availableCash
                  ? "투자가능 금액을 초과했습니다"
                  : "최소 100만원"}
              </p>
              {availableCash !== null && (
                <p className="text-xs text-gray-400">
                  투자가능 금액:{" "}
                  <span className="font-semibold text-gray-300">
                    {availableCash.toLocaleString("ko-KR")}원
                  </span>
                </p>
              )}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              전략 선택
            </label>
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsDropdownOpen((prev) => !prev)}
                className="w-full px-3 py-2 border border-white/[0.08] rounded-lg bg-[#171717] text-left flex items-center justify-between focus:outline-none focus:border-white/[0.2]"
              >
                <span
                  className={
                    selectedStrategy
                      ? "text-white text-sm"
                      : "text-gray-500 text-sm"
                  }
                >
                  {loadingStrategies
                    ? "로딩 중..."
                    : isNoStrategySelected
                    ? "전략 없음"
                    : selectedStrategy
                    ? selectedStrategy.name
                    : "전략을 선택하세요"}
                </span>
                <CaretDown
                  size={16}
                  className={`text-gray-400 transition-transform ${isDropdownOpen ? "rotate-180" : ""}`}
                />
              </button>

              {isDropdownOpen && (
                <div className="absolute z-10 mt-1 w-full bg-[#171717] border border-white/[0.08] rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedStrategyId(NO_STRATEGY_ID);
                      setTradingMode("manual");
                      setIsDropdownOpen(false);
                    }}
                    className={`w-full px-3 py-2 text-left text-sm hover:bg-white/[0.06] ${
                      isNoStrategySelected
                        ? "text-blue-400 bg-blue-500/10"
                        : "text-white"
                    }`}
                  >
                    전략 없음
                  </button>
                  {strategies.length === 0 ? (
                    <div className="px-3 py-2 text-sm text-gray-500">
                      저장된 전략이 없습니다
                    </div>
                  ) : (
                    strategies.map((strategy) => (
                      <button
                        key={strategy.id}
                        type="button"
                        onClick={() => {
                          setSelectedStrategyId(strategy.id);
                          setTradingMode("manual");
                          setIsDropdownOpen(false);
                        }}
                        className={`w-full px-3 py-2 text-left text-sm hover:bg-white/[0.06] ${
                          selectedStrategyId === strategy.id
                            ? "text-blue-400 bg-blue-500/10"
                            : "text-white"
                        }`}
                      >
                        {strategy.name}
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          {selectedStrategy && (
            <div className="rounded-lg border border-white/[0.08] bg-[#171717] p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-white">
                    운용 전략
                  </p>
                  <p className="mt-0.5 text-xs text-gray-500">
                    선택한 전략의 핵심 조건을 먼저 확인합니다.
                  </p>
                </div>
                {selectedStrategy.description && (
                  <button
                    type="button"
                    onClick={() => setIsPromptVisible((prev) => !prev)}
                    className="shrink-0 rounded-md border border-white/[0.08] px-2.5 py-1 text-xs font-medium text-gray-300 transition-colors hover:bg-white/[0.06]"
                  >
                    {isPromptVisible ? "프롬프트 숨기기" : "프롬프트 보기"}
                  </button>
                )}
              </div>

              {summaryChips.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {summaryChips.map((chip) => (
                    <span
                      key={chip}
                      className="rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-gray-200"
                    >
                      {chip}
                    </span>
                  ))}
                </div>
              )}

              {isPromptVisible && selectedStrategy.description && (
                <div className="mt-3 rounded-lg border border-white/[0.08] bg-[#111111] p-3">
                  <p className="mb-1 text-xs font-semibold text-gray-500">
                    사용자 프롬프트
                  </p>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-gray-300">
                    {selectedStrategy.description}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* 매매 모드 선택 — 전략을 선택했을 때만 표시 */}
          {selectedStrategyId && !isNoStrategySelected && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                매매 방식
              </label>
              <button
                type="button"
                aria-label={`자동매매 ${tradingMode === "auto" ? "ON" : "OFF"}`}
                aria-pressed={tradingMode === "auto"}
                onClick={() => {
                  setTradingMode((prev) => prev === "auto" ? "manual" : "auto");
                }}
                className={`flex w-full items-center gap-3 rounded-lg border-2 p-3 text-left transition-all ${
                  tradingMode === "auto"
                    ? "border-blue-500"
                    : "border-white/[0.08] hover:border-white/[0.18]"
                }`}
              >
                <Robot
                  size={24}
                  className={tradingMode === "auto" ? "text-blue-400" : "text-gray-500"}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className={`text-sm font-semibold ${tradingMode === "auto" ? "text-blue-400" : "text-gray-300"}`}>
                      자동매매
                    </p>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-black tracking-wider ${
                        tradingMode === "auto"
                          ? "bg-blue-500/20 text-blue-300"
                          : "bg-white/[0.08] text-gray-500"
                      }`}
                    >
                      {tradingMode === "auto" ? "ON" : "OFF"}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-gray-500">
                    신호 발생 시 자동 주문
                  </p>
                </div>
              </button>
              <p className={`mt-2 rounded px-2 py-1.5 text-xs ${
                tradingMode === "auto"
                  ? "text-blue-400"
                  : "bg-white/[0.04] text-gray-400"
              }`}>
                {tradingMode === "auto"
                  ? "전략 신호가 발생하면 현재가로 자동 주문이 실행됩니다."
                  : "자동매매는 꺼져 있습니다. 계좌 생성 후에도 직접 켤 수 있습니다."}
              </p>
            </div>
          )}

          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-white/[0.08] rounded-lg text-gray-300 hover:bg-white/[0.06] transition-colors"
            >
              취소
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition-colors"
            >
              만들기
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
