// Portfolio Types

export interface VirtualAccount {
  id: string;
  name: string;
  initialAmount: number; // 초기 투자금액 (단위: 원)
  currentBalance: number; // 현재 잔액 (단위: 원)
  totalValue: number; // 총 자산 가치 (현금 + 주식 가치)
  strategyId?: string; // 연결된 전략 ID
  strategyName?: string; // 연결된 전략 이름
  tradingMode?: "auto" | "manual"; // "auto": 자동매매, "manual": 신호 알림 + 수동매매
  status?: "ACTIVE" | "CLOSED";
  createdAt: string;
  updatedAt: string;
  closedAt?: string;
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
  price: number;           // 주문가
  filledPrice?: number;    // 체결가 (슬리피지 반영)
  fee?: number;            // 수수료
  tax?: number;            // 증권거래세 (매도 시)
  avgBuyPrice?: number;    // 평균매수가 (매도 시 실현손익 기준가)
  realizedPnl?: number;    // 실현 손익 (매도 체결 시)
  totalAmount: number;     // 체결금액 (filledPrice * quantity)
  orderType: "MARKET" | "LIMIT";
  status: "PENDING" | "FILLED" | "CANCELLED";
  timestamp: string;       // createdAt
  filledAt?: string;       // 체결 시각
}

export interface PendingOrder extends Transaction {
  status: "PENDING";
}
