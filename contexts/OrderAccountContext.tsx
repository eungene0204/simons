"use client";

import { createContext, useContext, useMemo, useState } from "react";

interface OrderAccountContextValue {
  selectedAccountId: string | null;
  setSelectedAccountId: (accountId: string | null) => void;
}

const OrderAccountContext = createContext<OrderAccountContextValue | undefined>(
  undefined
);

export function useOrderAccount() {
  const context = useContext(OrderAccountContext);
  if (!context) {
    throw new Error("useOrderAccount must be used within OrderAccountProvider");
  }
  return context;
}

export function OrderAccountProvider({ children }: { children: React.ReactNode }) {
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const value = useMemo(
    () => ({ selectedAccountId, setSelectedAccountId }),
    [selectedAccountId]
  );

  return (
    <OrderAccountContext.Provider value={value}>
      {children}
    </OrderAccountContext.Provider>
  );
}
