"use client";

import { RiskManagement } from "@/types/strategy";
import { InformationCircleIcon } from "@heroicons/react/24/outline";

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
    return (
      <div className="bg-[#111111] p-4 rounded-xl border border-gray-800/50 hover:border-gray-700 transition-colors">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5">
            <label className="text-sm font-bold text-[#a0a0a0] uppercase tracking-tight">
              {label}
            </label>
            <div className="group relative">
              <InformationCircleIcon className="w-3.5 h-3.5 text-gray-600 cursor-help" />
              <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block z-20 w-56">
                <div className="bg-gray-900 text-white text-[11px] rounded-lg px-3 py-2 border border-gray-700 shadow-2xl">
                  {tooltip}
                </div>
              </div>
            </div>
          </div>
          <span className="text-base text-white font-mono font-bold">
            {value}{unit}
          </span>
        </div>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => handleChange(key, parseFloat(e.target.value))}
          className="w-full accent-main-blue h-1.5 bg-[#222222] rounded-lg appearance-none cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-[#a0a0a0] font-medium mt-2">
          <span>{min}{unit}</span>
          <span>{max}{unit}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 px-8">
      {/* Capital Management */}
      <section className="bg-[#0a0a0a]/50 rounded-3xl border border-gray-800/80 p-8 shadow-xl space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-1.5 h-6 bg-white rounded-full" />
          <h3 className="text-base font-black text-[#dfdfdf] tracking-tight">자금 관리</h3>
        </div>
        <div className="grid grid-cols-1 gap-6">
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
            "개별 종목의 일일 거래대금 대비 최대 투자 비중을 제한합니다. 과도한 비중으로 인한 체결 리스크를 방지합니다."
          )}
          {renderSlider(
            "최소 현금 보유 비중",
            "min_cash_reserve_pct",
            0, 100, 5, "%",
            "안정성을 위해 전략이 항상 보유해야 하는 최소 현금 비율입니다."
          )}
          {renderSlider(
            "일일 최대 매수 한도",
            "max_daily_buy_pct",
            0, 100, 5, "%",
            "과도한 매매를 방지하기 위해 하루에 투입할 수 있는 최대 자금 비율입니다."
          )}
        </div>
      </section>

      {/* Price-based Exit */}
      <section className="bg-[#0a0a0a]/50 rounded-3xl border border-gray-800/80 p-8 shadow-xl space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-1.5 h-6 bg-gray-400 rounded-full" />
          <h3 className="text-base font-black text-[#dfdfdf] tracking-tight">가격 기반 청산 리스크</h3>
        </div>
        <div className="grid grid-cols-1 gap-6">
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
          {renderSlider(
            "최대 보유 기간",
            "max_holding_days",
            0, 200, 1, "일",
            "설정한 기간이 지나면 수익 여부와 관계없이 매도합니다. (0은 무제한)"
          )}
        </div>
      </section>

      {/* Portfolio Controls */}
      <section className="bg-[#0a0a0a]/50 rounded-3xl border border-gray-800/80 p-8 shadow-xl space-y-6">
        <div className="flex items-center gap-3">
          <div className="w-1.5 h-6 bg-gray-600 rounded-full" />
          <h3 className="text-base font-black text-[#dfdfdf] tracking-tight">포트폴리오 제어</h3>
        </div>
        <div className="grid grid-cols-1 gap-6">
          {renderSlider(
            "일일 최대 손실",
            "max_daily_loss_pct",
            0, 20, 0.5, "%",
            "하루 동안 포트폴리오 전체에서 허용하는 최대 손실액입니다."
          )}
          {renderSlider(
            "최대 낙폭 제한 (MDD)",
            "max_mdd_limit_pct",
            0, 50, 0.5, "%",
            "전고점 대비 자산 가치가 설정한 비율만큼 하락하면 모든 포지션을 청산합니다."
          )}
          {renderSlider(
            "최대 총 노출도",
            "max_total_exposure_pct",
            0, 200, 5, "%",
            "전체 자산 대비 실제 시장에 노출된 자산의 총합입니다."
          )}
          {renderSlider(
            "섹터별 최대 집중도",
            "max_sector_exposure_pct",
            0, 100, 5, "%",
            "특정 섹터에 과도하게 자산이 쏠리는 것을 방지합니다."
          )}
        </div>
      </section>
    </div>
  );
}

