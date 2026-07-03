"use client";

import { useMemo, useState } from "react";
import { ArrowsClockwise, X } from "phosphor-react";

type OptimizationMethod = "grid" | "bayesian";

type OptimizationParameterConfig = {
  id: string;
  label: string;
  defaultMin: number;
  defaultMax: number;
  defaultStep: number;
  allowedMin: number;
  allowedMax: number;
  decimals?: number;
  unit?: string;
};

type ParameterDraft = {
  enabled: boolean;
  min: string;
  max: string;
  step: string;
};

interface OptimizationSettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const OPTIMIZATION_METRICS = [
  { value: "sharpe", label: "Sharpe Ratio" },
  { value: "cagr", label: "CAGR" },
  { value: "calmar", label: "Calmar Ratio" },
  { value: "profitFactor", label: "Profit Factor" },
  { value: "mdd", label: "MDD (최소)" },
  { value: "totalReturn", label: "Total Return" },
  { value: "winRate", label: "Win Rate" },
];

const BAYESIAN_TRIAL_OPTIONS = [20, 50, 100, 200, 500];

const PARAMETER_CONFIGS: OptimizationParameterConfig[] = [
  { id: "sma_period", label: "이동평균 (SMA)", defaultMin: 5, defaultMax: 120, defaultStep: 5, allowedMin: 2, allowedMax: 250, unit: "일" },
  { id: "ema_period", label: "EMA", defaultMin: 5, defaultMax: 120, defaultStep: 5, allowedMin: 2, allowedMax: 250, unit: "일" },
  { id: "rsi_period", label: "RSI 기간", defaultMin: 5, defaultMax: 30, defaultStep: 1, allowedMin: 2, allowedMax: 50, unit: "일" },
  { id: "rsi_overbought", label: "RSI 과매수", defaultMin: 65, defaultMax: 90, defaultStep: 5, allowedMin: 55, allowedMax: 95 },
  { id: "rsi_oversold", label: "RSI 과매도", defaultMin: 10, defaultMax: 35, defaultStep: 5, allowedMin: 5, allowedMax: 45 },
  { id: "macd_fast", label: "MACD Fast EMA", defaultMin: 5, defaultMax: 20, defaultStep: 1, allowedMin: 2, allowedMax: 30, unit: "일" },
  { id: "macd_slow", label: "MACD Slow EMA", defaultMin: 20, defaultMax: 40, defaultStep: 1, allowedMin: 10, allowedMax: 60, unit: "일" },
  { id: "macd_signal", label: "MACD Signal", defaultMin: 5, defaultMax: 15, defaultStep: 1, allowedMin: 2, allowedMax: 20, unit: "일" },
  { id: "bb_period", label: "Bollinger Bands 기간", defaultMin: 10, defaultMax: 40, defaultStep: 2, allowedMin: 5, allowedMax: 80, unit: "일" },
  { id: "bb_stddev", label: "Bollinger 표준편차", defaultMin: 1.5, defaultMax: 3, defaultStep: 0.25, allowedMin: 1, allowedMax: 4, decimals: 2 },
  { id: "adx_period", label: "ADX 기간", defaultMin: 7, defaultMax: 30, defaultStep: 1, allowedMin: 5, allowedMax: 50, unit: "일" },
  { id: "adx_threshold", label: "ADX 기준값", defaultMin: 20, defaultMax: 40, defaultStep: 2, allowedMin: 10, allowedMax: 60 },
  { id: "momentum_period", label: "Momentum 기간", defaultMin: 5, defaultMax: 60, defaultStep: 5, allowedMin: 2, allowedMax: 250, unit: "일" },
  { id: "atr_period", label: "ATR 기간", defaultMin: 7, defaultMax: 30, defaultStep: 1, allowedMin: 5, allowedMax: 60, unit: "일" },
  { id: "atr_stop_multiplier", label: "ATR 손절 배수", defaultMin: 1, defaultMax: 5, defaultStep: 0.5, allowedMin: 0.5, allowedMax: 10, decimals: 1, unit: "배" },
  { id: "atr_take_multiplier", label: "ATR 익절 배수", defaultMin: 1, defaultMax: 10, defaultStep: 0.5, allowedMin: 0.5, allowedMax: 20, decimals: 1, unit: "배" },
  { id: "stop_loss_pct", label: "손절(%)", defaultMin: 2, defaultMax: 15, defaultStep: 1, allowedMin: 1, allowedMax: 50, unit: "%" },
  { id: "take_profit_pct", label: "익절(%)", defaultMin: 5, defaultMax: 50, defaultStep: 5, allowedMin: 2, allowedMax: 200, unit: "%" },
  { id: "trailing_stop_pct", label: "트레일링 스탑(%)", defaultMin: 2, defaultMax: 20, defaultStep: 1, allowedMin: 1, allowedMax: 50, unit: "%" },
  { id: "volume_ma_period", label: "거래량 이동평균 기간", defaultMin: 5, defaultMax: 60, defaultStep: 5, allowedMin: 2, allowedMax: 250, unit: "일" },
  { id: "volume_spike_multiplier", label: "거래량 증가 배수", defaultMin: 1.2, defaultMax: 3, defaultStep: 0.2, allowedMin: 1, allowedMax: 10, decimals: 1, unit: "배" },
];

function initialDrafts(): Record<string, ParameterDraft> {
  return PARAMETER_CONFIGS.reduce<Record<string, ParameterDraft>>((acc, config) => {
    acc[config.id] = {
      enabled: false,
      min: String(config.defaultMin),
      max: String(config.defaultMax),
      step: String(config.defaultStep),
    };
    return acc;
  }, {});
}

function numberOrNull(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatDuration(testCount: number) {
  if (testCount <= 0) return "-";
  const seconds = testCount * 0.25;
  if (seconds < 60) return `약 ${Math.max(1, Math.round(seconds))}초`;
  if (seconds < 3600) return `약 ${Math.max(1, Math.round(seconds / 60))}분`;
  return `약 ${Math.round((seconds / 3600) * 10) / 10}시간`;
}

function gridChoiceCount(draft: ParameterDraft) {
  const min = numberOrNull(draft.min);
  const max = numberOrNull(draft.max);
  const step = numberOrNull(draft.step);
  if (min === null || max === null || step === null || min >= max || step <= 0) return 0;
  return Math.floor((max - min) / step) + 1;
}

function validateParameter(config: OptimizationParameterConfig, draft: ParameterDraft, method: OptimizationMethod) {
  const min = numberOrNull(draft.min);
  const max = numberOrNull(draft.max);
  const step = numberOrNull(draft.step);
  const errors: string[] = [];

  if (min === null || max === null) {
    errors.push("숫자를 입력해 주세요.");
    return errors;
  }
  if (min < config.allowedMin || max > config.allowedMax) {
    errors.push(`허용범위 ${formatNumber(config.allowedMin)}~${formatNumber(config.allowedMax)}를 벗어났습니다.`);
  }
  if (min >= max) {
    errors.push("최소값은 최대값보다 작아야 합니다.");
  }
  if (method === "grid" && (step === null || step <= 0)) {
    errors.push("Step은 0보다 커야 합니다.");
  }
  if (/손절|익절|트레일링/.test(config.label) && (min <= 0 || max <= 0)) {
    errors.push(`${config.label} 값은 0보다 커야 합니다.`);
  }

  return errors;
}

function pairErrors(drafts: Record<string, ParameterDraft>) {
  const errors: string[] = [];
  const fast = drafts.macd_fast;
  const slow = drafts.macd_slow;
  const oversold = drafts.rsi_oversold;
  const overbought = drafts.rsi_overbought;

  if (fast.enabled && slow.enabled) {
    const fastMin = numberOrNull(fast.min);
    const slowMax = numberOrNull(slow.max);
    if (fastMin !== null && slowMax !== null && fastMin >= slowMax) {
      errors.push("MACD Fast EMA는 Slow EMA보다 작아야 합니다.");
    }
  }

  if (oversold.enabled && overbought.enabled) {
    const oversoldMax = numberOrNull(oversold.max);
    const overboughtMin = numberOrNull(overbought.min);
    if (oversoldMax !== null && overboughtMin !== null && oversoldMax >= overboughtMin) {
      errors.push("RSI 과매도 값은 RSI 과매수 값보다 작아야 합니다.");
    }
  }

  return errors;
}

export default function OptimizationSettingsModal({
  open,
  onOpenChange,
}: OptimizationSettingsModalProps) {
  const [method, setMethod] = useState<OptimizationMethod>("grid");
  const [targetMetric, setTargetMetric] = useState("sharpe");
  const [bayesianTrials, setBayesianTrials] = useState(100);
  const [drafts, setDrafts] = useState<Record<string, ParameterDraft>>(() => initialDrafts());

  const enabledConfigs = PARAMETER_CONFIGS.filter((config) => drafts[config.id]?.enabled);
  const selectedCount = enabledConfigs.length;
  const rowErrors = PARAMETER_CONFIGS.reduce<Record<string, string[]>>((acc, config) => {
    acc[config.id] = validateParameter(config, drafts[config.id], method);
    return acc;
  }, {});
  const crossErrors = pairErrors(drafts);
  const hasErrors = enabledConfigs.some((config) => rowErrors[config.id].length > 0) || crossErrors.length > 0;

  const gridTestCount = useMemo(() => {
    if (method !== "grid" || selectedCount === 0 || hasErrors) return 0;
    return enabledConfigs.reduce((total, config) => total * gridChoiceCount(drafts[config.id]), 1);
  }, [drafts, enabledConfigs, hasErrors, method, selectedCount]);

  const expectedTests = method === "grid" ? gridTestCount : selectedCount > 0 ? bayesianTrials : 0;

  const updateDraft = (id: string, patch: Partial<ParameterDraft>) => {
    setDrafts((current) => ({
      ...current,
      [id]: {
        ...current[id],
        ...patch,
      },
    }));
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[10000] overflow-y-auto bg-black/80 p-2 md:p-3">
      <div className="mx-auto my-6 flex min-h-[calc(100vh-3rem)] w-full max-w-6xl items-center justify-center">
        <section
          role="dialog"
          aria-modal="true"
          aria-labelledby="optimization-settings-title"
          className="w-full overflow-hidden rounded-2xl border border-white/[0.08] bg-[var(--background)] shadow-[0_24px_80px_rgba(0,0,0,0.65)]"
        >
          <div className="flex items-start justify-between gap-4 border-b border-white/[0.08] p-5 md:p-6">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 text-[11px] font-black uppercase tracking-[0.22em] text-sky-300">
                <ArrowsClockwise className="h-4 w-4" />
                Optimization Settings
              </div>
              <h2 id="optimization-settings-title" className="mt-4 text-2xl font-black tracking-tight text-white">
                전략 최적화
              </h2>
              <p className="mt-2 max-w-2xl text-sm font-bold leading-6 text-gray-300">
                선택한 파라미터의 값을 자동으로 탐색하여 가장 좋은 결과를 찾습니다.
              </p>
            </div>
            <button
              type="button"
              aria-label="전략 최적화 닫기"
              onClick={() => onOpenChange(false)}
              className="rounded-lg border border-white/[0.08] bg-white/[0.04] p-2 text-gray-400 transition-colors hover:bg-white/[0.08] hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="max-h-[calc(100vh-16rem)] overflow-y-auto">
            <div className="grid grid-cols-1 divide-y divide-white/[0.08] lg:grid-cols-3 lg:divide-x lg:divide-y-0">
              <aside className="space-y-5 p-5 md:p-6">
                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">최적화 방식</p>
                  <div className="mt-3 space-y-2">
                    {[
                      { value: "grid", label: "Grid Search", body: "모든 조합을 테스트합니다." },
                      { value: "bayesian", label: "Bayesian Optimization", body: "유망한 값을 우선 탐색하여 적은 횟수로 최적값을 찾습니다." },
                    ].map((item) => (
                      <label
                        key={item.value}
                        className={`block cursor-pointer rounded-xl border p-4 transition-colors ${
                          method === item.value
                            ? "border-sky-400/40 bg-sky-500/10"
                            : "border-white/[0.08] bg-white/[0.03] hover:bg-white/[0.05]"
                        }`}
                      >
                        <span className="flex items-center gap-3">
                          <input
                            type="radio"
                            name="optimization-method"
                            value={item.value}
                            checked={method === item.value}
                            onChange={() => setMethod(item.value as OptimizationMethod)}
                            className="h-4 w-4 accent-[var(--main-blue)]"
                          />
                          <span className="text-sm font-black text-white">{item.label}</span>
                        </span>
                        <span className="mt-2 block text-xs font-bold leading-5 text-gray-400">{item.body}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <label htmlFor="optimization-target-metric" className="text-xs font-bold uppercase tracking-widest text-gray-500">
                    최적화 목표
                  </label>
                  <select
                    id="optimization-target-metric"
                    aria-label="최적화 목표"
                    value={targetMetric}
                    onChange={(event) => setTargetMetric(event.target.value)}
                    className="mt-3 w-full rounded-lg border border-white/[0.08] bg-[#111111] px-3 py-2.5 text-sm font-black text-white outline-none transition-colors focus:border-sky-400/50"
                  >
                    {OPTIMIZATION_METRICS.map((metric) => (
                      <option key={metric.value} value={metric.value}>
                        {metric.label}
                      </option>
                    ))}
                  </select>
                </div>

                {method === "bayesian" && (
                  <div>
                    <p className="text-xs font-bold uppercase tracking-widest text-gray-500">최대 시도 횟수</p>
                    <p className="mt-3 text-3xl font-black text-white font-outfit">{bayesianTrials.toLocaleString()}</p>
                    <input
                      aria-label="최대 시도 횟수"
                      type="range"
                      min={0}
                      max={BAYESIAN_TRIAL_OPTIONS.length - 1}
                      step={1}
                      value={BAYESIAN_TRIAL_OPTIONS.indexOf(bayesianTrials)}
                      onChange={(event) => setBayesianTrials(BAYESIAN_TRIAL_OPTIONS[Number(event.target.value)])}
                      className="mt-4 h-2 w-full cursor-pointer appearance-none rounded-full bg-white/[0.08]"
                    />
                    <div className="mt-3 flex justify-between text-[10px] font-bold uppercase tracking-widest text-gray-500">
                      {BAYESIAN_TRIAL_OPTIONS.map((value) => (
                        <span key={value}>{value}</span>
                      ))}
                    </div>
                    <p className="mt-3 text-xs font-bold leading-5 text-gray-400">
                      최대 시도 횟수만큼 다양한 조합을 탐색합니다.
                    </p>
                  </div>
                )}

                {method === "grid" && (
                  <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] p-4">
                    <p className="text-xs font-bold uppercase tracking-widest text-gray-500">Grid Search 예상</p>
                    <div className="mt-4 grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">예상 테스트</p>
                        <p className="mt-2 text-xl font-black text-white font-outfit">{expectedTests.toLocaleString()}회</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">예상 시간</p>
                        <p className="mt-2 text-xl font-black text-white font-outfit">{formatDuration(expectedTests)}</p>
                      </div>
                    </div>
                  </div>
                )}
              </aside>

              <div className="lg:col-span-2">
                <div className="border-b border-white/[0.08] p-5 md:p-6">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-500">파라미터 목록</p>
                  <p className="mt-2 text-sm font-bold leading-6 text-gray-400">
                    선택하지 않은 파라미터는 기존 전략 값을 그대로 사용합니다.
                  </p>
                </div>
                <div className="divide-y divide-white/[0.06]">
                  {PARAMETER_CONFIGS.map((config) => {
                    const draft = drafts[config.id];
                    const errors = rowErrors[config.id];
                    return (
                      <div key={config.id} className="p-4 md:p-5">
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1.2fr)_repeat(3,minmax(0,0.65fr))] md:items-start">
                          <label className="flex cursor-pointer items-start gap-3">
                            <input
                              type="checkbox"
                              checked={draft.enabled}
                              onChange={(event) => updateDraft(config.id, { enabled: event.target.checked })}
                              className="mt-1 h-4 w-4 rounded accent-[var(--main-blue)]"
                            />
                            <span>
                              <span className="block text-sm font-black text-white">{config.label}</span>
                              <span className="mt-1 block text-[11px] font-bold leading-5 text-gray-500">
                                허용범위 {formatNumber(config.allowedMin)}~{formatNumber(config.allowedMax)}
                                {config.unit ? config.unit : ""}
                              </span>
                            </span>
                          </label>

                          {[
                            { key: "min", label: "최소값", aria: `${config.label} 최소값` },
                            { key: "max", label: "최대값", aria: `${config.label} 최대값` },
                            { key: "step", label: "Step", aria: `${config.label} Step` },
                          ].filter((field) => method === "grid" || field.key !== "step").map((field) => (
                            <label key={field.key} className="block">
                              <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">{field.label}</span>
                              <input
                                aria-label={field.aria}
                                type="number"
                                value={draft[field.key as keyof ParameterDraft] as string}
                                min={field.key === "max" ? config.allowedMin : config.allowedMin}
                                max={config.allowedMax}
                                step={field.key === "step" ? config.defaultStep : config.decimals ? 0.1 : 1}
                                onChange={(event) => updateDraft(config.id, { [field.key]: event.target.value })}
                                className="mt-1 w-full rounded-lg border border-white/[0.08] bg-[#111111] px-3 py-2 text-sm font-black text-white outline-none transition-colors focus:border-sky-400/50"
                              />
                            </label>
                          ))}
                        </div>
                        {errors.length > 0 && (
                          <div className="mt-3 space-y-1">
                            {errors.map((error) => (
                              <p key={error} className="text-xs font-bold leading-5 text-[var(--main-blue)]">
                                {error}
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3 border-t border-white/[0.08] bg-[#0d0d0d] p-4 md:flex-row md:items-center md:justify-between md:px-6">
            <div className="flex flex-wrap gap-4 text-sm font-black text-white">
              <span>선택된 파라미터 {selectedCount.toLocaleString()}개</span>
              <span>예상 테스트 {expectedTests.toLocaleString()}회</span>
              {method === "grid" && <span>예상 시간 {formatDuration(expectedTests)}</span>}
            </div>
            <div className="flex items-center gap-2">
              {crossErrors.map((error) => (
                <p key={error} className="hidden text-xs font-bold text-[var(--main-blue)] md:block">
                  {error}
                </p>
              ))}
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="rounded-lg px-4 py-2 text-sm font-black text-gray-400 transition-colors hover:bg-white/[0.05] hover:text-white"
              >
                닫기
              </button>
              <button
                type="button"
                disabled={hasErrors}
                onClick={() => onOpenChange(false)}
                className="rounded-lg bg-[var(--main-blue)] px-4 py-2 text-sm font-black text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                설정 저장
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
