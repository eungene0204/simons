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
            <h3 className="text-xl font-black text-white tracking-tight">리스크 관리</h3>
            <p className="text-sm text-gray-500 mt-1 font-medium">
              손절매, 익절매 등 자산 보호를 위한 규칙을 설정합니다.
            </p>
          </div>
        </div>
        <div className="bg-[#0f0f0f] rounded-2xl border border-gray-800/50 p-8 min-h-[580px] max-w-5xl mx-auto flex flex-col shadow-2xl">
          <div className="flex-1 flex items-center justify-center">
             <div className="text-center w-full max-w-md">
               <div className="w-16 h-16 rounded-2xl bg-orange-500/10 flex items-center justify-center border border-orange-500/20 mx-auto mb-6">
                 <ShieldCheckIcon className="w-8 h-8 text-orange-400" />
               </div>
               <h4 className="text-lg font-bold text-white mb-6">리스크 규칙 구성</h4>
               
               <div className="bg-[#0a0a0a] rounded-xl border border-gray-800 p-6 text-left">
                 <RiskManagementEditor 
                   riskManagement={riskManagement} 
                   onChange={setRiskManagement} 
                 />
               </div>
               
               <p className="text-xs text-gray-500 mt-6 leading-relaxed">
                 설정한 리스크 관리 규칙은 백테스트와 실제 매매에 즉시 반영됩니다.
               </p>
             </div>
          </div>
        </div>
      </div>

      {/* Sticky Navigation Footer */}
      <div className="sticky bottom-0 bg-[#0a0a0a]/90 backdrop-blur-xl border-t border-gray-800/50 p-6 flex justify-end gap-3 z-50 mt-auto">
        <button
          onClick={onPrev}
          className="px-6 py-3 bg-[#0a0a0a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 hover:text-white transition-all flex items-center gap-2"
        >
          <ArrowLeftIcon className="w-5 h-5" />
          이전 단계
        </button>
        <button
          onClick={onNext}
          className="px-8 py-3 bg-blue-600 text-white rounded-xl text-md font-black hover:bg-blue-500 transition-all flex items-center gap-3 shadow-xl shadow-blue-900/40 hover:scale-[1.02]"
        >
          다음: 미리보기
          <ArrowRightIcon className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
