"use client";

type VirtualAccountSimulationNoticeProps = {
  className?: string;
};

export default function VirtualAccountSimulationNotice({
  className = "",
}: VirtualAccountSimulationNoticeProps) {
  return (
    <div
      data-testid="virtual-account-simulation-notice"
      className={`px-3 pb-3 pt-8 md:px-4 ${className}`.trim()}
    >
      <p className="text-center text-xs font-bold leading-6 text-gray-500">
        가상계좌의 자산과 거래 내역은 시뮬레이션 결과입니다. 실제 주문은 발생하지 않으며, 전략 검증 목적으로 제공됩니다.
      </p>
    </div>
  );
}
