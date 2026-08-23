"use client";

import { useState, useEffect } from "react";
import { X, CaretDown, Robot, Spinner } from "phosphor-react";
import {
  buildStrategySummaryChips,
  buildStrategySummaryFromDsl,
} from "@/lib/strategy-summary";
import type { StrategyDSL } from "@/types/strategy";
import { t } from "@/lib/i18n";

type Strategy = Pick<StrategyDSL, "id" | "name" | "description" | "universe" | "entry" | "exit" | "risk">;
const NO_STRATEGY_ID = "__none__";

interface CreateAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (name: string, amount: number, strategyId?: string, strategyName?: string, tradingMode?: "auto" | "manual") => void | Promise<void>;
  /**
   * 운용 전략이 이미 정해진 채로 여는 경우(백테스트 결과에서 바로 계좌 만들기).
   * 전략 목록·드롭다운 대신 이 전략을 고정해 보여준다. 아직 저장 전일 수 있어 id 가 없으므로,
   * onCreate 의 strategyId 는 undefined 로 전달되고 전략 행 확정은 부모가 맡는다.
   */
  presetStrategy?: {
    name: string;
    description?: string;
    /** 결과 화면 '내 전략' 팝오버와 같은 라벨·값 행 목록(promptSummaryRows). */
    summaryRows?: { label: string; values: string[] }[];
  };
}

export default function CreateAccountModal({
  isOpen,
  onClose,
  onCreate,
  presetStrategy,
}: CreateAccountModalProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [tradingMode, setTradingMode] = useState<"auto" | "manual">("manual");
  const [isPromptVisible, setIsPromptVisible] = useState(false);
  const [planInfo, setPlanInfo] = useState<{
    initialInvestmentAmount: number;
    accountsUsed: number;
    accountsLimit: number;
  } | null>(null);

  // 부모가 매 렌더 새 객체를 넘겨도 이름이 그대로면 효과가 다시 돌지 않게 한다
  // (돌면 사용자가 고쳐 넣은 계좌 이름을 되돌려 버린다).
  const presetStrategyName = presetStrategy?.name ?? null;

  useEffect(() => {
    if (!isOpen) return;
    if (presetStrategyName !== null) {
      // 전략이 이미 정해져 있으면 목록을 불러올 이유가 없다.
      setName(presetStrategyName.slice(0, 20));
      setStrategies([]);
      // 백테스트로 검증을 마친 전략을 그대로 돌려보려고 여는 화면이라 전략 시뮬레이션을 켜둔다
      // (드롭다운으로 전략을 고르는 기존 경로의 기본값은 OFF 그대로).
      setTradingMode("auto");
      return;
    }
    setLoadingStrategies(true);
    fetch("/api/strategy")
      .then((res) => res.ok ? res.json() : [])
      .then((data: Strategy[]) => setStrategies(data))
      .catch(() => setStrategies([]))
      .finally(() => setLoadingStrategies(false));
  }, [isOpen, presetStrategyName]);

  useEffect(() => {
    if (!isOpen) return;
    fetch("/api/user/plan")
      .then((res) => res.ok ? res.json() : null)
      .then((data) =>
        setPlanInfo(
          data
            ? {
                initialInvestmentAmount: data.plan.initialInvestmentAmount,
                accountsUsed: data.accounts.used,
                accountsLimit: data.accounts.limit,
              }
            : null
        )
      )
      .catch(() => setPlanInfo(null));
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    setIsPromptVisible(false);
  }, [isOpen, selectedStrategyId]);

  if (!isOpen) return null;

  const isNoStrategySelected = !presetStrategy && selectedStrategyId === NO_STRATEGY_ID;
  const selectedStrategy = strategies.find((s) => s.id === selectedStrategyId);
  const selectedSummary = buildStrategySummaryFromDsl(selectedStrategy as unknown as StrategyDSL);
  const summaryChips = buildStrategySummaryChips(selectedSummary);
  // 드롭다운 선택이든 고정 전략이든 아래 화면은 같은 한 벌로 그린다.
  const boundStrategy = presetStrategy
    ? {
        name: presetStrategy.name,
        description: presetStrategy.description,
        chips: [] as string[],
        rows: presetStrategy.summaryRows ?? [],
      }
    : selectedStrategy
    ? {
        name: selectedStrategy.name,
        description: selectedStrategy.description,
        chips: summaryChips,
        rows: [] as { label: string; values: string[] }[],
      }
    : null;

  const accountLimitReached =
    planInfo !== null && planInfo.accountsUsed >= planInfo.accountsLimit;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setError("");

    if (!name.trim()) {
      setError(t("계좌 이름을 입력해주세요."));
      return;
    }

    if (accountLimitReached) {
      setError(t("현재 플랜의 가상계좌 수 한도에 도달했습니다."));
      return;
    }

    if (!presetStrategy && !selectedStrategyId) {
      setError(t("전략을 선택해주세요."));
      return;
    }

    // 초기 투자금은 서버가 플랜 기준으로 결정한다. 표시 일관성을 위해 플랜 금액을 전달한다.
    const initialInvestment = planInfo?.initialInvestmentAmount ?? 0;

    setIsSubmitting(true);

    try {
      await onCreate(
        name.trim(),
        initialInvestment,
        presetStrategy || isNoStrategySelected ? undefined : selectedStrategyId,
        presetStrategy ? presetStrategy.name : isNoStrategySelected ? undefined : selectedStrategy?.name,
        isNoStrategySelected ? "manual" : tradingMode
      );
      setName("");
      setSelectedStrategyId("");
      setTradingMode("manual");
      setIsPromptVisible(false);
      onClose();
    } catch (e) {
      // 부모가 이유를 담아 던지면(전략 저장 한도 등) 그 문구를 그대로 보여준다.
      setError(
        e instanceof Error && e.message
          ? e.message
          : t("계좌 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.")
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 flex items-center justify-center z-50">
      <div className="bg-[#111111] border border-white/[0.08] rounded-lg shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between p-4 border-b border-white/[0.08]">
          <h2 className="text-lg font-semibold text-white">
            {t("가상계좌 만들기")}
          </h2>
          <button
            onClick={() => {
              if (isSubmitting) return;
              onClose();
            }}
            disabled={isSubmitting}
            className="text-gray-400 hover:text-white disabled:cursor-wait disabled:opacity-50"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              {t("계좌 이름")}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSubmitting}
              className="w-full px-3 py-2 border border-white/[0.08] rounded-lg bg-[#171717] text-white placeholder:text-gray-600 focus:outline-none focus:border-white/[0.2]"
              placeholder={t("예: 저PBR 전략, 모멘텀 전략, 가치주 전략...")}
              maxLength={20}
            />
          </div>

          <div className="rounded-lg border border-white/[0.08] bg-[#171717] p-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-300">{t("계좌당 초기 모의 투자금")}</span>
              <span className="text-sm font-semibold text-white">
                {planInfo
                  ? t("{0}원", planInfo.initialInvestmentAmount.toLocaleString("ko-KR"))
                  : "—"}
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <span className="text-xs text-gray-500">{t("사용 중인 계좌")}</span>
              <span className={`text-xs font-semibold ${accountLimitReached ? "text-red-400" : "text-gray-400"}`}>
                {planInfo ? t("{0} / {1}개", planInfo.accountsUsed, planInfo.accountsLimit) : "—"}
              </span>
            </div>
            {accountLimitReached && (
              <div className="mt-2 text-xs leading-5 text-red-400">
                <p>
                  {t("현재 플랜의 가상계좌 수 한도에 도달했습니다. 요금제를 업그레이드하면 더 많은 계좌를 만들 수 있습니다.")}
                </p>
                <div className="mt-1 flex justify-end">
                  <a
                    href="/pricing"
                    className="inline-flex items-center rounded-[4px] border border-gray-500/50 px-1.5 py-px text-[9px] font-black text-gray-300 transition-colors hover:border-gray-300/70 hover:text-white"
                  >
                    {t("업그레이드")}
                  </a>
                </div>
              </div>
            )}
          </div>

          {presetStrategy ? null : (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              {t("전략 선택")}
            </label>
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsDropdownOpen((prev) => !prev)}
                disabled={isSubmitting}
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
                    ? t("로딩 중...")
                    : isNoStrategySelected
                    ? t("전략 없음")
                    : selectedStrategy
                    ? selectedStrategy.name
                    : t("전략을 선택하세요")}
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
                      if (isSubmitting) return;
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
                    {t("전략 없음")}
                  </button>
                  {strategies.length === 0 ? (
                    <div className="px-3 py-2 text-sm text-gray-500">
                      {t("저장된 전략이 없습니다")}
                    </div>
                  ) : (
                    strategies.map((strategy) => (
                      <button
                        key={strategy.id}
                        type="button"
                        onClick={() => {
                          if (isSubmitting) return;
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
          )}

          {boundStrategy && (
            <div className="rounded-lg border border-white/[0.08] bg-[#171717] p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold text-gray-500">
                    {t("운용 전략")}
                  </p>
                  <p data-testid="bound-strategy-name" className="mt-0.5 text-sm font-semibold text-white">
                    {boundStrategy.name}
                  </p>
                </div>
                {boundStrategy.description && (
                  <button
                    type="button"
                    onClick={() => {
                      if (isSubmitting) return;
                      setIsPromptVisible((prev) => !prev);
                    }}
                    disabled={isSubmitting}
                    className="shrink-0 rounded-md border border-white/[0.08] px-2.5 py-1 text-xs font-medium text-gray-300 transition-colors hover:bg-white/[0.06]"
                  >
                    {isPromptVisible ? t("프롬프트 숨기기") : t("프롬프트 보기")}
                  </button>
                )}
              </div>

              {boundStrategy.rows.length > 0 ? (
                /* 결과 화면 '내 전략' 팝오버와 같은 규칙 — 라벨 열을 고정한 그리드에 값을
                   한 줄에 하나씩 쌓아 세로줄을 맞춘다. */
                <dl data-testid="bound-strategy-rows" className="border-t border-white/[0.06] pt-1">
                  {boundStrategy.rows.map((row) => (
                    <div
                      key={row.label}
                      className="grid grid-cols-[64px_minmax(0,1fr)] gap-3 py-1.5 text-xs leading-relaxed"
                    >
                      <dt className="break-keep font-bold text-gray-500">{row.label}</dt>
                      <dd className="min-w-0 break-keep font-bold text-gray-200">
                        <span className="flex flex-col gap-0.5">
                          {row.values.map((value, i) => (
                            <span key={`${value}-${i}`}>{value}</span>
                          ))}
                        </span>
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : boundStrategy.chips.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {boundStrategy.chips.map((chip) => (
                    <span
                      key={chip}
                      className="rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-gray-200"
                    >
                      {chip}
                    </span>
                  ))}
                </div>
              ) : null}

              {isPromptVisible && boundStrategy.description && (
                <div className="mt-3 rounded-lg border border-white/[0.08] bg-[#111111] p-3">
                  <p className="mb-1 text-xs font-semibold text-gray-500">
                    {t("사용자 프롬프트")}
                  </p>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-gray-300">
                    {boundStrategy.description}
                  </p>
                </div>
              )}
            </div>
          )}

          {presetStrategy && (
            <p className="text-xs leading-5 text-gray-500">
              {t("방금 백테스트한 전략이 이 계좌의 운용 전략이 됩니다. 아직 저장 전이라면 계좌를 만들 때 내 전략에 함께 저장됩니다.")}
            </p>
          )}

          {/* 매매 모드 선택 — 전략이 정해졌을 때만 표시 */}
          {(presetStrategy || (selectedStrategyId && !isNoStrategySelected)) && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {t("매매 방식")}
              </label>
              <button
                type="button"
                aria-label={t("전략 시뮬레이션 {0}", tradingMode === "auto" ? "ON" : "OFF")}
                aria-pressed={tradingMode === "auto"}
                disabled={isSubmitting}
                onClick={() => {
                  if (isSubmitting) return;
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
                      {t("전략 시뮬레이션")}
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
                    {t("전략 신호 기반 자동매매")}
                  </p>
                </div>
              </button>
              <p className={`mt-2 rounded px-2 py-1.5 text-xs ${
                tradingMode === "auto"
                  ? "text-blue-400"
                  : "bg-white/[0.04] text-gray-400"
              }`}>
                {tradingMode === "auto"
                  ? t("전략 신호가 발생하면 현재가로 모의 주문이 실행됩니다.")
                  : t("전략 시뮬레이션은 꺼져 있습니다. 계좌 생성 후에도 직접 켤 수 있습니다.")}
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
              disabled={isSubmitting}
              className="flex-1 px-4 py-2 border border-white/[0.08] rounded-lg text-gray-300 hover:bg-white/[0.06] transition-colors disabled:cursor-wait disabled:opacity-50"
            >
              {t("취소")}
            </button>
            <button
              type="submit"
              disabled={accountLimitReached || isSubmitting}
              aria-busy={isSubmitting}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="flex items-center justify-center gap-2">
                {isSubmitting ? (
                  <Spinner size={16} className="animate-spin" aria-hidden="true" />
                ) : null}
                {isSubmitting ? t("계좌 생성중...") : t("만들기")}
              </span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
