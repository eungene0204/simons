export interface Trade {
  date: string;
  type: "buy" | "sell";
  price: number;
  shares: number;
  reason: string;
}

export interface PortfolioState {
  cash: number;
  shares: number;
  entryPrice: number | null;
  entryIndex: number | null;
  peakEquity: number;
  equity: number[];
  trades: Trade[];
}

export class TradeSimulator {
  private state: PortfolioState;
  private initialCapital: number;

  constructor(initialCapital: number = 10000000) {
    this.initialCapital = initialCapital;
    this.state = {
      cash: initialCapital,
      shares: 0,
      entryPrice: null,
      entryIndex: null,
      peakEquity: initialCapital,
      equity: [initialCapital],
      trades: [],
    };
  }

  getState(): PortfolioState {
    return this.state;
  }

  executeEntry(date: string, index: number, price: number, reason: string, riskParams: any) {
    if (this.state.shares > 0) return;

    const positionSizePct = riskParams.position_size_pct || 100;
    const amountToInvest = (this.state.cash * positionSizePct) / 100;
    const sharesToBuy = Math.floor(amountToInvest / price);

    if (sharesToBuy > 0) {
      const cost = sharesToBuy * price;
      this.state.cash -= cost;
      this.state.shares = sharesToBuy;
      this.state.entryPrice = price;
      this.state.entryIndex = index;
      
      this.state.trades.push({
        date,
        type: "buy",
        price,
        shares: sharesToBuy,
        reason,
      });
    }
  }

  executeExit(date: string, price: number, reason: string = "Exit Condition Met") {
    if (this.state.shares === 0) return;

    const proceeds = this.state.shares * price;
    this.state.cash += proceeds;
    
    this.state.trades.push({
      date,
      type: "sell",
      price,
      shares: this.state.shares,
      reason,
    });

    this.state.shares = 0;
    this.state.entryPrice = null;
    this.state.entryIndex = null;
  }

  updateEquity(price: number) {
    const currentEquity = this.state.cash + this.state.shares * price;
    this.state.equity.push(currentEquity);
    this.state.peakEquity = Math.max(this.state.peakEquity, currentEquity);
  }

  finalize(lastPrice: number, lastDate: string) {
    if (this.state.shares > 0) {
      this.executeExit(lastDate, lastPrice, "End of period");
    }
  }
}
