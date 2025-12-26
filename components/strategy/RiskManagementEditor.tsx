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

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-white mb-4">자금 관리</h3>
        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1">
                <label className="text-sm font-medium text-gray-300">
                  포지션 크기 (%)
                </label>
                <div className="group relative">
                  <InformationCircleIcon className="w-4 h-4 text-gray-500 cursor-help" />
                  <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block z-10 w-48">
                    <div className="bg-gray-900 text-white text-xs rounded px-2 py-1 border border-gray-700">
                      거래당 사용할 자본의 비율
                    </div>
                  </div>
                </div>
              </div>
              <span className="text-sm text-white font-medium">
                {riskManagement.position_size_pct}%
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={20}
              step={0.5}
              value={riskManagement.position_size_pct}
              onChange={(e) =>
                handleChange("position_size_pct", parseFloat(e.target.value))
              }
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>1%</span>
              <span>20%</span>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1">
                <label className="text-sm font-medium text-gray-300">
                  최대 동시 포지션 수
                </label>
                <div className="group relative">
                  <InformationCircleIcon className="w-4 h-4 text-gray-500 cursor-help" />
                  <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block z-10 w-48">
                    <div className="bg-gray-900 text-white text-xs rounded px-2 py-1 border border-gray-700">
                      동시에 보유할 수 있는 최대 종목 수
                    </div>
                  </div>
                </div>
              </div>
              <span className="text-sm text-white font-medium">
                {riskManagement.max_positions}개
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={50}
              step={1}
              value={riskManagement.max_positions}
              onChange={(e) =>
                handleChange("max_positions", parseInt(e.target.value))
              }
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>1개</span>
              <span>50개</span>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1">
                <label className="text-sm font-medium text-gray-300">
                  최대 일일 손실 (%)
                </label>
                <div className="group relative">
                  <InformationCircleIcon className="w-4 h-4 text-gray-500 cursor-help" />
                  <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block z-10 w-48">
                    <div className="bg-gray-900 text-white text-xs rounded px-2 py-1 border border-gray-700">
                      하루 최대 허용 손실 비율
                    </div>
                  </div>
                </div>
              </div>
              <span className="text-sm text-white font-medium">
                {riskManagement.max_daily_loss_pct || 0}%
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={20}
              step={0.5}
              value={riskManagement.max_daily_loss_pct || 0}
              onChange={(e) =>
                handleChange("max_daily_loss_pct", parseFloat(e.target.value))
              }
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0%</span>
              <span>20%</span>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1">
                <label className="text-sm font-medium text-gray-300">
                  최대 총 노출 (%)
                </label>
                <div className="group relative">
                  <InformationCircleIcon className="w-4 h-4 text-gray-500 cursor-help" />
                  <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block z-10 w-48">
                    <div className="bg-gray-900 text-white text-xs rounded px-2 py-1 border border-gray-700">
                      전체 자본 대비 최대 투자 비율
                    </div>
                  </div>
                </div>
              </div>
              <span className="text-sm text-white font-medium">
                {riskManagement.max_total_exposure_pct || 0}%
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={riskManagement.max_total_exposure_pct || 0}
              onChange={(e) =>
                handleChange(
                  "max_total_exposure_pct",
                  parseFloat(e.target.value)
                )
              }
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>0%</span>
              <span>100%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

