"use client";

import { Dispatch, SetStateAction } from "react";
import { ShieldCheckIcon, ArrowLeftIcon, ArrowRightIcon } from "@heroicons/react/24/outline";
import { RiskManagement } from "@/types/strategy";
import RiskManagementEditor from "../RiskManagementEditor";

interface Step4RiskProps {
  riskManagement: RiskManagement;
  setRiskManagement: (risk: RiskManagement) => void;
  onNext: () => void;
  onPrev: () => void;
}

export default function Step4Risk({
  riskManagement,
  setRiskManagement,
  onNext,
  onPrev,
}: Step4RiskProps) {
  return (
    <div className="flex flex-col min-h-full">
      <div className="space-y-6 px-0 pt-8 pb-0">
        <div className="flex items-center justify-between mb-6 px-8">
          <div>
            <h3 className="text-xl font-black text-[#dfdfdf] tracking-tight">리스크 관리</h3>
            <p className="text-sm text-[#a0a0a0] mt-1 font-medium">
              손절매, 익절매 등 자산 보호를 위한 규칙을 설정합니다.
            </p>
          </div>
        </div>
        <div className="bg-[#0f0f0f] rounded-3xl border border-gray-800/50 p-8 min-h-[600px] max-w-6xl mx-8 shadow-2xl overflow-hidden relative">
          <div className="flex flex-col lg:flex-row gap-12">
            {/* Left: Introduction & Summary */}
            <div className="lg:w-1/3 xl:w-1/4">
              <div className="sticky top-0">
                <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center border border-white/20 mb-6">
                  <ShieldCheckIcon className="w-8 h-8 text-white" />
                </div>
                <h4 className="text-xl font-black text-[#dfdfdf] mb-4 tracking-tight">리스크 엔진 설정</h4>
                <p className="text-sm text-[#a0a0a0] leading-relaxed mb-8">
                  전문적인 퀀트 전략은 수익만큼 리스크 관리가 중요합니다. 자금 배분 원칙과 손실 방어 규칙을 세밀하게 구성하세요.
                </p>
                
                <div className="space-y-4 pt-6 border-t border-gray-800/50">
                  <div className="flex items-center gap-3 text-xs text-[#a0a0a0]">
                    <div className="w-1.5 h-1.5 rounded-full bg-white/50" />
                    <span>자본금 대비 투자 비율 자동 계산</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-[#a0a0a0]">
                    <div className="w-1.5 h-1.5 rounded-full bg-white/30" />
                    <span>실시간 변동성 기반 익절/손절</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-[#a0a0a0]">
                    <div className="w-1.5 h-1.5 rounded-full bg-white/10" />
                    <span>섹터 집중 위험 방어 엔진 작동</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right: Detailed Settings */}
            <div className="flex-1">
              <div className="bg-[#0a0a0a]/50 rounded-2xl border border-gray-800/80 p-8">
                <RiskManagementEditor 
                  riskManagement={riskManagement} 
                  onChange={setRiskManagement} 
                />
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
                <ShieldCheckIcon className="w-8 h-8 text-white" />
              </div>
              <div className="space-y-1">
                <h4 className="text-xl font-black text-[#dfdfdf] tracking-tight uppercase">리스크 관리 요약</h4>
              </div>
            </div>
            
            <div className="h-12 w-px bg-white/10" />
            
            <div className="flex gap-12">
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">손절매</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {riskManagement.stop_loss_pct ? `-${riskManagement.stop_loss_pct}%` : "OFF"}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">익절매</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {riskManagement.take_profit_pct ? `+${riskManagement.take_profit_pct}%` : "OFF"}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">트레일링 스탑</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {riskManagement.trailing_stop_pct ? "ON" : "OFF"}
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
              다음: 백테스트 <ArrowRightIcon className="w-6 h-6 group-hover:translate-x-2 transition-transform duration-500 text-white" />
            </button>
          </div>
        </div>
      </div>

    </div>
  );
}
