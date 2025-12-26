// Portfolio Types

export interface VirtualAccount {
  id: string;
  name: string;
  initialAmount: number; // 초기 투자금액 (단위: 원)
  currentBalance: number; // 현재 잔액 (단위: 원)
  totalValue: number; // 총 자산 가치 (현금 + 주식 가치)
  createdAt: string;
  updatedAt: string;
}

export interface PortfolioHolding {
  symbol: string;
  name: string;
  quantity: number; // 보유 수량
  averagePrice: number; // 평균 매수 가격
  currentPrice: number; // 현재 가격
  totalValue: number; // 총 가치 (quantity * currentPrice)
  profit: number; // 손익
  profitPercent: number; // 손익률
}

export interface Transaction {
  id: string;
  accountId: string;
  type: "buy" | "sell";
  symbol: string;
  name: string;
  quantity: number;
  price: number;
  totalAmount: number;
  timestamp: string;
}

