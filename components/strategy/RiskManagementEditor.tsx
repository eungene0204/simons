"use client";

import { RiskManagement } from "@/types/strategy";
import { Info } from "phosphor-react";

interface RiskManagementEditorProps {
  riskManagement: RiskManagement;
  onChange: (risk: RiskManagement) => void;
}

export default function RiskManagementEditor({
  riskManagement,
  onChange,
}: RiskManagementEditorProps) {
  const handleChange = (key: keyof RiskManagement, value: number) => {
    onChange({
      ...riskManagement,
      [key]: value,
    });
  };

  const renderSlider = (
    label: string,
    key: keyof RiskManagement,
    min: number,
    max: number,
    step: number,
    unit: string,
    tooltip: string
  ) => {
    const value = (riskManagement[key] as number) || 0;
    const disabled = riskManagement.skip_risk_management;
    
    return (
      <div className={`p-4 rounded-2xl border transition-all ${
        disabled 
          ? "bg-[#0a0a0a] border-white/5 opacity-30 grayscale" 
          : "bg-black/40 border-white/5 hover:border-white/10 shadow-inner"
      }`}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <label className={`text-xs font-black uppercase tracking-[0.2em] ${disabled ? "text-white/20" : "text-white/40"}`}>
              {label}
            </label>
            <div className="group relative">
              <Info className={`w-3.5 h-3.5 cursor-help transition-colors ${disabled ? "text-white/10" : "text-white/20 hover:text-[rgb(59,134,247)]"}`} />
              <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 hidden group-hover:block z-30 w-56">
                <div className="bg-gray-900/95 backdrop-blur-md text-white text-[10px] rounded-lg px-3 py-2 border border-white/10 shadow-2xl leading-relaxed">
                  {tooltip}
                </div>
              </div>
            </div>
          </div>
          <span className={`text-sm font-black tabular-nums transition-colors ${disabled ? "text-white/20" : "text-[rgb(59,134,247)]"}`}>
            {value}{unit}
          </span>
        </div>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          onChange={(e) => handleChange(key, parseFloat(e.target.value))}
          className={`w-full h-1.5 bg-black/60 rounded-full appearance-none cursor-pointer transition-all ${
            disabled ? "opacity-20 cursor-not-allowed" : "accent-[rgb(59,134,247)] hover:bg-black/80"
          }`}
        />
        <div className={`flex justify-between items-center mt-3 text-[9px] font-black uppercase tracking-widest ${disabled ? "text-white/10" : "text-white/20"}`}>
          <span>{min}{unit}</span>
          <span>{max}{unit}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="grid grid-cols-1 gap-12">
      {/* Capital Management */}
      <section className="relative">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-1.5 h-6 bg-blue-500 rounded-full shadow-[0_0_15px_rgba(59,130,246,0.3)]" />
          <h3 className="text-base font-black text-white/90 uppercase tracking-tight">자금 관리</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {renderSlider(
            "포지션 크기",
            "position_size_pct",
            1, 100, 1, "%",
            "거래당 투입할 자산의 비중을 설정합니다."
          )}
          {renderSlider(
            "유동성 제약",
            "liquidity_limit_pct",
            0, 100, 1, "%",
            "개별 종목의 일일 거래대금 대비 최대 투자 비중을 제한합니다."
          )}
          {renderSlider(
            "현금 보유 비중",
            "min_cash_reserve_pct",
            0, 100, 5, "%",
            "안정성을 위해 전략이 항상 보유해야 하는 최소 현금 비율입니다."
          )}
        </div>
      </section>

      {/* Price-based Exit */}
      <section className="relative">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-1.5 h-6 bg-red-500 rounded-full shadow-[0_0_15px_rgba(239,68,68,0.3)]" />
          <h3 className="text-base font-black text-white/90 uppercase tracking-tight">청산 리스크</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {renderSlider(
            "손절매",
            "stop_loss_pct",
            0, 30, 0.5, "%",
            "매수가 대비 설정한 비율 이상 하락 시 즉시 매도합니다."
          )}
          {renderSlider(
            "익절매",
            "take_profit_pct",
            0, 100, 1, "%",
            "매수가 대비 설정한 목표 수익률 도달 시 즉시 매도합니다."
          )}
          {renderSlider(
            "트레일링 스탑",
            "trailing_stop_pct",
            0, 20, 0.5, "%",
            "최고점 대비 설정한 비율만큼 하락 시 수익을 보존하며 매도합니다."
          )}
        </div>
      </section>

      {/* Portfolio Controls */}
      <section className="relative">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-1.5 h-6 bg-green-500 rounded-full shadow-[0_0_15px_rgba(34,197,94,0.3)]" />
          <h3 className="text-base font-black text-white/90 uppercase tracking-tight">포트폴리오 제어</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {renderSlider(
            "일일 최대 손실",
            "max_daily_loss_pct",
            0, 20, 0.5, "%",
            "하루 동안 포트폴리오 전체에서 허용하는 최대 손실액입니다."
          )}
          {renderSlider(
            "최대 낙폭 제한",
            "max_mdd_limit_pct",
            0, 50, 0.5, "%",
            "전고점 대비 자산 가치가 설정한 비율만큼 하락하면 청산합니다."
          )}
          {renderSlider(
            "최대 총 노출도",
            "max_total_exposure_pct",
            0, 200, 5, "%",
            "전체 자산 대비 실제 시장에 노출된 자산의 총합입니다."
          )}
        </div>
      </section>
    </div>
  );
}

