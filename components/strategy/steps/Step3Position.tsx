"use client";

import { 
  BriefcaseIcon, 
  ChartPieIcon, 
  ClockIcon, 
  ArrowPathIcon, 
  ArrowLeftIcon, 
  ArrowRightIcon 
} from "@heroicons/react/24/outline";

const EggIcon = ({ className }: { className?: string }) => (
  <svg 
    viewBox="0 0 24 24" 
    fill="none" 
    stroke="currentColor" 
    strokeWidth="2" 
    strokeLinecap="round" 
    strokeLinejoin="round" 
    className={className}
  >
    <path d="M12 22C16.9706 22 21 17.9706 21 13C21 7.47715 16.9706 2 12 2C7.02944 2 3 7.47715 3 13C3 17.9706 7.02944 22 12 22Z" />
  </svg>
);

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

interface Step3PositionProps {

  maxPositions: number;
  setMaxPositions: (val: number) => void;
  allocationType: "equal" | "fixed_pct";
  setAllocationType: (val: "equal" | "fixed_pct") => void;
  allocationValue: number;
  setAllocationValue: (val: number) => void;
  executionTiming: "next_open" | "current_close";
  setExecutionTiming: (val: "next_open" | "current_close") => void;
  rebalancingPeriod: string;
  setRebalancingPeriod: (val: string) => void;
  onNext: () => void;
  onPrev: () => void;
}

export default function Step3Position({

  maxPositions,
  setMaxPositions,
  allocationType,
  setAllocationType,
  allocationValue,
  setAllocationValue,
  executionTiming,
  setExecutionTiming,
  rebalancingPeriod,
  setRebalancingPeriod,
  onNext,
  onPrev,
}: Step3PositionProps) {
  return (
    <div className="flex flex-col min-h-full">
      <div className="px-8 pt-8 pb-0 max-w-[1440px] mx-auto w-full space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-xl font-black text-[#dfdfdf] tracking-tight">포지션 & 비중 설정</h3>
            <p className="text-sm text-[#a0a0a0] mt-1 font-medium">
              자산 배분 방식과 매매 체결 시점, 리밸런싱 주기를 구성합니다.
            </p>
          </div>
        </div>

        <div className="w-full grid grid-cols-1 lg:grid-cols-2 gap-4 pb-0 items-stretch">
          {/* Section 1: Capital & Max Positions */}
          <div className="bg-[#0f0f0f] rounded-3xl border border-gray-800/50 p-5 shadow-xl flex flex-col space-y-4">
            <div className="flex items-center gap-3.5 mb-2">
                <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center border border-white/20 shadow-inner">
                  <EggIcon className="w-5 h-5 text-gray-300" />
                </div>
                <div>
                  <h4 className="text-md font-black text-[#dfdfdf]">포트폴리오 구성</h4>
                  <p className="text-[11px] text-[#a0a0a0]">종목 수 및 분산 투자 범위를 설정합니다.</p>
                </div>
              </div>
              
              <div className="space-y-4 bg-[#0a0a0a]/40 p-5 rounded-2xl border border-gray-800/40 backdrop-blur-sm flex-1 min-h-[200px] flex flex-col justify-center">

              
              <div>
                <div className="flex justify-between items-end mb-3">
                  <label className="text-xs text-[#a0a0a0] font-black uppercase tracking-widest">최대 보유 종목 수</label>
                  <span className="text-lg font-black text-[#dfdfdf]">{maxPositions}<span className="text-xs ml-0.5 text-[#a0a0a0]">개</span></span>
                </div>
                <div className="flex items-center gap-4">
                  <input 
                    type="range" 
                    min="1" 
                    max="100" 
                    value={maxPositions}
                    onChange={(e) => setMaxPositions(Number(e.target.value))}
                    className="flex-1 h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-main-blue"
                  />
                </div>
                <p className="text-[11px] text-[#a0a0a0] mt-3 font-medium">동시에 최대 {maxPositions}개의 종목까지 매수합니다.</p>
              </div>
            </div>
          </div>

          {/* Section 2: Allocation Strategy */}
          <div className="bg-[#0f0f0f] rounded-3xl border border-gray-800/50 p-5 shadow-xl flex flex-col space-y-4">
            <div className="flex items-center gap-3.5 mb-2">
              <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center border border-white/20 shadow-inner">
                <ChartPieIcon className="w-5 h-5 text-white" />
              </div>
              <div>
                <h4 className="text-md font-black text-[#dfdfdf]">비중 배분 정책</h4>
                <p className="text-[11px] text-[#a0a0a0]">개별 종목당 자산 투입 비중을 결정합니다.</p>
              </div>
            </div>

            <div className="space-y-4 bg-[#0a0a0a]/40 p-5 rounded-2xl border border-gray-800/40 backdrop-blur-sm flex-1 flex flex-col min-h-[200px]">
              <div className="flex p-1 bg-[#0a0a0a] rounded-xl border border-gray-800">
                <button 
                  onClick={() => setAllocationType("equal")}
                  className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-all ${
                    allocationType === "equal" 
                      ? "bg-main-blue text-white shadow-lg shadow-main-blue/20" 
                      : "text-[#a0a0a0] hover:text-gray-300"
                  }`}
                >
                  동일 비중
                </button>
                <button 
                  onClick={() => setAllocationType("fixed_pct")}
                  className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-all ${
                    allocationType === "fixed_pct" 
                      ? "bg-main-blue text-white shadow-lg shadow-main-blue/20" 
                      : "text-[#a0a0a0] hover:text-gray-300"
                  }`}
                >
                  고정 비중 (%)
                </button>
              </div>

              <div className="flex-1">
                {allocationType === "fixed_pct" ? (
                  <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                      <div className="flex justify-between items-end mb-3">
                        <label className="text-xs text-[#a0a0a0] font-black uppercase tracking-widest">종목당 투입 비중</label>
                        <span className="text-lg font-black text-[#dfdfdf]">{allocationValue}<span className="text-xs ml-0.5 text-[#a0a0a0]">%</span></span>
                      </div>
                    <div className="flex items-center gap-4">
                      <input 
                        type="range" 
                        min="1" 
                        max="100" 
                        value={allocationValue}
                        onChange={(e) => setAllocationValue(Number(e.target.value))}
                        className="flex-1 h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-main-blue"
                      />
                    </div>
                    <p className="text-[11px] text-[#a0a0a0] mt-3 font-medium">거래 건마다 가용 자산의 {allocationValue}%를 고정적으로 투자합니다.</p>
                  </div>
                ) : null}
              </div>

              <div className="p-4 bg-white/5 border border-white/10 rounded-xl mt-auto">
                <p className="text-[11px] text-[#a0a0a0] leading-relaxed font-medium">
                  {allocationType === "equal" 
                    ? `💡 최대 보유 종목 수(${maxPositions}개)에 맞춰 모든 자산을 균등하게 배분합니다. 종목당 배정 목표는 약 ${Number(100/maxPositions).toFixed(1)}% 입니다.`
                    : "💡 각 거래마다 설정된 고정 비중만큼의 자산을 투입합니다."}
                </p>
              </div>
            </div>
          </div>

          {/* Section 3: Execution Timing */}
          <div className="bg-[#0f0f0f] rounded-3xl border border-gray-800/50 p-5 shadow-xl flex flex-col space-y-4">
            <div className="flex items-center gap-3.5 mb-2">
              <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center border border-white/20 shadow-inner">
                <ClockIcon className="w-5 h-5 text-white" />
              </div>
              <div>
                <h4 className="text-md font-black text-[#dfdfdf]">체결 시점 선택</h4>
                <p className="text-[11px] text-[#a0a0a0]">조건 충족 시 실제 주문이 나가는 타이밍입니다.</p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 bg-[#1a1a1a]/40 p-5 rounded-2xl border border-gray-800/40 backdrop-blur-sm flex-1 min-h-[200px]">
              <button 
                onClick={() => setExecutionTiming("next_open")}
                className={`px-5 py-4 rounded-xl border transition-all text-left flex items-start gap-4 ${
                  executionTiming === "next_open"
                    ? "bg-white/5 border-white/30 ring-1 ring-white/10"
                    : "bg-[#0a0a0a] border-gray-800 hover:border-gray-700"
                }`}
              >
                <div className={`w-2 h-2 rounded-full mt-1.5 ${executionTiming === "next_open" ? "bg-main-blue animate-pulse" : "bg-gray-700"}`} />
                <div>
                  <div className={`text-sm font-black mb-1 ${executionTiming === "next_open" ? "text-main-blue" : "text-[#a0a0a0]"}`}>익일 시가 (Next Open)</div>
                  <div className="text-[11px] text-[#a0a0a0] leading-tight">신호가 발생한 다음 영업일 아침 시가에 즉시 체결합니다. 가장 일반적인 방식입니다.</div>
                </div>
              </button>
              <button 
                onClick={() => setExecutionTiming("current_close")}
                className={`px-5 py-4 rounded-xl border transition-all text-left flex items-start gap-4 ${
                  executionTiming === "current_close"
                    ? "bg-white/5 border-white/30 ring-1 ring-white/10"
                    : "bg-[#0a0a0a] border-gray-800 hover:border-gray-700"
                }`}
              >
                <div className={`w-2 h-2 rounded-full mt-1.5 ${executionTiming === "current_close" ? "bg-main-blue animate-pulse" : "bg-gray-700"}`} />
                <div>
                  <div className={`text-sm font-black mb-1 ${executionTiming === "current_close" ? "text-main-blue" : "text-[#a0a0a0]"}`}>당일 종가 (Direct Close)</div>
                  <div className="text-[11px] text-[#a0a0a0] leading-tight">신호가 발생한 당일 장 마감 직전 종가로 체결합니다. 빠른 대응이 가능합니다.</div>
                </div>
              </button>
            </div>
          </div>

          {/* Section 4: Rebalancing */}
          <div className="bg-[#0f0f0f] rounded-3xl border border-gray-800/50 p-5 shadow-xl flex flex-col space-y-4">
            <div className="flex items-center gap-3.5 mb-2">
              <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center border border-white/20 shadow-inner">
                <ArrowPathIcon className="w-5 h-5 text-white" />
              </div>
              <div>
                <h4 className="text-md font-black text-[#dfdfdf]">리밸런싱 설정</h4>
                <p className="text-[11px] text-[#a0a0a0]">보유 종목의 비중을 정기적으로 재조정합니다.</p>
              </div>
            </div>

            <div className="bg-[#1a1a1a]/40 p-5 rounded-2xl border border-gray-800/40 backdrop-blur-sm flex-1 flex flex-col justify-between min-h-[200px]">
              <div>
                <div className="flex p-1 bg-[#0a0a0a] rounded-xl border border-gray-800 mb-5">
                  {[
                    { id: "none", label: "안함" },
                    { id: "daily", label: "매일" },
                    { id: "weekly", label: "매주" },
                    { id: "monthly", label: "매월" },
                    { id: "custom", label: "직접 입력" }
                  ].map((period) => (
                    <button
                      key={period.id}
                      onClick={() => {
                        if (period.id === "custom") {
                          setRebalancingPeriod("custom:2:week");
                        } else {
                          setRebalancingPeriod(period.id);
                        }
                      }}
                      className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-all ${
                        (period.id === "custom" ? rebalancingPeriod.startsWith("custom:") : rebalancingPeriod === period.id)
                          ? "bg-main-blue text-white shadow-lg shadow-main-blue/20"
                          : "text-[#a0a0a0] hover:text-gray-300"
                      }`}
                    >
                      {period.label}
                    </button>
                  ))}
                </div>

                {rebalancingPeriod.startsWith("custom:") && (
                  <div className="flex items-center gap-3 mb-5 animate-in fade-in slide-in-from-top-2 duration-300">
                    <div className="flex-1">
                      <input 
                        type="number" 
                        min="1"
                        value={rebalancingPeriod.split(":")[1]}
                        onChange={(e) => {
                          const parts = rebalancingPeriod.split(":");
                          setRebalancingPeriod(`custom:${e.target.value}:${parts[2]}`);
                        }}
                        className="w-full bg-[#0a0a0a] border border-gray-800 rounded-xl px-4 py-2 text-white font-black text-sm outline-none focus:border-white/50"
                      />
                    </div>
                    <select 
                      value={rebalancingPeriod.split(":")[2]}
                      onChange={(e) => {
                        const parts = rebalancingPeriod.split(":");
                        setRebalancingPeriod(`custom:${parts[1]}:${e.target.value}`);
                      }}
                      className="bg-[#0a0a0a] border border-gray-800 rounded-xl px-4 py-2 text-white font-black text-sm outline-none focus:border-white/50 appearance-none cursor-pointer"
                    >
                      <option value="day">일</option>
                      <option value="week">주</option>
                      <option value="month">월</option>
                    </select>
                  </div>
                )}
              </div>
              <div className="p-4 bg-white/5 border border-white/10 rounded-xl mt-auto">
                <p className="text-[11px] text-[#a0a0a0] leading-relaxed font-medium">
                  {rebalancingPeriod === "none" 
                    ? "💡 포지션 진입 시점의 비중을 그대로 유지하며 별도의 도중 조정을 하지 않습니다."
                    : rebalancingPeriod.startsWith("custom:")
                    ? `💡 설정하신 주기(${rebalancingPeriod.split(":")[1]}${rebalancingPeriod.split(":")[2] === "day" ? "일" : rebalancingPeriod.split(":")[2] === "week" ? "주" : "달"})마다 포트폴리오 비중을 배분 정책에 맞춰 다시 계산합니다.`
                    : `💡 정해진 주기(${rebalancingPeriod === "daily" ? "매일" : rebalancingPeriod === "weekly" ? "매주" : "매월"})마다 포트폴리오 비중을 배분 정책에 맞춰 다시 계산합니다.`}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="h-8" />
      </div>

      {/* macOS-style Bottom Toolbar / Status View */}
      <div className="sticky bottom-0 left-0 right-0 bg-[#0f0f0f] backdrop-blur-3xl px-8 py-5 z-50">
        <div className="max-w-full mx-auto flex items-center justify-between">
          <div className="flex items-center gap-12">
            <div className="flex items-center gap-6">
              <div className="w-16 h-16 bg-[rgb(59, 134, 247)] rounded-2xl flex items-center justify-center shadow-[0_0_40px_rgba(0,122,255,0.4)]">
                <EggIcon className="w-8 h-8 text-white" />
              </div>
              <div className="space-y-1">
                <h4 className="text-xl font-black text-[#dfdfdf] tracking-tight uppercase">자금 배분 요약</h4>
              </div>
            </div>
            
            <div className="h-12 w-px bg-white/10" />
            
            <div className="flex gap-12">
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">최대 종목 수</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">{maxPositions}개</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">배분 방식</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {allocationType === "equal" ? "동일 비중" : "고정 비중"}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">체결 시점</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {executionTiming === "next_open" ? "익일 시가" : "당일 종가"}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button 
              onClick={onPrev} 
              className="px-8 py-5 bg-white/5 text-white/40 rounded-2xl text-lg font-black hover:bg-white/10 hover:text-white transition-all flex items-center gap-4 active:scale-95"
            >
              <ArrowLeftIcon className="w-6 h-6" /> 이전
            </button>
            <button 
              onClick={onNext} 
              className="group px-12 py-5 bg-[#161616] text-white rounded-2xl text-lg font-black hover:bg-[#1f1f1f] transition-all flex items-center gap-4 shadow-[0_20px_40px_rgba(0,0,0,0.3)] border border-white/5 hover:border-white/10 hover:scale-105 active:scale-95"
            >
              리스크 관리 설정하기 <ArrowRightIcon className="w-6 h-6 group-hover:translate-x-2 transition-transform duration-500 text-white" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
