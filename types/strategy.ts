// Strategy DSL Types
export type LogicOperator = "AND" | "OR" | "NOT" | "WEIGHTED_SUM";

export type ConditionType = "indicator" | "flow" | "risk" | "ml" | "filter";

export type IndicatorType =
  | "ma_crossover"
  | "rsi"
  | "macd"
  | "bollinger_bands"
  | "volume_spike"
  | "breakout";

export type FlowType = "investor_net_buy";

export type RiskType =
  | "stop_loss_pct"
  | "take_profit_pct"
  | "max_holding_days"
  | "trailing_stop";

export type MLType = "probability" | "sentiment" | "pattern";

export interface Condition {
  type: ConditionType;
  id: string;
  params: Record<string, any>;
  weight?: number; // For weighted sum
}

export interface ConditionGroup {
  logic: LogicOperator;
  conditions: Condition[];
}

export interface RiskManagement {
  position_size_pct: number; // Percentage of capital per trade
  max_positions: number; // Maximum concurrent positions
  stop_loss_pct?: number; // Fixed stop loss percentage
  take_profit_pct?: number; // Fixed take profit percentage
  trailing_stop_pct?: number; // Trailing stop loss percentage
  max_holding_days?: number; // Maximum holding period in days
  max_daily_loss_pct?: number; // Maximum daily loss percentage
  max_total_exposure_pct?: number; // Maximum total exposure
  max_sector_exposure_pct?: number; // Maximum sector concentration
}

export interface UniverseSelection {
  id: string; // e.g., "kospi", "kosdaq", "US_TECH_TOP10"
  filters: Record<string, any>;
}

export interface StrategyDSL {
  id: string;
  name: string;
  description: string;
  version: string;
  universe: UniverseSelection;
  entry: ConditionGroup;
  exit: ConditionGroup;
  risk: RiskManagement;
  created_at: string;
  updated_at: string;
}

// Signal Block Definitions
export interface SignalBlock {
  id: string;
  name: string;
  description: string;
  category: "indicator" | "flow" | "risk" | "ml" | "filter";
  hidden?: boolean;
  icon?: string;
  defaultParams: Record<string, any>;
  paramSchema: {
    [key: string]: {
      type: "number" | "string" | "boolean" | "select";
      label: string;
      min?: number;
      max?: number;
      step?: number;
      options?: { value: any; label: string }[];
      tooltip?: string;
      suffix?: string;
    };
  };
}

// Backtest Result Types
export interface BacktestResult {
  strategyId: string;
  symbol: string;
  totalReturn: number;
  cagr: number;
  buyAndHoldReturn: number;
  maxDrawdown: number;
  winRate: number;
  profitFactor: number;
  sharpe: number;
  sortino: number;
  volatility?: number;
  calmar?: number;
  kelly: number;
  trades: number;
  finalEquity: number;
  initialCapital: number;
  equity: number[];
  benchmarkEquity?: number[];
  dates: string[];
  tradesList: Array<{
    date: string;
    type: "buy" | "sell";
    price: number;
    quantity: number;
    amount?: number;
    reason: string;
  }>;
  monthlyReturns: Record<string, number>;
  yearlyReturns: Record<string, number>;
  signals: Array<{
    date: string;
    type: "entry" | "exit";
    condition: string;
    price: number;
    quantity?: number;
    amount?: number;
  }>;
  warnings?: string[];
}

export interface BacktestScenario {
  id: string;
  strategyId: string;
  strategyName: string;
  params: Record<string, any>;
  results: BacktestResult;
  timestamp: string;
}


export interface StrategyDataset {
  symbol: string;
  dates: string[];
  prices: {
    open: number[];
    high: number[];
    low: number[];
    close: number[];
    volume: number[];
  };
  features: Record<string, number[] | any>;
}

export interface CanvasBlock {
  id: string;
  type: "filter" | "entry" | "exit";
  blockId: string;
  position: { x: number; y: number };
  params: Record<string, any>;
  connections?: string[]; // IDs of connected blocks
}
