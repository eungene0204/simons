"use client";

import { useState, useEffect } from "react";
import { 
  PlayCircle,
  ArrowsClockwise,
  Globe,
  Code,
  Briefcase,
  ShieldCheck,
  WarningCircle,
  ChartBar
} from "phosphor-react";

const formatKoreanUnit = (num: number) => {
  if (num === 0) return "0원";
  const units = ["", "만", "억", "조", "경"];
  const result = [];
  let temp = num;
  let unitIdx = 0;

  while (temp > 0 && unitIdx < units.length) {
    const chunk = temp % 10000;
    if (chunk > 0) {
      const formattedChunk = chunk.toLocaleString();
      result.unshift(`${formattedChunk}${units[unitIdx]}`);
    }
    temp = Math.floor(temp / 10000);
    unitIdx++;
  }

  return result.join(" ") + "원";
};

export interface BacktestConfigOptions {
  period: string;
  startDate?: string;
  endDate?: string;
  initialCapital: number;
  commissionPct: number;
  slippagePct: number;
}

export interface StrategySummaryData {
  strategyName: string;
  universeName: string;
  universeSettings: {
    marketCapRange: number[];
    minTradingVolume: number;
    selectedSectors: string[];
    excludeLossMaking: boolean;
    excludeCapitalImpaired: boolean;
    excludeAdministrative: boolean;
    excludePreferred: boolean;
    excludeETF_ETN: boolean;
    excludeSPAC: boolean;
    excludeREITs: boolean;
    excludeInvestmentWarning: boolean;
    excludeDelistingPending: boolean;
    excludeForeignStock: boolean;
    excludePennyStocks: boolean;
    excludeNewListings: boolean;
    excludeHighVolatility: boolean;
  };
  universeFiltersCount: number;
  blockNames: string[];
  entryLogic?: string;
  exitLogic?: string;
    riskSettings: {
    maxPositions: number;
    allocationType: string;
    allocationValue?: number;
    executionTiming: string;
    rebalancingPeriod: string;
    skip_position_setting?: boolean;
  };
  riskManagement: {
    stop_loss_pct?: number;
    take_profit_pct?: number;
    trailing_stop_pct?: number;
    position_size_pct?: number;
    liquidity_limit_pct?: number;
    min_cash_reserve_pct?: number;
    max_daily_loss_pct?: number;
    max_mdd_limit_pct?: number;
    max_total_exposure_pct?: number;
    skip_risk_management?: boolean;
  };
}

interface BacktestConfigProps {
  onRun: (options: BacktestConfigOptions) => void;
  isRunning: boolean;
  initialConfig?: Partial<BacktestConfigOptions>;
  summary: StrategySummaryData;
}

const getRebalancingLabel = (period?: string) => {
  if (!period || period === "none") return "안함";
  if (period === "daily") return "매일";
  if (period === "weekly") return "매주";
  if (period === "monthly") return "매월";
  if (period.startsWith("custom:")) {
    const parts = period.split(":");
    const unit = parts[2] === "day" ? "일" : parts[2] === "week" ? "주" : "달";
    return `${parts[1]}${unit}마다`;
  }
  return period;
};

export default function BacktestConfig({ onRun, isRunning, initialConfig, summary }: BacktestConfigProps) {
  const [period, setPeriod] = useState(initialConfig?.period || "1Y");
  const [initialCapital, setInitialCapital] = useState(initialConfig?.initialCapital || 10000000);
  const [commissionPct, setCommissionPct] = useState(initialConfig?.commissionPct || 0.015);
  const [slippagePct, setSlippagePct] = useState(initialConfig?.slippagePct || 0.05);
  
  console.log("[DEBUG-UI] BacktestConfig summary.entryLogic:", summary.entryLogic);

  // Custom Date Range State
  const [startDate, setStartDate] = useState(initialConfig?.startDate || new Date(new Date().setFullYear(new Date().getFullYear() - 1)).toISOString().split('T')[0]);
  const [endDate, setEndDate] = useState(initialConfig?.endDate || new Date().toISOString().split('T')[0]);

  // Sync with initialConfig if it changes (e.g. returning from dashboard)
  useEffect(() => {
    if (initialConfig) {
      if (initialConfig.period) setPeriod(initialConfig.period);
      if (initialConfig.initialCapital) setInitialCapital(initialConfig.initialCapital);
      if (initialConfig.commissionPct !== undefined) setCommissionPct(initialConfig.commissionPct);
      if (initialConfig.slippagePct !== undefined) setSlippagePct(initialConfig.slippagePct);
      if (initialConfig.startDate) setStartDate(initialConfig.startDate);
      if (initialConfig.endDate) setEndDate(initialConfig.endDate);
    }
  }, [initialConfig]);

  const periods = [
    { id: "6M", label: "6개월" },
    { id: "1Y", label: "1년" },
    { id: "5Y", label: "5년" },
    { id: "10Y", label: "10년" },
    { id: "20Y", label: "20년" },
    { id: "custom", label: "직접 입력" },
  ];
  const handlePeriodChange = (id: string) => {
    setPeriod(id);
    if (id !== "custom") {
      const end = new Date();
      const start = new Date();
      
      switch (id) {
        case "6M": start.setMonth(end.getMonth() - 6); break;
        case "1Y": start.setFullYear(end.getFullYear() - 1); break;
        case "5Y": start.setFullYear(end.getFullYear() - 5); break;
        case "10Y": start.setFullYear(end.getFullYear() - 10); break;
        case "20Y": start.setFullYear(end.getFullYear() - 20); break;
      }
      setStartDate(start.toISOString().split('T')[0]);
      setEndDate(end.toISOString().split('T')[0]);
    }
  };

  const handleRun = () => {
    onRun({
      period,
      startDate: period === "custom" ? startDate : undefined,
      endDate: period === "custom" ? endDate : undefined,
      initialCapital,
      commissionPct,
      slippagePct,
    });
  };

  return (
    <div className="w-full h-full flex flex-col lg:flex-row bg-[#0a0a0a] animate-in fade-in duration-500">
      
      {/* =========================================================
          Left Column: Functional Inputs (Simulation Parameters)
          ========================================================= */}
      <div className="flex-1 flex flex-col border-r border-white/5 overflow-y-auto">
        <div className="flex-none px-6 pt-4 lg:px-10 lg:pt-5 pb-6">
          <h3 className="text-lg font-black text-[#dfdfdf] tracking-tight">백테스트 & 성과 분석</h3>
          <p className="text-[11px] text-[#a0a0a0] mt-0.5 font-medium">
            설정한 전략을 과거 데이터를 바탕으로 시뮬레이션하고 성과를 검증합니다.
          </p>
        </div>
        
        {/* Step 1 + Step 2: 2컬럼 */}
        <div className="flex flex-row divide-x divide-white/5 flex-1">
          {/* Step 1: Period */}
          <div className="flex-1 px-6 py-3 lg:px-10 lg:py-4 flex flex-col">
            <div className="flex flex-col mb-1.5">
              <span className="text-[10px] font-bold text-main-blue uppercase tracking-widest mb-0.5">Step 1</span>
              <h2 className="text-base font-black text-[#dfdfdf] tracking-tight">테스트 기간 설정</h2>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2">
                {periods.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handlePeriodChange(p.id)}
                    className={`py-2 rounded-lg text-xs font-bold transition-all border ${
                      period === p.id
                        ? "bg-main-blue border-main-blue text-white shadow-[0_0_10px_rgba(59,134,247,0.2)]"
                        : "bg-[#111] border-white/5 text-[#a0a0a0] hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              {period === "custom" && (
                <div className="flex gap-3 animate-in fade-in slide-in-from-top-1 duration-200 bg-[#111] p-3 rounded-xl border border-white/5">
                  <div className="flex-1 space-y-1">
                    <label className="text-[10px] font-black text-[#606060] uppercase tracking-widest pl-1">시작일</label>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="bg-[#0a0a0a] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-bold w-full outline-none focus:border-main-blue transition-all"
                    />
                  </div>
                  <div className="flex-1 space-y-1">
                    <label className="text-[10px] font-black text-[#606060] uppercase tracking-widest pl-1">종료일</label>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="bg-[#0a0a0a] border border-white/10 rounded-lg px-3 py-2 text-xs text-white font-bold w-full outline-none focus:border-main-blue transition-all"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Step 2: Capital & Costs */}
          <div className="flex-1 px-6 py-3 lg:px-10 lg:py-4 flex flex-col">
            <div className="flex flex-col mb-1.5">
              <span className="text-[10px] font-bold text-main-blue uppercase tracking-widest mb-0.5">Step 2</span>
              <h2 className="text-base font-black text-[#dfdfdf] tracking-tight">초기 자본 및 거래 비용</h2>
            </div>

            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-[10px] font-black text-[#a0a0a0] uppercase tracking-widest pl-1">초기 자본금</label>
                <div className="bg-[#111] border border-white/5 rounded-xl px-4 py-2 group hover:border-white/10 focus-within:border-main-blue transition-all relative overflow-hidden">
                  <div className="absolute inset-y-0 left-0 w-1 bg-main-blue opacity-0 group-focus-within:opacity-100 transition-opacity" />
                  <div className="flex items-center justify-between">
                    <input
                      type="text"
                      value={initialCapital.toLocaleString()}
                      onChange={(e) => {
                        const val = Number(e.target.value.replace(/,/g, ''));
                        if (!isNaN(val)) setInitialCapital(val);
                      }}
                      className="w-full bg-transparent border-none p-0 text-white font-black text-lg outline-none"
                    />
                    <span className="text-[#606060] font-black text-sm ml-3 tracking-widest">KRW</span>
                  </div>
                  <p className="text-[9px] font-bold text-main-blue mt-0.5 text-right">{formatKoreanUnit(initialCapital)}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] font-black text-[#a0a0a0] uppercase tracking-widest pl-1">수수료</label>
                  <div className="flex items-center bg-[#111] border border-white/5 rounded-xl px-4 py-2 group hover:border-white/10 focus-within:border-white transition-all">
                    <input
                      type="number"
                      step="0.001"
                      value={commissionPct}
                      onChange={(e) => setCommissionPct(Number(e.target.value))}
                      className="w-full bg-transparent border-none p-0 text-base text-white font-black outline-none font-mono"
                    />
                    <span className="text-xs text-[#606060] font-black ml-2">%</span>
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] font-black text-[#a0a0a0] uppercase tracking-widest pl-1">슬리피지</label>
                  <div className="flex items-center bg-[#111] border border-white/5 rounded-xl px-4 py-2 group hover:border-white/10 focus-within:border-white transition-all">
                    <input
                      type="number"
                      step="0.01"
                      value={slippagePct}
                      onChange={(e) => setSlippagePct(Number(e.target.value))}
                      className="w-full bg-transparent border-none p-0 text-base text-white font-black outline-none font-mono"
                    />
                    <span className="text-xs text-[#606060] font-black ml-2">%</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* =========================================================
          Right Column: Strategy Snapshot (Bento Grid)
          ========================================================= */}
      <div className="w-full lg:w-[420px] xl:w-[460px] bg-[#141414] flex flex-col overflow-y-auto shrink-0 border-l border-white/5">
        <div className="p-4 lg:p-6 flex-1 flex flex-col relative">
          <div className="absolute top-0 right-0 w-64 h-64 bg-main-blue/5 rounded-full blur-[80px] pointer-events-none" />
          
          <div className="mb-6 relative z-10">
            <h3 className="text-2xl font-black text-white uppercase tracking-tighter">전략 요약</h3>
          </div>

          {/* Redesigned Summary Content */}
          <div className="space-y-6 relative z-10">
            
            {/* Universe */}
            <div>
              <div className="mb-3">
                <span className="text-base font-black text-white/40 uppercase tracking-widest">유니버스 설정</span>
              </div>
              <div className="pl-8 space-y-4">
                <div className="flex flex-col">
                  <span className="text-xs font-black text-white/30 uppercase tracking-[0.1em] mb-1.5">전략 이름</span>
                  <span className="text-2xl font-black text-white tracking-tight leading-tight">{summary.strategyName || "이름 없는 전략"}</span>
                </div>

                <div className="flex flex-col">
                  <span className="text-xs font-black text-white/30 uppercase tracking-[0.1em] mb-1.5">선택된 시장</span>
                  <span className="text-xl font-black text-white/80 tracking-tight">{summary.universeName}</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="flex flex-col">
                    <span className="text-xs font-black text-white/30 uppercase tracking-[0.1em] mb-1.5">시가총액 범위</span>
                    <span className="text-white text-sm font-bold border border-white/10 px-3 py-1 rounded-md w-fit">
                      {(() => {
                        const range = summary.universeSettings?.marketCapRange || [0, 50];
                        if (range[0] === 0 && range[1] === 50) return "대형주 (상위 50%)";
                        if (range[0] === 50 && range[1] === 80) return "중형주 (50-80%)";
                        if (range[0] === 80 && range[1] === 100) return "소형주 (80-100%)";
                        return `상위 ${range[0]}% - ${range[1]}%`;
                      })()}
                    </span>
                  </div>

                  <div className="flex flex-col">
                    <span className="text-xs font-black text-white/30 uppercase tracking-[0.1em] mb-1.5">최소 거래대금</span>
                    <span className="text-white text-sm font-bold border border-white/10 px-3 py-1 rounded-md w-fit">
                      {summary.universeSettings?.minTradingVolume === 0 
                        ? "제한 없음" 
                        : `${summary.universeSettings?.minTradingVolume}억원 이상`}
                    </span>
                  </div>
                </div>

                {summary.universeSettings?.selectedSectors && summary.universeSettings.selectedSectors.length > 0 && (
                  <div className="flex flex-col">
                    <span className="text-xs font-black text-white/30 uppercase tracking-[0.1em] mb-1.5">섹터 필터</span>
                    <div className="flex flex-wrap gap-2">
                      {summary.universeSettings.selectedSectors.map((sector, i) => (
                        <span key={i} className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                          {sector}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {(() => {
                  const exclusions = [
                    summary.universeSettings?.excludeLossMaking && "적자 기업",
                    summary.universeSettings?.excludeCapitalImpaired && "자본 잠식",
                    summary.universeSettings?.excludeAdministrative && "관리 종목",
                    summary.universeSettings?.excludePreferred && "우선주",
                    summary.universeSettings?.excludeETF_ETN && "ETF/ETN",
                    summary.universeSettings?.excludeSPAC && "SPAC",
                    summary.universeSettings?.excludeREITs && "리츠",
                    summary.universeSettings?.excludeInvestmentWarning && "투자 경고",
                    summary.universeSettings?.excludeDelistingPending && "상장 폐지 예정",
                    summary.universeSettings?.excludeForeignStock && "외국주",
                    summary.universeSettings?.excludePennyStocks && "동전주",
                    summary.universeSettings?.excludeNewListings && "신규 상장",
                    summary.universeSettings?.excludeHighVolatility && "급변동 종목",
                  ].filter(Boolean);

                  if (exclusions.length === 0) return null;

                  return (
                    <div className="flex flex-col">
                      <span className="text-xs font-black text-white/30 uppercase tracking-[0.1em] mb-1.5">제외 대상</span>
                      <div className="flex flex-wrap gap-2">
                        {exclusions.map((ex, i) => (
                          <span key={i} className="text-white text-[10px] font-bold border border-white/10 px-2 py-0.5 rounded opacity-60">
                            {ex}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>

            {/* Trading Logic */}
            <div>
              <div className="mb-4">
                <span className="text-base font-black text-white/40 uppercase tracking-widest">매매 로직 블록</span>
              </div>
              <div className="flex flex-col pl-8 gap-4">
                <div className="space-y-2">

                  <div className="flex flex-wrap gap-2">
                    {summary.blockNames.length > 0 ? (
                      summary.blockNames.map((name, idx) => (
                        <span key={idx} className="px-3.5 py-1.5 border-2 border-purple-500/30 bg-purple-500/10 text-purple-400 text-sm font-black rounded-lg">
                          {name}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs font-medium text-white/30 italic">설정된 조건 없음</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Position Sizing */}
            <div>
              <div className="mb-3">
                <span className="text-base font-black text-white/40 uppercase tracking-widest">포지션/비중</span>
              </div>
              <div className="pl-8 grid grid-cols-1 sm:grid-cols-2 gap-y-4 gap-x-8">
                <div className="flex flex-col">
                  <span className="text-xs font-black text-white/30 uppercase tracking-widest mb-1">최대 보유 종목</span>
                  <span className="text-xl font-black text-white">
                    {summary.riskSettings.skip_position_setting ? 'OFF' : `${summary.riskSettings.maxPositions}개`}
                  </span>
                </div>
                
                <div className="flex flex-col">
                  <span className="text-xs font-black text-white/30 uppercase tracking-widest mb-1">배분 방식</span>
                  <span className={`${summary.riskSettings.skip_position_setting ? 'text-xl font-black' : 'text-sm font-bold'} text-white`}>
                    {summary.riskSettings.skip_position_setting 
                      ? 'OFF'
                      : (summary.riskSettings.allocationType === 'equal' 
                        ? '동일 비중' 
                        : `고정 비중 (${summary.riskSettings.allocationValue}%)`)}
                  </span>
                </div>

                <div className="flex flex-col">
                  <span className="text-xs font-black text-white/30 uppercase tracking-widest mb-1">체결 시점 선택</span>
                  <span className={`${summary.riskSettings.skip_position_setting ? 'text-xl font-black' : 'text-sm font-bold'} text-white`}>
                    {summary.riskSettings.skip_position_setting 
                      ? 'OFF'
                      : (summary.riskSettings.executionTiming === 'next_open' ? '익일 시가' : '당일 종가')}
                  </span>
                </div>

                <div className="flex flex-col">
                  <span className="text-xs font-black text-white/30 uppercase tracking-widest mb-1">리밸런싱 설정</span>
                  <span className={`${summary.riskSettings.skip_position_setting ? 'text-xl font-black' : 'text-sm font-bold'} text-white`}>
                    {summary.riskSettings.skip_position_setting 
                      ? 'OFF'
                      : getRebalancingLabel(summary.riskSettings.rebalancingPeriod)}
                  </span>
                </div>
              </div>
            </div>

            {/* Risk Management */}
            <div>
              <div className="mb-4">
                <span className="text-base font-black text-white/40 uppercase tracking-widest">리스크 관리</span>
              </div>
              
              <div className="pl-8 space-y-6">
                {summary.riskManagement?.skip_risk_management ? (
                  <span className="text-sm font-medium text-white/30 italic">리스크 관리 하지 않음</span>
                ) : (
                  <>
                    {/* Category 1: Capital */}
                    <div className="space-y-3">
                      <span className="text-xs font-black text-white/30 uppercase tracking-[0.1em]">자금 관리</span>
                      <div className="flex flex-wrap gap-2">
                        {summary.riskManagement?.position_size_pct !== undefined && (
                          <span className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                            포지션 {summary.riskManagement.position_size_pct}%
                          </span>
                        )}
                        {summary.riskManagement?.liquidity_limit_pct !== undefined && (
                          <span className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                            유동성 {summary.riskManagement.liquidity_limit_pct}%
                          </span>
                        )}
                        {summary.riskManagement?.min_cash_reserve_pct !== undefined && (
                          <span className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                            현금 {summary.riskManagement.min_cash_reserve_pct}%
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Category 2: Price Exit */}
                    <div className="space-y-3">
                      <span className="text-xs font-black text-white/30 uppercase tracking-[0.1em]">청산 리스크</span>
                      <div className="flex flex-wrap gap-2">
                        {summary.riskManagement?.stop_loss_pct ? (
                          <span className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                            손절 -{summary.riskManagement.stop_loss_pct}%
                          </span>
                        ) : null}
                        {summary.riskManagement?.take_profit_pct ? (
                          <span className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                            익절 +{summary.riskManagement.take_profit_pct}%
                          </span>
                        ) : null}
                        {summary.riskManagement?.trailing_stop_pct !== undefined ? (
                          <span className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                            트레일링 스탑 {summary.riskManagement.trailing_stop_pct}%
                          </span>
                        ) : null}
                      </div>
                    </div>

                    {/* Category 3: Portfolio Control */}
                    <div className="space-y-3">
                      <span className="text-xs font-black text-white/30 uppercase tracking-[0.1em]">포트폴리오 제어</span>
                      <div className="flex flex-wrap gap-2">
                        {summary.riskManagement?.max_daily_loss_pct !== undefined && (
                          <span className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                            일일 손실 {summary.riskManagement.max_daily_loss_pct}%
                          </span>
                        )}
                        {summary.riskManagement?.max_mdd_limit_pct !== undefined && (
                          <span className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                            MDD 제한 {summary.riskManagement.max_mdd_limit_pct}%
                          </span>
                        )}
                        {summary.riskManagement?.max_total_exposure_pct !== undefined && (
                          <span className="text-white text-xs font-bold border border-white/10 px-3 py-1 rounded-md">
                            총 노출 {summary.riskManagement.max_total_exposure_pct}%
                          </span>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

          {/* Backtest Action at bottom of summary */}
          <div className="mt-10 pt-8 border-t border-white/10 relative z-10 pb-4">
            <button
              onClick={handleRun}
              disabled={isRunning}
              className="w-full relative overflow-hidden group py-4 px-8 bg-main-blue hover:bg-blue-500 text-white rounded-xl text-base font-black transition-all flex items-center justify-center gap-3 shadow-[0_0_20px_rgba(59,134,247,0.3)] hover:shadow-[0_0_30px_rgba(59,134,247,0.5)] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isRunning ? (
                <>
                  <ArrowsClockwise className="w-6 h-6 animate-spin" />
                  <span>시뮬레이션 분석 중...</span>
                </>
              ) : (
                <>
                  <PlayCircle className="w-6 h-6" />
                  <span>백테스트 시작하기</span>
                </>
              )}
            </button>
            <p className="text-[10px] text-white/30 mt-4 text-center leading-relaxed">
              운용 결과는 과거 데이터를 기반으로 하며 미래 수익을 보장하지 않습니다.
            </p>
          </div>

          </div>
        </div>
      </div>
    </div>
  );
}
