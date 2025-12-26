// Portfolio Utility Functions

import { VirtualAccount, PortfolioHolding, Transaction } from "@/types/portfolio";
import { generateStockPriceData } from "@/lib/mock-stock-data";

const STORAGE_KEY_ACCOUNTS = "virtual_accounts";
const STORAGE_KEY_HOLDINGS = "portfolio_holdings";
const STORAGE_KEY_TRANSACTIONS = "portfolio_transactions";

// 가상계좌 관리
export function getAllAccounts(): VirtualAccount[] {
  if (typeof window === "undefined") return [];
  const data = localStorage.getItem(STORAGE_KEY_ACCOUNTS);
  return data ? JSON.parse(data) : [];
}

export function getAccount(id: string): VirtualAccount | null {
  const accounts = getAllAccounts();
  return accounts.find((acc) => acc.id === id) || null;
}

export function createAccount(name: string, initialAmount: number): VirtualAccount {
  const accounts = getAllAccounts();
  const newAccount: VirtualAccount = {
    id: `acc_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    name,
    initialAmount,
    currentBalance: initialAmount,
    totalValue: initialAmount,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  accounts.push(newAccount);
  localStorage.setItem(STORAGE_KEY_ACCOUNTS, JSON.stringify(accounts));
  return newAccount;
}

export function updateAccount(account: VirtualAccount): void {
  const accounts = getAllAccounts();
  const index = accounts.findIndex((acc) => acc.id === account.id);
  if (index !== -1) {
    accounts[index] = { ...account, updatedAt: new Date().toISOString() };
    localStorage.setItem(STORAGE_KEY_ACCOUNTS, JSON.stringify(accounts));
  }
}

export function deleteAccount(id: string): void {
  const accounts = getAllAccounts().filter((acc) => acc.id !== id);
  localStorage.setItem(STORAGE_KEY_ACCOUNTS, JSON.stringify(accounts));
  
  // 관련 보유 종목도 삭제
  const holdings = getAllHoldings().filter((h) => h.accountId !== id);
  localStorage.setItem(STORAGE_KEY_HOLDINGS, JSON.stringify(holdings));
  
  // 관련 거래 내역도 삭제
  const transactions = getAllTransactions().filter((t) => t.accountId !== id);
  localStorage.setItem(STORAGE_KEY_TRANSACTIONS, JSON.stringify(transactions));
}

// 보유 종목 관리
interface HoldingWithAccountId extends PortfolioHolding {
  accountId: string;
}

export function getAllHoldings(): HoldingWithAccountId[] {
  if (typeof window === "undefined") return [];
  const data = localStorage.getItem(STORAGE_KEY_HOLDINGS);
  return data ? JSON.parse(data) : [];
}

export function getHoldingsByAccount(accountId: string): PortfolioHolding[] {
  const holdings = getAllHoldings();
  return holdings
    .filter((h) => h.accountId === accountId)
    .map(({ accountId, ...holding }) => {
      // 실제 현재가를 mock 데이터에서 가져오기
      const priceData = generateStockPriceData(holding.symbol);
      const currentPrice = priceData.currentPrice;
      const totalValue = holding.quantity * currentPrice;
      const profit = totalValue - (holding.quantity * holding.averagePrice);
      const profitPercent = (profit / (holding.quantity * holding.averagePrice)) * 100;

      return {
        ...holding,
        currentPrice,
        totalValue,
        profit,
        profitPercent,
      };
    });
}

export function updateHolding(
  accountId: string,
  symbol: string,
  quantity: number,
  price: number,
  name?: string
): void {
  const holdings = getAllHoldings();
  const existingIndex = holdings.findIndex(
    (h) => h.accountId === accountId && h.symbol === symbol
  );

  if (quantity === 0) {
    // 수량이 0이면 보유 종목에서 제거
    if (existingIndex !== -1) {
      holdings.splice(existingIndex, 1);
    }
  } else {
    if (existingIndex !== -1) {
      // 기존 보유 종목 업데이트
      const existing = holdings[existingIndex];
      const totalQuantity = existing.quantity + quantity;
      const totalCost = existing.averagePrice * existing.quantity + price * quantity;
      holdings[existingIndex] = {
        ...existing,
        quantity: totalQuantity,
        averagePrice: totalCost / totalQuantity,
        currentPrice: price,
        name: name || existing.name,
      };
    } else {
      // 새 보유 종목 추가
      holdings.push({
        accountId,
        symbol,
        name: name || symbol, // 실제 이름이 있으면 사용, 없으면 심볼 사용
        quantity,
        averagePrice: price,
        currentPrice: price,
        totalValue: quantity * price,
        profit: 0,
        profitPercent: 0,
      });
    }
  }

  localStorage.setItem(STORAGE_KEY_HOLDINGS, JSON.stringify(holdings));
}

// 거래 내역 관리
export function getAllTransactions(): Transaction[] {
  if (typeof window === "undefined") return [];
  const data = localStorage.getItem(STORAGE_KEY_TRANSACTIONS);
  return data ? JSON.parse(data) : [];
}

export function getTransactionsByAccount(accountId: string): Transaction[] {
  const transactions = getAllTransactions();
  return transactions.filter((t) => t.accountId === accountId);
}

export function addTransaction(transaction: Omit<Transaction, "id" | "timestamp">): Transaction {
  const transactions = getAllTransactions();
  const newTransaction: Transaction = {
    ...transaction,
    id: `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    timestamp: new Date().toISOString(),
  };
  transactions.push(newTransaction);
  localStorage.setItem(STORAGE_KEY_TRANSACTIONS, JSON.stringify(transactions));
  return newTransaction;
}

// 계좌 총 자산 계산
export function calculateAccountTotalValue(accountId: string): number {
  const account = getAccount(accountId);
  if (!account) return 0;

  const holdings = getHoldingsByAccount(accountId);
  const stocksValue = holdings.reduce((sum, h) => sum + h.totalValue, 0);
  return account.currentBalance + stocksValue;
}

// 계좌 업데이트 (총 자산 가치 반영)
export function refreshAccountValue(accountId: string): void {
  const account = getAccount(accountId);
  if (!account) return;

  const totalValue = calculateAccountTotalValue(accountId);
  updateAccount({
    ...account,
    totalValue,
  });
}

