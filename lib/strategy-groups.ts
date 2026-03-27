/**
 * Strategy Groups - Organized by strategy category
 */

export type StrategyGroupId =
  | "trend_following"
  | "momentum"
  | "mean_reversion"
  | "volatility_based"
  | "factor_investing"
  | "long_short"
  | "asset_allocation"
  | "machine_learning"
  | "crypto_futures";

export interface StrategyParam {
  key: string;
  label: string;
  min: number;
  max: number;
  default: number;
  step?: number;
  tooltip?: string;
  type?: "number" | "select";
  options?: Array<{ value: string | number; label: string }>;
}

export interface StrategyDefinition {
  id: string;
  name: string;
  description: string;
  groupId: StrategyGroupId;
  params: StrategyParam[];
  icon?: string;
}

export interface StrategyGroup {
  id: StrategyGroupId;
  name: string;
  description: string;
  icon: string;
  color: string;
  strategies: StrategyDefinition[];
}

export const strategyGroups: StrategyGroup[] = [
  {
    id: "trend_following",
    name: "추세 추종 전략",
    description: "시장 추세를 따라가는 전략들",
    icon: "📈",
    color: "blue",
    strategies: [
      {
        id: "sma_crossover",
        name: "단순 이동평균 교차 전략",
        description: "단기 SMA가 장기 SMA를 상향 돌파하면 매수, 하향 돌파하면 매도",
        groupId: "trend_following",
        params: [
          {
            key: "shortMA",
            label: "단기 이동평균",
            min: 5,
            max: 50,
            default: 10,
            step: 1,
            tooltip: "단기 이동평균 기간",
          },
          {
            key: "longMA",
            label: "장기 이동평균",
            min: 20,
            max: 200,
            default: 50,
            step: 1,
            tooltip: "장기 이동평균 기간",
          },
        ],
      },
      {
        id: "ema_crossover",
        name: "지수 이동평균 교차 전략",
        description: "단기 EMA가 장기 EMA를 상향 돌파하면 매수, 하향 돌파하면 매도",
        groupId: "trend_following",
        params: [
          {
            key: "shortEMA",
            label: "단기 EMA",
            min: 5,
            max: 50,
            default: 12,
            step: 1,
            tooltip: "단기 지수 이동평균 기간",
          },
          {
            key: "longEMA",
            label: "장기 EMA",
            min: 20,
            max: 200,
            default: 26,
            step: 1,
            tooltip: "장기 지수 이동평균 기간",
          },
        ],
      },
      {
        id: "macd_signal",
        name: "MACD 시그널 전략",
        description: "MACD가 시그널선을 상향 돌파하면 매수, 하향 돌파하면 매도",
        groupId: "trend_following",
        params: [
          {
            key: "fastPeriod",
            label: "Fast EMA",
            min: 5,
            max: 20,
            default: 12,
            step: 1,
          },
          {
            key: "slowPeriod",
            label: "Slow EMA",
            min: 20,
            max: 50,
            default: 26,
            step: 1,
          },
          {
            key: "signalPeriod",
            label: "Signal Period",
            min: 5,
            max: 15,
            default: 9,
            step: 1,
          },
        ],
      },
      {
        id: "donchian_breakout",
        name: "Donchian Channel Breakout",
        description: "N일 고가/저가 채널을 돌파하면 매수/매도",
        groupId: "trend_following",
        params: [
          {
            key: "period",
            label: "채널 기간",
            min: 10,
            max: 100,
            default: 20,
            step: 1,
            tooltip: "Donchian 채널 계산 기간",
          },
          {
            key: "direction",
            label: "방향",
            min: 0,
            max: 1,
            default: 0,
            type: "select",
            options: [
              { value: 0, label: "상향 돌파 (매수)" },
              { value: 1, label: "하향 돌파 (매도)" },
            ],
          },
        ],
      },
      {
        id: "n_day_breakout",
        name: "N일 고가·저가 돌파 전략",
        description: "N일 고가를 돌파하면 매수, N일 저가를 돌파하면 매도",
        groupId: "trend_following",
        params: [
          {
            key: "period",
            label: "기간",
            min: 5,
            max: 100,
            default: 20,
            step: 1,
            tooltip: "고가/저가 계산 기간",
          },
        ],
      },
      {
        id: "atr_breakout",
        name: "ATR Breakout 전략",
        description: "ATR 기반 변동성 돌파 전략",
        groupId: "trend_following",
        params: [
          {
            key: "atrPeriod",
            label: "ATR 기간",
            min: 5,
            max: 30,
            default: 14,
            step: 1,
          },
          {
            key: "multiplier",
            label: "ATR 배수",
            min: 1,
            max: 5,
            default: 2,
            step: 0.1,
            tooltip: "ATR의 몇 배를 돌파해야 하는지",
          },
        ],
      },
      {
        id: "price_channel_breakout",
        name: "Price Channel Breakout",
        description: "가격 채널 상단/하단 돌파 전략",
        groupId: "trend_following",
        params: [
          {
            key: "period",
            label: "채널 기간",
            min: 10,
            max: 100,
            default: 20,
            step: 1,
          },
        ],
      },
      {
        id: "ichimoku_trend",
        name: "Ichimoku Trend Strategy",
        description: "일목균형표 기반 추세 전략",
        groupId: "trend_following",
        params: [
          {
            key: "tenkanPeriod",
            label: "전환선 기간",
            min: 5,
            max: 20,
            default: 9,
            step: 1,
          },
          {
            key: "kijunPeriod",
            label: "기준선 기간",
            min: 20,
            max: 50,
            default: 26,
            step: 1,
          },
        ],
      },
    ],
  },
  {
    id: "momentum",
    name: "모멘텀 전략",
    description: "가격 모멘텀을 활용한 전략들",
    icon: "⚡",
    color: "yellow",
    strategies: [
      {
        id: "absolute_momentum",
        name: "절대 모멘텀 전략",
        description: "과거 N일 수익률이 양수이면 매수, 음수이면 매도",
        groupId: "momentum",
        params: [
          {
            key: "period",
            label: "모멘텀 기간",
            min: 5,
            max: 100,
            default: 12,
            step: 1,
            tooltip: "과거 N일 수익률 계산",
          },
        ],
      },
      {
        id: "relative_momentum",
        name: "상대 모멘텀 전략",
        description: "다른 자산 대비 상대적 모멘텀 비교",
        groupId: "momentum",
        params: [
          {
            key: "period",
            label: "모멘텀 기간",
            min: 5,
            max: 100,
            default: 12,
            step: 1,
          },
          {
            key: "threshold",
            label: "임계값 (%)",
            min: 0,
            max: 20,
            default: 5,
            step: 0.5,
            tooltip: "상대 모멘텀 임계값",
          },
        ],
      },
      {
        id: "dual_momentum",
        name: "Dual Momentum 전략",
        description: "절대 모멘텀과 상대 모멘텀을 결합",
        groupId: "momentum",
        params: [
          {
            key: "absolutePeriod",
            label: "절대 모멘텀 기간",
            min: 5,
            max: 50,
            default: 12,
            step: 1,
          },
          {
            key: "relativePeriod",
            label: "상대 모멘텀 기간",
            min: 5,
            max: 50,
            default: 12,
            step: 1,
          },
        ],
      },
      {
        id: "twelve_one_momentum",
        name: "12-1 모멘텀 전략",
        description: "12개월 수익률이 양수이고 1개월 수익률이 음수일 때 매수",
        groupId: "momentum",
        params: [
          {
            key: "longPeriod",
            label: "장기 기간 (일)",
            min: 200,
            max: 300,
            default: 252,
            step: 1,
            tooltip: "12개월 = 약 252일",
          },
          {
            key: "shortPeriod",
            label: "단기 기간 (일)",
            min: 15,
            max: 30,
            default: 21,
            step: 1,
            tooltip: "1개월 = 약 21일",
          },
        ],
      },
      {
        id: "fiftytwo_week_high",
        name: "52주 신고가 모멘텀",
        description: "52주 신고가 근처에서 매수",
        groupId: "momentum",
        params: [
          {
            key: "period",
            label: "기간 (일)",
            min: 200,
            max: 300,
            default: 252,
            step: 1,
            tooltip: "52주 = 약 252일",
          },
          {
            key: "threshold",
            label: "임계값 (%)",
            min: 0,
            max: 10,
            default: 2,
            step: 0.1,
            tooltip: "신고가 대비 몇 % 이내",
          },
        ],
      },
    ],
  },
  {
    id: "mean_reversion",
    name: "평균회귀 전략",
    description: "가격이 평균으로 회귀하는 특성을 활용",
    icon: "🔄",
    color: "green",
    strategies: [
      {
        id: "rsi_mean_reversion",
        name: "RSI 평균회귀 전략",
        description: "RSI가 과매도 구간에서 반등하면 매수, 과매수 구간에서 하락하면 매도",
        groupId: "mean_reversion",
        params: [
          {
            key: "rsiPeriod",
            label: "RSI 기간",
            min: 5,
            max: 30,
            default: 14,
            step: 1,
          },
          {
            key: "oversold",
            label: "과매도 기준",
            min: 10,
            max: 40,
            default: 30,
            step: 1,
          },
          {
            key: "overbought",
            label: "과매수 기준",
            min: 60,
            max: 90,
            default: 70,
            step: 1,
          },
        ],
      },
      {
        id: "bollinger_mean_reversion",
        name: "Bollinger Band Mean Reversion",
        description: "볼린저 밴드 하단 터치 시 매수, 상단 터치 시 매도",
        groupId: "mean_reversion",
        params: [
          {
            key: "period",
            label: "이동평균 기간",
            min: 10,
            max: 50,
            default: 20,
            step: 1,
          },
          {
            key: "stdDev",
            label: "표준편차",
            min: 1,
            max: 3,
            default: 2,
            step: 0.1,
          },
        ],
      },
      {
        id: "stochastic_reversal",
        name: "Stochastic Reversal 전략",
        description: "Stochastic Oscillator 기반 반전 전략",
        groupId: "mean_reversion",
        params: [
          {
            key: "kPeriod",
            label: "%K 기간",
            min: 5,
            max: 20,
            default: 14,
            step: 1,
          },
          {
            key: "dPeriod",
            label: "%D 기간",
            min: 1,
            max: 10,
            default: 3,
            step: 1,
          },
          {
            key: "oversold",
            label: "과매도",
            min: 10,
            max: 30,
            default: 20,
            step: 1,
          },
          {
            key: "overbought",
            label: "과매수",
            min: 70,
            max: 90,
            default: 80,
            step: 1,
          },
        ],
      },
      {
        id: "keltner_mean_reversion",
        name: "Keltner Channel Mean Reversion",
        description: "Keltner Channel 기반 평균회귀",
        groupId: "mean_reversion",
        params: [
          {
            key: "emaPeriod",
            label: "EMA 기간",
            min: 10,
            max: 50,
            default: 20,
            step: 1,
          },
          {
            key: "atrPeriod",
            label: "ATR 기간",
            min: 5,
            max: 30,
            default: 10,
            step: 1,
          },
          {
            key: "multiplier",
            label: "ATR 배수",
            min: 1,
            max: 3,
            default: 2,
            step: 0.1,
          },
        ],
      },
      {
        id: "vwap_mean_reversion",
        name: "VWAP Mean Reversion / VWAP Bounce",
        description: "VWAP 기준 평균회귀 전략",
        groupId: "mean_reversion",
        params: [
          {
            key: "deviation",
            label: "편차 (%)",
            min: 0.5,
            max: 5,
            default: 2,
            step: 0.1,
            tooltip: "VWAP 대비 편차 임계값",
          },
        ],
      },
    ],
  },
  {
    id: "volatility_based",
    name: "변동성 기반 전략",
    description: "변동성을 활용한 전략들",
    icon: "📊",
    color: "purple",
    strategies: [
      {
        id: "volatility_breakout",
        name: "변동성 돌파 전략",
        description: "변동성 기반 돌파 전략",
        groupId: "volatility_based",
        params: [
          {
            key: "volatilityPeriod",
            label: "변동성 기간",
            min: 5,
            max: 30,
            default: 14,
            step: 1,
          },
          {
            key: "multiplier",
            label: "배수",
            min: 1,
            max: 3,
            default: 2,
            step: 0.1,
          },
        ],
      },
      {
        id: "atr_volatility",
        name: "ATR 기반 변동성 전략",
        description: "ATR을 활용한 변동성 전략",
        groupId: "volatility_based",
        params: [
          {
            key: "atrPeriod",
            label: "ATR 기간",
            min: 5,
            max: 30,
            default: 14,
            step: 1,
          },
          {
            key: "threshold",
            label: "임계값",
            min: 0.5,
            max: 5,
            default: 2,
            step: 0.1,
          },
        ],
      },
      {
        id: "target_volatility",
        name: "Target Volatility 전략",
        description: "목표 변동성 유지 전략",
        groupId: "volatility_based",
        params: [
          {
            key: "targetVol",
            label: "목표 변동성 (%)",
            min: 5,
            max: 30,
            default: 15,
            step: 0.5,
          },
          {
            key: "lookbackPeriod",
            label: "회귀 기간",
            min: 10,
            max: 100,
            default: 20,
            step: 1,
          },
        ],
      },
      {
        id: "volatility_scaling",
        name: "Volatility Scaling 전략",
        description: "변동성에 따라 포지션 크기 조절",
        groupId: "volatility_based",
        params: [
          {
            key: "volatilityPeriod",
            label: "변동성 기간",
            min: 5,
            max: 30,
            default: 20,
            step: 1,
          },
          {
            key: "baseVolatility",
            label: "기준 변동성 (%)",
            min: 5,
            max: 30,
            default: 15,
            step: 0.5,
          },
        ],
      },
    ],
  },
  {
    id: "factor_investing",
    name: "팩터 전략",
    description: "팩터 투자 전략들",
    icon: "🎯",
    color: "indigo",
    strategies: [
      {
        id: "value_factor",
        name: "Value Factor 전략",
        description: "저PBR/저PER/EV-EBIT 기반 가치 투자",
        groupId: "factor_investing",
        params: [
          {
            key: "pbrThreshold",
            label: "PBR 임계값",
            min: 0.5,
            max: 2,
            default: 1,
            step: 0.1,
          },
          {
            key: "perThreshold",
            label: "PER 임계값",
            min: 5,
            max: 20,
            default: 10,
            step: 1,
          },
        ],
      },
      {
        id: "quality_factor",
        name: "Quality Factor 전략",
        description: "ROE, 이익 안정성 기반 품질 팩터",
        groupId: "factor_investing",
        params: [
          {
            key: "minROE",
            label: "최소 ROE (%)",
            min: 5,
            max: 30,
            default: 15,
            step: 1,
          },
          {
            key: "profitStability",
            label: "이익 안정성",
            min: 0.5,
            max: 1,
            default: 0.7,
            step: 0.1,
          },
        ],
      },
      {
        id: "momentum_factor",
        name: "Momentum Factor 전략",
        description: "모멘텀 팩터 기반 전략",
        groupId: "factor_investing",
        params: [
          {
            key: "period",
            label: "모멘텀 기간",
            min: 1,
            max: 12,
            default: 6,
            step: 1,
            tooltip: "개월 단위",
          },
        ],
      },
      {
        id: "low_volatility_factor",
        name: "Low Volatility Factor 전략",
        description: "저변동성 팩터 전략",
        groupId: "factor_investing",
        params: [
          {
            key: "volatilityPeriod",
            label: "변동성 기간",
            min: 20,
            max: 252,
            default: 60,
            step: 1,
          },
          {
            key: "maxVolatility",
            label: "최대 변동성 (%)",
            min: 10,
            max: 50,
            default: 20,
            step: 1,
          },
        ],
      },
      {
        id: "profitability_factor",
        name: "Profitability Factor 전략",
        description: "수익성 팩터 전략",
        groupId: "factor_investing",
        params: [
          {
            key: "minROA",
            label: "최소 ROA (%)",
            min: 2,
            max: 15,
            default: 5,
            step: 0.5,
          },
          {
            key: "minROE",
            label: "최소 ROE (%)",
            min: 5,
            max: 30,
            default: 15,
            step: 1,
          },
        ],
      },
      {
        id: "multi_factor",
        name: "Multi-Factor Composite 전략",
        description: "여러 팩터를 결합한 멀티팩터 전략",
        groupId: "factor_investing",
        params: [
          {
            key: "valueWeight",
            label: "가치 팩터 가중치",
            min: 0,
            max: 1,
            default: 0.3,
            step: 0.1,
          },
          {
            key: "qualityWeight",
            label: "품질 팩터 가중치",
            min: 0,
            max: 1,
            default: 0.3,
            step: 0.1,
          },
          {
            key: "momentumWeight",
            label: "모멘텀 팩터 가중치",
            min: 0,
            max: 1,
            default: 0.4,
            step: 0.1,
          },
        ],
      },
    ],
  },
  {
    id: "long_short",
    name: "롱·쇼트 / 시장중립 전략",
    description: "롱/쇼트 포지션을 동시에 사용하는 전략",
    icon: "⚖️",
    color: "pink",
    strategies: [
      {
        id: "pair_trading",
        name: "Pair Trading",
        description: "상관관계가 높은 두 종목의 가격 차이를 이용",
        groupId: "long_short",
        params: [
          {
            key: "lookbackPeriod",
            label: "회귀 기간",
            min: 20,
            max: 100,
            default: 60,
            step: 1,
          },
          {
            key: "entryThreshold",
            label: "진입 임계값 (표준편차)",
            min: 1,
            max: 3,
            default: 2,
            step: 0.1,
          },
          {
            key: "exitThreshold",
            label: "청산 임계값 (표준편차)",
            min: 0,
            max: 1,
            default: 0.5,
            step: 0.1,
          },
        ],
      },
      {
        id: "statistical_arbitrage",
        name: "Statistical Arbitrage",
        description: "통계적 차익거래 전략",
        groupId: "long_short",
        params: [
          {
            key: "lookbackPeriod",
            label: "회귀 기간",
            min: 20,
            max: 100,
            default: 60,
            step: 1,
          },
          {
            key: "zScoreThreshold",
            label: "Z-Score 임계값",
            min: 1,
            max: 3,
            default: 2,
            step: 0.1,
          },
        ],
      },
      {
        id: "factor_long_short",
        name: "Factor Long–Short 전략",
        description: "팩터 기반 롱/쇼트 전략",
        groupId: "long_short",
        params: [
          {
            key: "factorType",
            label: "팩터 유형",
            min: 0,
            max: 4,
            default: 0,
            type: "select",
            options: [
              { value: 0, label: "Value" },
              { value: 1, label: "Quality" },
              { value: 2, label: "Momentum" },
              { value: 3, label: "Low Volatility" },
              { value: 4, label: "Profitability" },
            ],
          },
          {
            key: "topPercent",
            label: "상위 비율 (%)",
            min: 10,
            max: 50,
            default: 20,
            step: 5,
            tooltip: "롱 포지션 비율",
          },
          {
            key: "bottomPercent",
            label: "하위 비율 (%)",
            min: 10,
            max: 50,
            default: 20,
            step: 5,
            tooltip: "쇼트 포지션 비율",
          },
        ],
      },
      {
        id: "dollar_neutral_momentum",
        name: "Dollar Neutral Long–Short Momentum",
        description: "달러 중립 롱/쇼트 모멘텀",
        groupId: "long_short",
        params: [
          {
            key: "momentumPeriod",
            label: "모멘텀 기간",
            min: 5,
            max: 50,
            default: 12,
            step: 1,
          },
        ],
      },
      {
        id: "sector_neutral_value",
        name: "Sector Neutral Long–Short Value",
        description: "섹터 중립 롱/쇼트 가치 전략",
        groupId: "long_short",
        params: [
          {
            key: "valueMetric",
            label: "가치 지표",
            min: 0,
            max: 2,
            default: 0,
            type: "select",
            options: [
              { value: 0, label: "PBR" },
              { value: 1, label: "PER" },
              { value: 2, label: "EV/EBIT" },
            ],
          },
        ],
      },
    ],
  },
  {
    id: "asset_allocation",
    name: "자산배분 전략",
    description: "자산 배분 기반 전략들",
    icon: "🌐",
    color: "cyan",
    strategies: [
      {
        id: "gtaa",
        name: "Global Tactical Asset Allocation (GTAA)",
        description: "글로벌 전술적 자산 배분",
        groupId: "asset_allocation",
        params: [
          {
            key: "rebalancePeriod",
            label: "재조정 주기 (일)",
            min: 30,
            max: 365,
            default: 90,
            step: 30,
          },
        ],
      },
      {
        id: "all_weather",
        name: "All Weather Portfolio",
        description: "모든 날씨 포트폴리오",
        groupId: "asset_allocation",
        params: [
          {
            key: "riskParity",
            label: "리스크 패리티",
            min: 0,
            max: 1,
            default: 1,
            type: "select",
            options: [
              { value: 0, label: "비활성화" },
              { value: 1, label: "활성화" },
            ],
          },
        ],
      },
      {
        id: "permanent_portfolio",
        name: "Permanent Portfolio",
        description: "영구 포트폴리오",
        groupId: "asset_allocation",
        params: [
          {
            key: "stockPercent",
            label: "주식 비율 (%)",
            min: 20,
            max: 40,
            default: 25,
            step: 5,
          },
          {
            key: "bondPercent",
            label: "채권 비율 (%)",
            min: 20,
            max: 40,
            default: 25,
            step: 5,
          },
          {
            key: "goldPercent",
            label: "금 비율 (%)",
            min: 20,
            max: 40,
            default: 25,
            step: 5,
          },
          {
            key: "cashPercent",
            label: "현금 비율 (%)",
            min: 20,
            max: 40,
            default: 25,
            step: 5,
          },
        ],
      },
      {
        id: "min_variance",
        name: "Minimum Variance Portfolio",
        description: "최소 분산 포트폴리오",
        groupId: "asset_allocation",
        params: [
          {
            key: "lookbackPeriod",
            label: "회귀 기간",
            min: 60,
            max: 252,
            default: 120,
            step: 30,
          },
        ],
      },
      {
        id: "risk_parity",
        name: "Risk Parity 전략",
        description: "리스크 패리티 전략",
        groupId: "asset_allocation",
        params: [
          {
            key: "targetVolatility",
            label: "목표 변동성 (%)",
            min: 5,
            max: 20,
            default: 10,
            step: 0.5,
          },
        ],
      },
    ],
  },
  {
    id: "machine_learning",
    name: "머신러닝 기반 전략",
    description: "ML 기반 예측 전략들",
    icon: "🤖",
    color: "orange",
    strategies: [
      {
        id: "random_forest",
        name: "Random Forest Signal Strategy",
        description: "랜덤 포레스트 기반 신호 생성",
        groupId: "machine_learning",
        params: [
          {
            key: "nEstimators",
            label: "트리 개수",
            min: 50,
            max: 500,
            default: 100,
            step: 50,
          },
          {
            key: "confidence",
            label: "신뢰도 임계값",
            min: 0.5,
            max: 0.95,
            default: 0.7,
            step: 0.05,
          },
        ],
      },
      {
        id: "xgboost",
        name: "XGBoost Signal Strategy",
        description: "XGBoost 기반 신호 생성",
        groupId: "machine_learning",
        params: [
          {
            key: "nEstimators",
            label: "부스팅 라운드",
            min: 50,
            max: 500,
            default: 100,
            step: 50,
          },
          {
            key: "learningRate",
            label: "학습률",
            min: 0.01,
            max: 0.3,
            default: 0.1,
            step: 0.01,
          },
          {
            key: "confidence",
            label: "신뢰도 임계값",
            min: 0.5,
            max: 0.95,
            default: 0.7,
            step: 0.05,
          },
        ],
      },
      {
        id: "lstm_prediction",
        name: "LSTM 가격 예측 전략",
        description: "LSTM 기반 가격 예측",
        groupId: "machine_learning",
        params: [
          {
            key: "sequenceLength",
            label: "시퀀스 길이",
            min: 10,
            max: 60,
            default: 20,
            step: 5,
          },
          {
            key: "hiddenUnits",
            label: "은닉 유닛",
            min: 32,
            max: 256,
            default: 64,
            step: 32,
          },
          {
            key: "predictionHorizon",
            label: "예측 기간",
            min: 1,
            max: 10,
            default: 5,
            step: 1,
          },
        ],
      },
      {
        id: "rl_agent",
        name: "강화학습 트레이딩 에이전트",
        description: "RL 기반 트레이딩 에이전트",
        groupId: "machine_learning",
        params: [
          {
            key: "episodes",
            label: "에피소드 수",
            min: 100,
            max: 1000,
            default: 500,
            step: 100,
          },
          {
            key: "learningRate",
            label: "학습률",
            min: 0.0001,
            max: 0.01,
            default: 0.001,
            step: 0.0001,
          },
        ],
      },
      {
        id: "automl_optimization",
        name: "AutoML 기반 파라미터 최적화 전략",
        description: "AutoML로 파라미터 자동 최적화",
        groupId: "machine_learning",
        params: [
          {
            key: "optimizationMethod",
            label: "최적화 방법",
            min: 0,
            max: 2,
            default: 0,
            type: "select",
            options: [
              { value: 0, label: "Grid Search" },
              { value: 1, label: "Random Search" },
              { value: 2, label: "Bayesian Optimization" },
            ],
          },
          {
            key: "maxIterations",
            label: "최대 반복",
            min: 10,
            max: 100,
            default: 50,
            step: 10,
          },
        ],
      },
    ],
  },
  {
    id: "crypto_futures",
    name: "코인/선물 특화 전략",
    description: "암호화폐 및 선물 특화 전략",
    icon: "₿",
    color: "amber",
    strategies: [
      {
        id: "crypto_volatility_breakout",
        name: "Volatility Breakout for Crypto Futures",
        description: "암호화폐 선물 변동성 돌파",
        groupId: "crypto_futures",
        params: [
          {
            key: "volatilityPeriod",
            label: "변동성 기간",
            min: 5,
            max: 30,
            default: 14,
            step: 1,
          },
          {
            key: "multiplier",
            label: "배수",
            min: 1,
            max: 5,
            default: 2.5,
            step: 0.1,
          },
        ],
      },
      {
        id: "funding_rate_arbitrage",
        name: "Funding Rate Arbitrage",
        description: "펀딩 레이트 차익거래",
        groupId: "crypto_futures",
        params: [
          {
            key: "minFundingRate",
            label: "최소 펀딩 레이트 (%)",
            min: 0.01,
            max: 1,
            default: 0.1,
            step: 0.01,
          },
        ],
      },
      {
        id: "bitcoin_dominance",
        name: "Bitcoin Dominance Rotation",
        description: "비트코인 지배력 로테이션",
        groupId: "crypto_futures",
        params: [
          {
            key: "dominancePeriod",
            label: "지배력 계산 기간",
            min: 20,
            max: 100,
            default: 30,
            step: 10,
          },
        ],
      },
      {
        id: "perpetual_carry",
        name: "Perpetual Futures Carry Strategy",
        description: "영구 선물 캐리 전략",
        groupId: "crypto_futures",
        params: [
          {
            key: "fundingRateThreshold",
            label: "펀딩 레이트 임계값",
            min: 0.01,
            max: 1,
            default: 0.05,
            step: 0.01,
          },
        ],
      },
      {
        id: "opening_range_breakout",
        name: "Opening Range Breakout (선물/코인)",
        description: "시초가 범위 돌파 전략",
        groupId: "crypto_futures",
        params: [
          {
            key: "rangeMinutes",
            label: "범위 시간 (분)",
            min: 5,
            max: 60,
            default: 15,
            step: 5,
          },
        ],
      },
    ],
  },
];

// Helper function to get strategy by ID
export function getStrategyById(strategyId: string): StrategyDefinition | undefined {
  for (const group of strategyGroups) {
    const strategy = group.strategies.find((s) => s.id === strategyId);
    if (strategy) return strategy;
  }
  return undefined;
}

// Helper function to get strategy by name
export function getStrategyByName(strategyName: string): StrategyDefinition | undefined {
  for (const group of strategyGroups) {
    const strategy = group.strategies.find((s) => s.name === strategyName);
    if (strategy) return strategy;
  }
  return undefined;
}

// Helper function to get group by ID
export function getGroupById(groupId: StrategyGroupId): StrategyGroup | undefined {
  return strategyGroups.find((g) => g.id === groupId);
}

