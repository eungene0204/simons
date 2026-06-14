"use client";

interface AutoTradingStrategyMissingModalProps {
  isOpen: boolean;
  title?: string;
  description?: string;
  isCreatingStrategy?: boolean;
  onClose: () => void;
  onCreateStrategy: () => void;
}

export default function AutoTradingStrategyMissingModal({
  isOpen,
  title = "자동매매 설정",
  description = "자동매매를 시작하려면 저장된 전략이 필요합니다.",
  isCreatingStrategy = false,
  onClose,
  onCreateStrategy,
}: AutoTradingStrategyMissingModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm">
      <div className="w-full max-w-md overflow-hidden rounded-2xl bg-[#121212] shadow-2xl">
        <div className="px-5 pt-6 text-center">
          <div>
            <h2 className="text-lg font-black text-white">{title}</h2>
            <p className="mt-1 text-xs font-medium text-gray-500">
              {description}
            </p>
          </div>
        </div>

        <div className="px-5 py-6 text-center">
          <p className="text-sm font-bold text-white">
            아직 저장된 전략이 없습니다. 전략을 만들어 보세요
          </p>
        </div>

        <div className="flex items-center justify-center gap-2 px-5 pb-5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-white/[0.06] px-4 py-2 text-xs font-bold text-gray-400 transition-colors hover:bg-white/[0.1] hover:text-white"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onCreateStrategy}
            disabled={isCreatingStrategy}
            className="rounded-xl bg-[var(--main-blue)] px-4 py-2 text-xs font-black text-white transition-colors hover:bg-[var(--main-blue)]/85 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isCreatingStrategy ? "이동 중..." : "전략 만들기"}
          </button>
        </div>
      </div>
    </div>
  );
}
