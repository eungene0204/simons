"use client";

import { useEffect, useState, memo } from "react";
import { useRouter } from "next/navigation";
import {
  CaretLeft,
  Bank,
  Plus,
  Robot,
  Bell,
} from "phosphor-react";
import { VirtualAccount } from "@/types/portfolio";
import { getAllAccounts, createAccount } from "@/lib/portfolio";
import CreateAccountModal from "@/components/ui/CreateAccountModal";

interface VirtualAccountDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onAccountSelect: (accountId: string) => void;
}

function VirtualAccountDrawer({
  isOpen,
  onClose,
  onAccountSelect,
}: VirtualAccountDrawerProps) {
  const router = useRouter();
  const [accounts, setAccounts] = useState<VirtualAccount[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isOpen) {
      loadAccounts();
    }
  }, [isOpen]);

  const loadAccounts = async () => {
    setLoading(true);
    const allAccounts = await getAllAccounts();
    setAccounts(allAccounts);
    setLoading(false);
  };

  const handleCreateAccount = async (name: string, amount: number, strategyId?: string, strategyName?: string, tradingMode?: "auto" | "manual") => {
    await createAccount(name, amount, strategyId, strategyName, tradingMode);
    await loadAccounts();
    setIsModalOpen(false);
  };

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  const formatPercent = (value: number, initial: number) => {
    const percent = ((value - initial) / initial) * 100;
    return `${percent >= 0 ? "+" : ""}${percent.toFixed(2)}%`;
  };

  const handleAccountClick = (accountId: string) => {
    onAccountSelect(accountId);
    router.push(`/virtual-account/${accountId}`);
  };

  return (
    <>
      {/* Drawer */}
      <div
        className={`fixed left-0 top-0 h-full w-[20vw] min-w-[300px] max-w-[400px] bg-[#1a1a1a] z-50 transform transition-transform duration-300 ease-out ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{
          willChange: "transform",
          transitionTimingFunction: "cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        <div className="h-full flex flex-col">
          {/* Header */}
          <div
            className="flex flex-col px-4 py-3 flex-shrink-0"
            style={{
              height: "var(--top-menu-bar-height, 76px)",
              minHeight: "var(--top-menu-bar-height, 76px)",
              maxHeight: "var(--top-menu-bar-height, 76px)",
            }}
          >
            <div className="flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xl font-bold text-white">
                  가상계좌
                </h2>
                <button
                  onClick={onClose}
                  className="p-1.5 hover:bg-[#252525] rounded-lg transition-colors"
                  title="닫기"
                >
                  <CaretLeft size={20} className="text-gray-400" />
                </button>
              </div>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto flex flex-col">
            {/* Add Account Button at Top */}
            <div className="px-4 py-3 flex-shrink-0">
              <button
                onClick={() => setIsModalOpen(true)}
                className="w-full flex items-center gap-3 text-left"
              >
                <div className="w-10 h-10 rounded-full bg-[#252525] flex items-center justify-center flex-shrink-0">
                  <Plus size={20} className="text-blue-400" />
                </div>
                <span className="text-sm font-medium text-white">
                  계좌 추가
                </span>
              </button>
            </div>

            {/* Account List */}
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="p-4">
                  <div className="animate-pulse space-y-2">
                    {[...Array(3)].map((_, i) => (
                      <div
                        key={i}
                        className="h-16 bg-[#252525] rounded"
                      ></div>
                    ))}
                  </div>
                </div>
              ) : accounts.length === 0 ? (
                <div className="p-4 text-center text-sm text-gray-400">
                  가상계좌가 없습니다.
                </div>
              ) : (
                <div>
                  {accounts.map((account) => {
                    const profit = account.totalValue - account.initialAmount;
                    const profitPercent =
                      (profit / account.initialAmount) * 100;
                    const isPositive = profit >= 0;

                    return (
                      <div
                        key={account.id}
                        onClick={() => {
                          handleAccountClick(account.id);
                        }}
                        className="px-4 py-3 hover:bg-[#252525] transition-colors cursor-pointer"
                      >
                        <div className="flex items-center gap-3 justify-between">
                          <div className="flex items-center gap-3 flex-1 min-w-0">
                            <div className="w-10 h-10 rounded-full bg-blue-900/30 flex items-center justify-center flex-shrink-0">
                              <Bank size={20} className="text-blue-400" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5">
                                <div className="text-sm font-medium text-white truncate">
                                  {account.name}
                                </div>
                                {account.strategyName && (
                                  account.tradingMode === "auto" ? (
                                    <span className="flex items-center gap-0.5 px-1.5 py-0.5 bg-blue-900/40 text-blue-400 rounded text-xs font-medium flex-shrink-0">
                                      <Robot size={10} weight="bold" />
                                      자동
                                    </span>
                                  ) : (
                                    <span className="flex items-center gap-0.5 px-1.5 py-0.5 bg-[#252525] text-gray-400 rounded text-xs font-medium flex-shrink-0">
                                      <Bell size={10} weight="bold" />
                                      알림
                                    </span>
                                  )
                                )}
                              </div>
                              {account.strategyName ? (
                                <div className="text-xs text-blue-400 truncate">
                                  {account.strategyName}
                                </div>
                              ) : (
                                <div className="text-xs text-gray-400">
                                  잔액: {formatPrice(account.currentBalance)}원
                                </div>
                              )}
                            </div>
                          </div>
                          <div className="flex flex-col items-end flex-shrink-0">
                            <span className="text-sm font-medium text-white">
                              {formatPrice(account.totalValue)}원
                            </span>
                            <span
                              className={`text-xs mt-0.5 ${
                                isPositive
                                  ? "text-red-400"
                                  : "text-blue-400"
                              }`}
                            >
                              {isPositive ? "+" : ""}
                              {formatPrice(Math.abs(profit))}원 (
                              {formatPercent(
                                account.totalValue,
                                account.initialAmount
                              )}
                              )
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Create Account Modal */}
      <CreateAccountModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreate={handleCreateAccount}
      />
    </>
  );
}

export default memo(VirtualAccountDrawer);
