"use client";

import { useState, useEffect } from "react";
import { X, CaretDown, Robot, Bell } from "phosphor-react";

interface Strategy {
  id: string;
  name: string;
}

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

  useEffect(() => {
    if (!isOpen) return;
    setLoadingStrategies(true);
    fetch("/api/strategy")
      .then((res) => res.ok ? res.json() : [])
      .then((data: Strategy[]) => setStrategies(data))
      .catch(() => setStrategies([]))
      .finally(() => setLoadingStrategies(false));
  }, [isOpen]);

  if (!isOpen) return null;

  const selectedStrategy = strategies.find((s) => s.id === selectedStrategyId);

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

    if (amountNum > 1000) {
      setError("최대 투자금액은 1000만원입니다.");
      return;
    }

    if (!selectedStrategyId) {
      setError("전략을 선택해주세요.");
      return;
    }

    onCreate(
      name.trim(),
      amountInWon,
      selectedStrategyId,
      selectedStrategy?.name,
      tradingMode
    );
    setName("");
    setAmount("");
    setSelectedStrategyId("");
    setTradingMode("manual");
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
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            가상계좌 만들기
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              계좌 이름
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="예: 바이오, 반도체,..."
              maxLength={20}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              투자금액 (단위: 만원)
            </label>
            <div className="relative">
              <input
                type="text"
                value={formatAmount(amount)}
                onChange={handleAmountChange}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="100"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 dark:text-gray-400 text-sm">
                만원
              </span>
            </div>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              최소 100만원 ~ 최대 1000만원
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              전략 선택
            </label>
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsDropdownOpen((prev) => !prev)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-left flex items-center justify-between focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <span
                  className={
                    selectedStrategy
                      ? "text-gray-900 dark:text-white text-sm"
                      : "text-gray-400 dark:text-gray-500 text-sm"
                  }
                >
                  {loadingStrategies
                    ? "로딩 중..."
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
                <div className="absolute z-10 mt-1 w-full bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  {strategies.length === 0 ? (
                    <div className="px-3 py-2 text-sm text-gray-400 dark:text-gray-500">
                      저장된 전략이 없습니다
                    </div>
                  ) : (
                    strategies.map((strategy) => (
                      <button
                        key={strategy.id}
                        type="button"
                        onClick={() => {
                          setSelectedStrategyId(strategy.id);
                          setIsDropdownOpen(false);
                        }}
                        className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-600 ${
                          selectedStrategyId === strategy.id
                            ? "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20"
                            : "text-gray-900 dark:text-white"
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

          {/* 매매 모드 선택 — 전략을 선택했을 때만 표시 */}
          {selectedStrategyId && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                매매 방식
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setTradingMode("auto")}
                  className={`flex flex-col items-center gap-2 p-3 rounded-lg border-2 transition-all ${
                    tradingMode === "auto"
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                      : "border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500"
                  }`}
                >
                  <Robot
                    size={24}
                    className={tradingMode === "auto" ? "text-blue-500" : "text-gray-400 dark:text-gray-500"}
                  />
                  <div className="text-center">
                    <p className={`text-sm font-semibold ${tradingMode === "auto" ? "text-blue-600 dark:text-blue-400" : "text-gray-700 dark:text-gray-300"}`}>
                      자동매매
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                      신호 발생 시 자동 주문
                    </p>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setTradingMode("manual")}
                  className={`flex flex-col items-center gap-2 p-3 rounded-lg border-2 transition-all ${
                    tradingMode === "manual"
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                      : "border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500"
                  }`}
                >
                  <Bell
                    size={24}
                    className={tradingMode === "manual" ? "text-blue-500" : "text-gray-400 dark:text-gray-500"}
                  />
                  <div className="text-center">
                    <p className={`text-sm font-semibold ${tradingMode === "manual" ? "text-blue-600 dark:text-blue-400" : "text-gray-700 dark:text-gray-300"}`}>
                      신호 알림만
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                      알림 받고 직접 매매
                    </p>
                  </div>
                </button>
              </div>
              {tradingMode === "auto" && (
                <p className="mt-2 text-xs text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 rounded px-2 py-1.5">
                  전략 신호가 발생하면 현재가로 자동 주문이 실행됩니다.
                </p>
              )}
              {tradingMode === "manual" && (
                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-700 rounded px-2 py-1.5">
                  신호 발생 시 알림을 받고, 직접 매매 여부를 결정합니다.
                </p>
              )}
            </div>
          )}

          {error && (
            <div className="p-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              취소
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-600 transition-colors"
            >
              만들기
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
