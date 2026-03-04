"use client";

import { Dispatch, SetStateAction } from "react";
import { ShieldCheck, ArrowLeft, ArrowRight, ChartBar } from "phosphor-react";
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
  const skip_risk = riskManagement.skip_risk_management;

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
                  리스크 관리
                </h1>
                <p className="text-sm font-medium text-white/50 mb-12">
                  손절매, 익절매 등 자산 보호를 위한 규칙을 설정합니다.
                </p>
              </div>

              {/* Skip Setting Toggle */}
              <div
                className="flex items-center gap-3 bg-[#111] px-5 py-3 rounded-2xl border border-white/5 hover:border-white/10 transition-all cursor-pointer group"
                onClick={() => setRiskManagement({ ...riskManagement, skip_risk_management: !skip_risk })}
              >
                <div className={`w-10 h-6 rounded-full transition-colors relative ${skip_risk ? 'bg-blue-500' : 'bg-[#2a2a2a]'}`}>
                  <div className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${skip_risk ? 'translate-x-4' : ''}`} />
                </div>
                <span className={`text-sm font-bold tracking-tight transition-colors ${skip_risk ? 'text-white' : 'text-white/40'}`}>
                  리스크 관리 안 함
                </span>
              </div>
            </div>

            <div className={`transition-all duration-500 pb-12 ${skip_risk ? 'opacity-30 grayscale pointer-events-none' : ''}`}>
              <RiskManagementEditor 
                riskManagement={riskManagement} 
                onChange={setRiskManagement} 
              />
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
                <span>다음: 백테스트</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>

          </div>
        </div>

        {/* Right Fixed Sidebar (Summary) */}
        <div className="hidden lg:block w-[320px] xl:w-[380px] bg-[#141414] border-l border-white/5 h-full overflow-y-auto shrink-0 p-8">
          
          <div className="flex items-center gap-3 mb-10">
            <ChartBar className="w-6 h-6 text-blue-500" />
            <h3 className="text-base font-black text-white/60 uppercase tracking-widest">리스크 설정 요약</h3>
          </div>

          <div className={`space-y-8 transition-opacity duration-500 ${skip_risk ? 'opacity-30' : 'opacity-100'}`}>
            
            <div>
              <div className="flex items-center gap-2 mb-3">
                <ShieldCheck className="w-5 h-5 text-red-500" />
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">손절매</span>
              </div>
              <span className="text-2xl font-black text-white block pl-8 tracking-tight">
                {skip_risk ? "OFF" : (riskManagement.stop_loss_pct ? `-${riskManagement.stop_loss_pct}%` : "OFF")}
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-3">
                <ShieldCheck className="w-5 h-5 text-green-500" />
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">익절매</span>
              </div>
              <span className="text-2xl font-black text-white block pl-8 tracking-tight">
                {skip_risk ? "OFF" : (riskManagement.take_profit_pct ? `+${riskManagement.take_profit_pct}%` : "OFF")}
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-3">
                <ShieldCheck className="w-5 h-5 text-orange-500" />
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">최대 낙폭 (MDD)</span>
              </div>
              <span className="text-2xl font-black text-white block pl-8 tracking-tight">
                {skip_risk ? "OFF" : (riskManagement.max_mdd_limit_pct ? `-${riskManagement.max_mdd_limit_pct}%` : "OFF")}
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-3">
                <ShieldCheck className="w-5 h-5 text-blue-500" />
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">유동성 제약</span>
              </div>
              <span className="text-2xl font-black text-white block pl-8 tracking-tight">
                {skip_risk ? "OFF" : `${riskManagement.liquidity_limit_pct || 0}%`}
              </span>
            </div>

          </div>

          {skip_risk && (
            <div className="mt-8 p-4 bg-white/5 rounded-xl border border-white/10">
              <p className="text-xs text-blue-400 font-bold mb-1">안내</p>
              <p className="text-[11px] text-white/40 leading-relaxed">
                리스크 관리 설정을 건너뛰며 필터링 없이 100% 자산 운용을 시도합니다. 손실 보호가 제공되지 않으므로 주의가 필요합니다.
              </p>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
