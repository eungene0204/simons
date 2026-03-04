"use client";

import React, { useState } from "react";
import {
  Briefcase,
  ChartPie,
  Clock,
  ArrowsClockwise,
  ChartBar,
  ArrowRight,
  ArrowLeft,
} from "phosphor-react";

import { RiskManagement } from "@/types/strategy";

interface Step3PositionProps {
  riskManagement: RiskManagement;
  setRiskManagement: (risk: RiskManagement) => void;
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
  riskManagement,
  setRiskManagement,
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

  const skip_pos = riskManagement.skip_position_setting;

  const getRebalancingLabel = () => {
    if (rebalancingPeriod === "none") return "안함";
    if (rebalancingPeriod === "daily") return "매일";
    if (rebalancingPeriod === "weekly") return "매주";
    if (rebalancingPeriod === "monthly") return "매월";
    if (rebalancingPeriod.startsWith("custom:")) {
      const parts = rebalancingPeriod.split(":");
      const unit = parts[2] === "day" ? "일" : parts[2] === "week" ? "주" : "달";
      return `${parts[1]}${unit}마다`;
    }
    return "안함";
  };

  return (
    <div className="flex-1 w-full bg-[#0a0a0a] min-h-screen text-white flex justify-center relative">
      
      <div className="flex w-full h-full">
        
        {/* Left Main Content */}
        <div className="flex-1 flex flex-col overflow-y-auto">
          
          <div className="w-full px-8 pt-8 lg:px-12">
            {/* Header section */}
            <div className="mb-14 flex justify-between items-start">
              <div>
                <h1 className="text-3xl font-bold tracking-tight text-white mb-2">
                  포지션 &amp; 비중 설정
                </h1>
                <p className="text-sm font-medium text-white/50 mb-12">
                  자산 배분 방식과 매매 체결 시점, 리밸런싱 주기를 구성합니다.
                </p>
              </div>

              {/* Skip Setting Toggle */}
              <div
                className="flex items-center gap-3 bg-[#111] px-5 py-3 rounded-2xl border border-white/5 hover:border-white/10 transition-all cursor-pointer group"
                onClick={() => setRiskManagement({ ...riskManagement, skip_position_setting: !skip_pos })}
              >
                <div className={`w-10 h-6 rounded-full transition-colors relative ${skip_pos ? 'bg-blue-500' : 'bg-[#2a2a2a]'}`}>
                  <div className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${skip_pos ? 'translate-x-4' : ''}`} />
                </div>
                <span className={`text-sm font-bold tracking-tight transition-colors ${skip_pos ? 'text-white' : 'text-white/40'}`}>
                  포지션/비중 설정 안 함
                </span>
              </div>
            </div>

            <div className={`flex flex-col gap-6 transition-all duration-500 ${skip_pos ? 'opacity-30 grayscale pointer-events-none' : ''}`}>
              
              {/* Panels 1 & 2: 2-Column Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                {/* Panel 1: 포트폴리오 구성 */}
                <div className="flex flex-col">
                  <div className="flex items-center gap-2 mb-4">
                    <Briefcase className="w-5 h-5 text-blue-500" />
                    <h2 className="text-lg font-bold text-blue-500">포트폴리오 구성</h2>
                  </div>
                  
                  <div className="bg-[#111] rounded-xl p-6 flex-1 flex flex-col">
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-6">
                        <span className="text-sm font-medium text-white/70">최대 보유 종목 수</span>
                        <span className="text-sm font-bold text-blue-500">{maxPositions}개</span>
                      </div>
                      <div className="relative px-2">
                        <input
                          type="range"
                          min="1"
                          max="100"
                          value={maxPositions}
                          onChange={(e) => setMaxPositions(Number(e.target.value))}
                          className="w-full h-1.5 bg-[#0a0a0a] rounded-full appearance-none cursor-pointer accent-blue-500"
                        />
                        <div className="flex justify-between items-center mt-3 text-[9px] font-bold text-white/30 uppercase tracking-wider">
                          <span>1개</span>
                          <span>50개</span>
                          <span>100개</span>
                        </div>
                      </div>
                    </div>
                    <p className="text-[11px] text-white/40 font-medium leading-relaxed mt-4">
                      동시에 최대 <span className="text-white font-bold">{maxPositions}개</span>의 종목까지 보유합니다.
                    </p>
                  </div>
                </div>

                {/* Panel 2: 비중 배분 정책 */}
                <div className="flex flex-col">
                  <div className="flex items-center gap-2 mb-4">
                    <ChartPie className="w-5 h-5 text-blue-500" />
                    <h2 className="text-lg font-bold text-blue-500">비중 배분 정책</h2>
                  </div>
                  
                  <div className="bg-[#111] rounded-xl p-6 flex-1 flex flex-col">
                    <div className="mb-6">
                      <div className="flex items-center justify-between mb-4">
                        <span className="text-sm font-medium text-white/70">배분 방식</span>
                      </div>
                      <div className="flex gap-2 p-1 bg-[#0a0a0a] rounded-lg">
                        <button
                          onClick={() => setAllocationType("equal")}
                          className={`flex-1 py-2.5 text-sm font-bold rounded-md transition-all ${
                            allocationType === "equal"
                              ? "bg-blue-500 text-white shadow-[0_0_15px_rgba(59,130,246,0.2)]"
                              : "text-white/50 hover:text-white hover:bg-white/5"
                          }`}
                        >
                          동일 비중
                        </button>
                        <button
                          onClick={() => setAllocationType("fixed_pct")}
                          className={`flex-1 py-2.5 text-sm font-bold rounded-md transition-all ${
                            allocationType === "fixed_pct"
                              ? "bg-blue-500 text-white shadow-[0_0_15px_rgba(59,130,246,0.2)]"
                              : "text-white/50 hover:text-white hover:bg-white/5"
                          }`}
                        >
                          고정 비중 (%)
                        </button>
                      </div>
                    </div>

                    <div className="flex-1 flex flex-col justify-end">
                      {allocationType === "fixed_pct" ? (
                        <div className="animate-in fade-in duration-300">
                          <div className="flex items-center justify-between mb-4">
                            <span className="text-sm font-medium text-white/70">종목당 투입 비중</span>
                            <span className="text-sm font-bold text-blue-500">{allocationValue}%</span>
                          </div>
                          <div className="relative px-2">
                            <input
                              type="range"
                              min="1"
                              max="100"
                              value={allocationValue}
                              onChange={(e) => setAllocationValue(Number(e.target.value))}
                              className="w-full h-1.5 bg-[#0a0a0a] rounded-full appearance-none cursor-pointer accent-blue-500"
                            />
                            <div className="flex justify-between items-center mt-3 text-[9px] font-bold text-white/30 uppercase tracking-wider">
                              <span>1%</span>
                              <span>50%</span>
                              <span>100%</span>
                            </div>
                          </div>
                          <p className="text-[11px] text-white/40 font-medium leading-relaxed mt-4">
                            각 거래마다 가용 자산의 <span className="text-white font-bold">{allocationValue}%</span>를 고정적으로 투자합니다.
                          </p>
                        </div>
                      ) : (
                        <div className="animate-in fade-in duration-300">
                          <p className="text-[11px] text-white/40 font-medium leading-relaxed mt-2">
                            종목당 목표 비중: <span className="text-white font-bold">약 {Number(100 / maxPositions).toFixed(1)}%</span> (총 {maxPositions}개 균등 배분)
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Panels 3 & 4: 2-Column Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-16">
                
                {/* Panel 3: 체결 시점 선택 */}
                <div className="flex flex-col">
                  <div className="flex items-center gap-2 mb-4">
                    <Clock className="w-5 h-5 text-blue-500" />
                    <h2 className="text-lg font-bold text-blue-500">체결 시점 선택</h2>
                  </div>
                  
                  <div className="bg-[#111] rounded-xl p-6 relative flex-1 flex flex-col">
                    <div className="flex flex-col gap-4 flex-1 justify-center">
                      {[
                        {
                          id: "next_open" as const,
                          name: "익일 시가 (Next Open)",
                          desc: "신호 발생 다음 영업일 아침 시가에 즉시 체결합니다. 가장 일반적인 추천 방식입니다.",
                        },
                        {
                          id: "current_close" as const,
                          name: "당일 종가 (Direct Close)",
                          desc: "신호 발생 당일 장 마감 직전 종가로 체결합니다. 빠른 대응이 필요할 때 사용합니다.",
                        }
                      ].map((opt) => (
                        <div
                          key={opt.id}
                          onClick={() => setExecutionTiming(opt.id)}
                          className={`p-5 rounded-xl cursor-pointer transition-all border ${
                            executionTiming === opt.id
                              ? "bg-[#161616] border-blue-500/50"
                              : "bg-[#0a0a0a] border-transparent hover:border-white/10"
                          }`}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <h3 className={`text-sm font-bold ${executionTiming === opt.id ? "text-white" : "text-white/60"}`}>{opt.name}</h3>
                            <div className={`w-3 h-3 rounded-full border-2 transition-all ${executionTiming === opt.id ? 'border-blue-500 bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]' : 'border-white/20 bg-transparent'}`} />
                          </div>
                          <p className="text-[11px] text-white/40 font-medium leading-relaxed">{opt.desc}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Panel 4: 리밸런싱 설정 */}
                <div className="flex flex-col">
                  <div className="flex items-center gap-2 mb-4">
                    <ArrowsClockwise className="w-5 h-5 text-blue-500" />
                    <h2 className="text-lg font-bold text-blue-500">리밸런싱 설정</h2>
                  </div>
                  
                  <div className="bg-[#111] rounded-xl p-6 relative flex-1 flex flex-col">
                    <div className="flex flex-wrap gap-2 p-1 bg-[#0a0a0a] rounded-lg mb-6 w-full">
                      {[
                        { id: "none", label: "안함" },
                        { id: "daily", label: "매일" },
                        { id: "weekly", label: "매주" },
                        { id: "monthly", label: "매월" },
                        { id: "custom", label: "직접 입력" },
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
                          className={`flex-1 py-2.5 px-3 text-sm font-bold rounded-md transition-all whitespace-nowrap ${
                            (period.id === "custom" ? rebalancingPeriod.startsWith("custom:") : rebalancingPeriod === period.id)
                              ? "bg-blue-500 text-white shadow-[0_0_15px_rgba(59,130,246,0.2)]"
                              : "text-white/50 hover:text-white hover:bg-white/5"
                          }`}
                        >
                          {period.label}
                        </button>
                      ))}
                    </div>

                    <div className="flex-1 flex flex-col justify-end">
                      {rebalancingPeriod.startsWith("custom:") && (
                        <div className="flex items-center gap-3 animate-in fade-in slide-in-from-top-2 duration-300 w-full mb-4">
                          <div className="flex-1">
                            <input
                              type="number"
                              min="1"
                              value={rebalancingPeriod.split(":")[1]}
                              onChange={(e) => {
                                const parts = rebalancingPeriod.split(":");
                                setRebalancingPeriod(`custom:${e.target.value}:${parts[2]}`);
                              }}
                              className="w-full bg-[#0a0a0a] border border-white/10 rounded-lg px-4 py-2.5 text-white font-bold text-sm outline-none focus:border-blue-500/50"
                            />
                          </div>
                          <select
                            value={rebalancingPeriod.split(":")[2]}
                            onChange={(e) => {
                              const parts = rebalancingPeriod.split(":");
                              setRebalancingPeriod(`custom:${parts[1]}:${e.target.value}`);
                            }}
                            className="bg-[#0a0a0a] border border-white/10 rounded-lg px-4 py-2.5 text-white font-bold text-sm outline-none focus:border-blue-500/50 appearance-none cursor-pointer w-24 text-center"
                          >
                            <option value="day">일</option>
                            <option value="week">주</option>
                            <option value="month">월</option>
                          </select>
                        </div>
                      )}

                      <p className="text-[11px] text-white/40 font-medium leading-relaxed">
                        {rebalancingPeriod === "none"
                          ? "포지션 진입 후 별도의 재조정 없이 신호에 따라 매도될 때까지 유지합니다."
                          : "설정된 주기마다 전체 포트폴리오 비중을 배분 정책에 맞춰 재조정합니다."}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

            </div>

            {/* Action Buttons at the bottom of the main content */}
            <div className="flex items-center justify-between border-t border-white/5 pt-8 mb-12">
              <button 
                onClick={onPrev}
                className="py-3 px-6 rounded-lg bg-transparent border border-white/10 hover:border-white/30 text-sm font-bold text-white transition-all flex items-center gap-2"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>이전</span>
              </button>
              
              <button 
                onClick={onNext}
                className="py-3 px-8 rounded-lg bg-blue-500 hover:bg-blue-400 active:bg-blue-600 text-sm font-bold text-white transition-all shadow-[0_0_15px_rgba(59,130,246,0.3)] flex items-center gap-2"
              >
                <span>리스크 관리</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>

          </div>
        </div>

        {/* Right Fixed Sidebar (Summary) */}
        <div className="hidden lg:block w-[320px] xl:w-[380px] bg-[#141414] border-l border-white/5 h-full overflow-y-auto shrink-0 p-8">
          
          <div className="flex items-center gap-3 mb-10">
            <ChartBar className="w-6 h-6 text-blue-500" />
            <h3 className="text-base font-black text-white/60 uppercase tracking-widest">포지션 설정 요약</h3>
          </div>

          <div className={`space-y-8 transition-opacity duration-500 ${skip_pos ? 'opacity-30' : 'opacity-100'}`}>
            
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Briefcase className="w-5 h-5 text-blue-500" />
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">최대 종목 수</span>
              </div>
              <span className="text-2xl font-black text-white block pl-8 tracking-tight">
                {skip_pos ? "OFF" : `${maxPositions}개`}
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-3">
                <ChartPie className="w-5 h-5 text-blue-500" />
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">배분 방식</span>
              </div>
              <span className="text-2xl font-black text-white block pl-8 tracking-tight">
                {skip_pos ? "OFF" : (allocationType === "equal" ? "동일 비중" : `고정 비중 (${allocationValue}%)`)}
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-3">
                <Clock className="w-5 h-5 text-blue-500" />
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">체결 시점</span>
              </div>
              <span className="text-2xl font-black text-white block pl-8 tracking-tight">
                {skip_pos ? "OFF" : (executionTiming === "next_open" ? "익일 시가" : "당일 종가")}
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-3">
                <ArrowsClockwise className="w-5 h-5 text-blue-500" />
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">리밸런싱</span>
              </div>
              <span className="text-2xl font-black text-white block pl-8 tracking-tight">
                {skip_pos ? "OFF" : getRebalancingLabel()}
              </span>
            </div>

          </div>

          {skip_pos && (
            <div className="mt-8 p-4 bg-white/5 rounded-xl border border-white/10">
              <p className="text-xs text-blue-400 font-bold mb-1">안내</p>
              <p className="text-[11px] text-white/40 leading-relaxed">
                포지션 및 비중 설정을 건너뜁니다. 모델 자체의 시그널 크기 등에 의존하거나 기본 설정이 적용됩니다.
              </p>
            </div>
          )}

        </div>
      </div>

    </div>
  );
}
