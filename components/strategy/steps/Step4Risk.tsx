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
      <div className="space-y-6 p-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-xl font-black text-[#dfdfdf] tracking-tight">리스크 관리</h3>
            <p className="text-sm text-[#a0a0a0] mt-1 font-medium">
              손절매, 익절매 등 자산 보호를 위한 규칙을 설정합니다.
            </p>
          </div>
        </div>
        <div className="bg-[#0f0f0f] rounded-3xl border border-gray-800/50 p-8 min-h-[600px] max-w-6xl mx-auto shadow-2xl overflow-hidden relative">
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
        {/* Navigation Buttons (Non-sticky) */}
        <div className="max-w-6xl mx-auto w-full flex justify-end gap-3 pt-8 pb-12">
          <button
            onClick={onPrev}
            className="px-6 py-3 bg-[#0a0a0a] border border-gray-800 text-gray-300 rounded-2xl text-md font-black hover:bg-gray-800 hover:text-white transition-all flex items-center gap-2"
          >
            <ArrowLeftIcon className="w-5 h-5" />
            이전 단계
          </button>
          <button
            onClick={onNext}
            className="px-8 py-3 bg-white text-black rounded-2xl text-md font-black hover:bg-gray-100 transition-all flex items-center gap-3 shadow-xl shadow-white/5 hover:scale-[1.02]"
          >
            다음: 백테스트
            <ArrowRightIcon className="w-5 h-5" />
          </button>
        </div>
      </div>

    </div>
  );
}
