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
          <div className="flex items-center gap-3 bg-[#161616] px-5 py-3 rounded-2xl border border-white/5 hover:border-white/10 transition-all cursor-pointer group"
               onClick={() => setRiskManagement({...riskManagement, skip_risk_management: !riskManagement.skip_risk_management})}>
            <div className={`w-10 h-6 rounded-full transition-colors relative ${riskManagement.skip_risk_management ? 'bg-main-blue' : 'bg-[#2a2a2a]'}`}>
              <div className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${riskManagement.skip_risk_management ? 'translate-x-4' : ''}`} />
            </div>
            <span className={`text-sm font-bold tracking-tight transition-colors ${riskManagement.skip_risk_management ? 'text-[#dfdfdf]' : 'text-[#a0a0a0]'}`}>
              리스크 관리 안 함
            </span>
          </div>
        </div>
        
        <div className="max-w-full mx-auto pb-12">
          <RiskManagementEditor 
            riskManagement={riskManagement} 
            onChange={setRiskManagement} 
          />
        </div>
        
        <div className="h-2" />
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
                  {riskManagement.skip_risk_management ? "OFF" : (riskManagement.stop_loss_pct ? `-${riskManagement.stop_loss_pct}%` : "OFF")}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">익절매</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {riskManagement.skip_risk_management ? "OFF" : (riskManagement.take_profit_pct ? `+${riskManagement.take_profit_pct}%` : "OFF")}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">최대 낙폭 (MDD)</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {riskManagement.skip_risk_management ? "OFF" : (riskManagement.max_mdd_limit_pct ? `-${riskManagement.max_mdd_limit_pct}%` : "OFF")}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">유동성 제약</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {riskManagement.skip_risk_management ? "OFF" : `${riskManagement.liquidity_limit_pct || 0}%`}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button 
              onClick={onPrev} 
              className="px-8 py-5 bg-[#161616] border border-white/5 text-white rounded-2xl text-lg font-black hover:bg-[#1f1f1f] hover:border-white/10 transition-all flex items-center gap-4 active:scale-95"
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
