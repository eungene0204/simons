import { SignalBlock } from "@/types/strategy";

export const signalBlocks: Record<string, SignalBlock> = {
  // Indicator Blocks
  ma_crossover: {
    id: "ma_crossover",
    name: "이동평균선 교차",
    description: "단기 이평선이 장기 이평선을 돌파할 때의 추세 전환을 포착합니다. '매수(골든크로스)'는 단기 선이 위로 뚫고 올라올 때의 강력한 상승 추세를, '매도(데드크로스)'는 아래로 뚫고 내려갈 때의 하락 전환 신호를 의미합니다.",
    category: "indicator",
    defaultParams: {
      shortMA: 5,
      longMA: 20,
      signalType: "buy", // "buy" for golden cross, "sell" for death cross
    },
    paramSchema: {
      shortMA: {
        type: "select",
        label: "단기 이평선",
        options: [
          { value: 5, label: "5" },
          { value: 20, label: "20" },
          { value: 60, label: "60" },
          { value: 120, label: "120" },
          { value: 200, label: "200" },
        ],
        tooltip: "추세의 빠른 변화를 감지할 단기 이동평균 기간",
        suffix: "일",
      },
      longMA: {
        type: "select",
        label: "장기 이평선",
        options: [
          { value: 5, label: "5" },
          { value: 20, label: "20" },
          { value: 60, label: "60" },
          { value: 120, label: "120" },
          { value: 200, label: "200" },
        ],
        tooltip: "추세의 기본 방향을 나타내는 장기 이동평균 기간",
        suffix: "일",
      },
      signalType: {
        type: "select",
        label: "교차 종류",
        options: [
          { value: "buy", label: "매수 (골든크로스)" },
          { value: "sell", label: "매도 (데드크로스)" },
        ],
        tooltip: "단기 선이 장기 선을 상향 돌파(골든) 혹은 하향 돌파(데드) 하는 조건",
      },
    },
  },
  rsi: {
    id: "rsi",
    name: "RSI 임계값",
    description: "주가의 과매수 및 과매도 상태를 판단하는 보조지표입니다. 일반적으로 RSI가 30 이하이면 과매도 구간(반등 기대), 70 이상이면 과매수 구간(조정 경계)으로 해석하며, 설정한 임계값과의 비교를 통해 진입/청산 시점을 결정합니다.",
    category: "indicator",
    defaultParams: {
      period: 14,
      operator: "<",
      value: 30,
      signalType: "buy",
    },
    paramSchema: {
      period: {
        type: "number",
        label: "RSI 기간",
        min: 1,
        max: 200,
        step: 1,
        tooltip: "RSI 계산 기간 (보통 14일 권장)",
        suffix: "일",
      },
      value: {
        type: "number",
        label: "임계값",
        min: 0,
        max: 100,
        step: 1,
        tooltip: "RSI 임계값 (0-100)",
        suffix: "pt",
      },
      operator: {
        type: "select",
        label: "연산자",
        options: [
          { value: "<", label: "미만 (<)" },
          { value: ">", label: "초과 (>)" },
          { value: "<=", label: "이하 (≤)" },
          { value: ">=", label: "이상 (≥)" },
        ],
        tooltip: "RSI와 임계값 비교 연산자",
      },
      signalType: {
        type: "select",
        label: "신호 구분",
        options: [
          { value: "buy", label: "매수 (과매도 탈출 등)" },
          { value: "sell", label: "매도 (과매수 진입 등)" },
        ],
        tooltip: "RSI 임계값 도달 시 발생시킬 신호 종류",
      },
    },
  },
  macd: {
    id: "macd",
    name: "MACD 신호",
    description: "이평선의 수렴과 확산을 이용해 추세의 강도와 방향을 분석합니다. MACD선(단기이평 - 장기이평)이 시그널선(MACD 평균)을 상향 돌파하면 매수 타이밍, 하향 돌파하면 매도 타이밍으로 봅니다. 추세 추종 전략에서 매우 신뢰도가 높은 지표입니다.",
    category: "indicator",
    defaultParams: {
      fastPeriod: 12,
      slowPeriod: 26,
      signalPeriod: 9,
      signalType: "buy",
    },
    paramSchema: {
      fastPeriod: {
        type: "number",
        label: "단기 지수이평 (Fast)",
        min: 5,
        max: 20,
        step: 1,
        suffix: "일",
      },
      slowPeriod: {
        type: "number",
        label: "장기 지수이평 (Slow)",
        min: 20,
        max: 50,
        step: 1,
        suffix: "일",
      },
      signalPeriod: {
        type: "number",
        label: "시그널 기간 (Signal)",
        min: 5,
        max: 15,
        step: 1,
        suffix: "일",
      },
      signalType: {
        type: "select",
        label: "신호 구분",
        options: [
          { value: "buy", label: "매수 (상향 돌파)" },
          { value: "sell", label: "매도 (하향 돌파)" },
        ],
      },
    },
  },
  bollinger_bands: {
    id: "bollinger_bands",
    name: "볼린저 밴드",
    description: "주가의 변동성을 상하단 밴드로 시각화한 지표입니다. 가격이 하단 밴드를 하향 돌파할 때 과매도로 판단하여 매수하거나, 상단 밴드를 상향 돌파할 때 강력한 추세로 판단하여 매매 신호를 발생시킵니다. (기본 설정: 20일 이동평균선, 2표준편차)",
    category: "indicator",
    defaultParams: {
      period: 20,
      stdDev: 2,
      signalType: "buy",
    },
    paramSchema: {
      period: {
        type: "number",
        label: "이평선 기간",
        min: 5,
        max: 60,
        step: 1,
        tooltip: "중단 밴드의 기준이 되는 이동평균선 기간",
        suffix: "일",
      },
      stdDev: {
        type: "number",
        label: "표준편차 승수 (K)",
        min: 1,
        max: 4,
        step: 0.1,
        tooltip: "밴드 폭을 결정하는 표준편차 배수 (보통 2.0)",
        suffix: "배",
      },
      signalType: {
        type: "select",
        label: "신호 조건",
        options: [
          { value: "buy", label: "하단 밴드 하향 돌파 (매수)" },
          { value: "sell", label: "상단 밴드 상향 돌파 (매도)" },
        ],
        tooltip: "가격과 밴드의 상호작용에 따른 신호 발생 지점",
      },
    },
  },
  volume_spike: {
    id: "volume_spike",
    name: "거래량 신호",
    description: "거래량의 누적 흐름을 보여주는 OBV(On-Balance Volume)와 그 이동평균선(Signal)의 교차를 감지합니다. OBV가 시그널을 상향 돌파하면 매수세 유입, 하향 돌파하면 매도세 강화를 의미하여 추세 변화의 선행 지표로 활용됩니다.",
    category: "indicator",
    defaultParams: {
      period: 20,
      signalType: "buy",
    },
    paramSchema: {
      period: {
        type: "number",
        label: "신호 평균 기간",
        min: 5,
        max: 120,
        step: 1,
        tooltip: "OBV의 이동평균(Signal)을 산출할 기간 (기본 20일)",
        suffix: "일",
      },
      signalType: {
        type: "select",
        label: "신호 구분",
        options: [
          { value: "buy", label: "매수 (시그널 상향 돌파)" },
          { value: "sell", label: "매도 (시그널 하향 돌파)" },
        ],
        tooltip: "OBV가 시그널선을 상향 돌파(매수) 또는 하향 돌파(매도) 하는 조건",
      },
    },
  },
  breakout: {
    id: "breakout",
    name: "신고가/신저가 돌파",
    description: "주가가 특정 기간(Lookback) 동안의 최고가를 갱신하거나 최저가를 이탈하는 순간을 포착합니다. 박스권 횡보를 끝내고 새로운 추세가 시작될 때 진입하는 '추세 돌파 전략'의 핵심 요소입니다.",
    category: "indicator",
    defaultParams: {
      lookbackPeriod: 20,
      signalType: "buy",
    },
    paramSchema: {
      lookbackPeriod: {
        type: "number",
        label: "기준 기간 (Lookback)",
        min: 5,
        max: 60,
        step: 1,
        tooltip: "신고가 또는 신저가를 계산할 기준 일수",
        suffix: "일",
      },
      signalType: {
        type: "select",
        label: "신호 구분",
        options: [
          { value: "buy", label: "매수 (신고가 돌파)" },
          { value: "sell", label: "매도 (신저가 돌파)" },
        ],
        tooltip: "돌파 시 발생시킬 신호의 성격 (상향/하향)",
      },
    },
  },

  // Flow Blocks
  investor_net_buy: {
    id: "investor_net_buy",
    name: "투자자별 매매",
    description: "기관, 외국인, 개인 등 주요 투자 주체별 매매 동향을 추적합니다. 특정 기간 동안 설정한 수급 강도(합계 금액)를 분석하여 매수 또는 매도 시그널을 발생시킵니다.",
    category: "flow",
    defaultParams: {
      investorType: "institutional",
      period: 5,
      minAmount: 10,
      signalType: "buy",
    },
    paramSchema: {
      investorType: {
        type: "select",
        label: "투자 주체",
        options: [
          { value: "institutional", label: "기관" },
          { value: "foreigner", label: "외국인" },
          { value: "individual", label: "개인" },
        ],
        tooltip: "매매 데이터를 확인할 투자자 그룹",
      },
      period: {
        type: "number",
        label: "기간",
        min: 1,
        max: 20,
        step: 1,
        suffix: "일",
        tooltip: "매매 데이터를 확인할 최근 거래일 기간",
      },
      minAmount: {
        type: "number",
        label: "매매 규모",
        min: 0,
        max: 10000,
        step: 1,
        suffix: "억",
        tooltip: "설정 기간 동안 발생한 순매매 합계 금액 기준",
      },
      signalType: {
        type: "select",
        label: "신호 구분",
        options: [
          { value: "buy", label: "매수 (매수가 많을 때)" },
          { value: "sell", label: "매도 (매도가 많을 때)" },
        ],
      },
    },
  },

  // Risk Blocks
  price_limit_exit: {
    id: "price_limit_exit",
    name: "손절/익절",
    description: "설정한 익절 및 손절 기준에 도달하면 자동으로 매도하여 이익을 확정하거나 큰 손실을 방지합니다.",
    category: "risk",
    defaultParams: {
      stopLossPct: 5.0,
      takeProfitPct: 10.0,
      signalType: "sell",
    },
    paramSchema: {
      stopLossPct: {
        type: "number",
        label: "손절매 기준",
        min: 0,
        max: 50,
        step: 0.5,
        tooltip: "매수 가격 대비 설정한 비율(%) 이하로 하락 시 매도",
        suffix: "%",
      },
      takeProfitPct: {
        type: "number",
        label: "익절매 기준",
        min: 0,
        max: 200,
        step: 0.5,
        tooltip: "매수 가격 대비 설정한 비율(%) 이상으로 상승 시 매도",
        suffix: "%",
      },
    },
  },
  max_holding_days: {
    id: "max_holding_days",
    name: "최대 보유 기간",
    description: "기회비용을 줄이기 위해 투자 자산의 보유 기간을 제한합니다. 설정한 일수가 지나도 목표가에 도달하지 못할 경우 자동으로 매도하여 자금의 회전율을 높이고 비효율적인 투자를 방지합니다.",
    category: "risk",
    defaultParams: {
      value: 20,
      signalType: "sell",
    },
    paramSchema: {
      value: {
        type: "number",
        label: "최대 보유일",
        min: 1,
        max: 365,
        step: 1,
        suffix: "일",
      },
    },
  },
  trailing_stop: {
    id: "trailing_stop",
    name: "트레일링 스탑",
    description: "수익을 극대화하면서도 급격한 하락에 대비하는 유연한 매도 전략입니다. 전고점(최고가)에서 설정한 비율만큼 하락하면 매도하여, 상승 추세 중에는 계속 보유하고 하락 전환 시 이익을 지킵니다.",
    category: "risk",
    defaultParams: {
      percentage: 3.0,
      signalType: "sell",
    },
    paramSchema: {
      percentage: {
        type: "number",
        label: "하락률",
        min: 1,
        max: 10,
        step: 0.5,
        tooltip: "최고가 대비 하락 비율",
        suffix: "%",
      },
    },
  },

  // ML Blocks
  ai_model: {
    id: "ai_model",
    name: "Simons AI 예측 모델",
    description: "Transformer와 XGBoost가 결합된 하이브리드 AI 모델이 계산한 상승 확률을 이용합니다. 과거 패턴을 기반으로 현재 종목이 10일 이내에 7% 이상 상승할 확률이 설정한 임계값보다 높을 때 진입합니다.",
    category: "ml",
    defaultParams: {
      threshold: 70,
      direction: "above",
      signalType: "buy",
    },
    paramSchema: {
      threshold: {
        type: "number",
        label: "확률 임계값",
        min: 5,
        max: 95,
        step: 5,
        tooltip: "매수 신호 발생을 위한 최소 AI 예측 확률 (5% ~ 95%)",
        suffix: "%",
      },
      direction: {
        type: "select",
        label: "판단 기준",
        options: [
          { value: "above", label: "임계값 이상 (상승 예측)" },
          { value: "below", label: "임계값 이하 (하락 예측)" },
        ],
        tooltip: "AI 점수가 설정한 값보다 높을 때 혹은 낮을 때 신호를 발생시킵니다.",
      },
      signalType: {
        type: "select",
        label: "신호 구분",
        options: [
          { value: "buy", label: "매수" },
          { value: "sell", label: "매도" },
        ],
      },
    },
  },

  // Filter Blocks
  trading_value: {
    id: "trading_value",
    name: "거래대금",
    description: "시장의 관심도와 유동성을 필터링합니다. 거래대금이 너무 적은 종목은 매매가 원활하지 않아 슬리피지가 발생할 수 있으므로, 일정 수준 이상의 자금이 유입되는 '활발한 종목' 위주로 선별합니다.",
    category: "filter",
    defaultParams: {
      operator: ">=",
      value: 100, // 100억원
    },
    paramSchema: {
      value: {
        type: "number",
        label: "거래대금",
        min: 0,
        max: 10000,
        step: 1,
        tooltip: "일일 거래대금 기준값 (억)",
        suffix: "억",
      },
      operator: {
        type: "select",
        label: "연산자",
        options: [
          { value: ">=", label: "이상 (≥)" },
          { value: "<=", label: "이하 (≤)" },
          { value: ">", label: "초과 (>)" },
          { value: "<", label: "미만 (<)" },
        ],
        tooltip: "거래대금 비교 연산자",
      },
    },
  },
  market_cap: {
    id: "market_cap",
    name: "시가총액",
    description: "종목의 규모를 기준으로 투자 우주를 정의합니다. 대형주 위주의 안정적인 포트폴리오를 구성하거나, 가볍게 움직이는 중소형주를 타겟팅하는 등 전략의 성격에 맞는 종목군으로 좁히는 역할을 합니다.",
    category: "filter",
    defaultParams: {
      operator: ">=",
      value: 1000, // 1000억원
    },
    paramSchema: {
      value: {
        type: "number",
        label: "시가총액",
        min: 0,
        max: 1000000,
        step: 100,
        tooltip: "시가총액 기준값 (억)",
        suffix: "억",
      },
      operator: {
        type: "select",
        label: "연산자",
        options: [
          { value: ">=", label: "이상 (≥)" },
          { value: "<=", label: "이하 (≤)" },
          { value: ">", label: "초과 (>)" },
          { value: "<", label: "미만 (<)" },
        ],
        tooltip: "시가총액 비교 연산자",
      },
    },
  },
  roe_or_gpa: {
    id: "roe_or_gpa",
    name: "수익성 지표",
    description: "회사의 수익성을 나타내는 핵심 펀더멘털 지표입니다. 자기자본이익률(ROE)이나 매출총이익 대비 자산 비율(GP/A)이 높은 우량한 종목 위주로 투자하여 기본기가 탄탄한 종목을 선별합니다.",
    category: "filter",
    defaultParams: {
      metric: "roe",
      operator: ">=",
      value: 10.0,
    },
    paramSchema: {
      metric: {
        type: "select",
        label: "지표",
        options: [
          { value: "roe", label: "ROE (%)" },
          { value: "gpa", label: "GP/A (%)" },
        ],
        tooltip: "ROE 또는 GP/A 선택",
      },
      value: {
        type: "number",
        label: "값",
        min: -100,
        max: 100,
        step: 0.1,
        tooltip: "ROE 또는 GP/A 기준값",
        suffix: "%",
      },
      operator: {
        type: "select",
        label: "연산자",
        options: [
          { value: ">=", label: "이상 (≥)" },
          { value: "<=", label: "이하 (≤)" },
          { value: ">", label: "초과 (>)" },
          { value: "<", label: "미만 (<)" },
        ],
        tooltip: "비교 연산자",
      },
    },
  },
  debt_ratio: {
    id: "debt_ratio",
    name: "부채비율",
    description: "재무적 안정성을 검증합니다. 회사의 자본 대비 부채량이 너무 많은 종목은 파산 위험이나 재무적 리스크가 클 수 있으므로, 안정적인 운영이 가능한 적정 수준 이하의 부채율을 가진 종목만 남깁니다.",
    category: "filter",
    defaultParams: {
      operator: "<=",
      value: 100.0,
    },
    paramSchema: {
      value: {
        type: "number",
        label: "부채비율",
        min: 0,
        max: 1000,
        step: 1,
        tooltip: "부채비율 기준값",
        suffix: "%",
      },
      operator: {
        type: "select",
        label: "연산자",
        options: [
          { value: ">=", label: "이상 (≥)" },
          { value: "<=", label: "이하 (≤)" },
          { value: ">", label: "초과 (>)" },
          { value: "<", label: "미만 (<)" },
        ],
        tooltip: "부채비율 비교 연산자",
      },
    },
  },

  trading_suspension: {
    id: "trading_suspension",
    name: "거래정지/관리종목",
    description: "위험 종목을 선제적으로 차단합니다. 거래가 정지되었거나 관리종목으로 지정된 부실한 기업들을 투자 대상에서 완전히 제외하여, 예기치 못한 시장 리스크와 상장 폐지 위험으로부터 자산을 보호합니다.",
    category: "filter",
    defaultParams: {
      exclude: true,
    },
    paramSchema: {
      exclude: {
        type: "boolean",
        label: "제외",
        tooltip: "거래정지/관리종목을 필터에서 제외할지 여부",
      },
    },
  },

  // Extended Factors - Hidden from sidebar, visible in search
  per: {
    id: "per",
    name: "PER",
    description: "현재 주가를 주당순이익(EPS)으로 나눈 값입니다. 기업의 수익성 대비 주가 수준을 나타내며, 낮을수록 저평가된 것으로 간주됩니다.",
    category: "filter",
    defaultParams: {
      operator: "<",
      value: 10,
    },
    paramSchema: {
      value: {
        type: "number",
        label: "기준값",
        min: 0,
        max: 500,
        step: 5,
        suffix: "배",
      },
      operator: {
        type: "select",
        label: "비교 연산자",
        options: [
          { value: "<", label: "미만" },
          { value: ">", label: "초과" },
          { value: "<=", label: "이하" },
          { value: ">=", label: "이상" },
        ],
      },
    },
  },

  pbr: {
    id: "pbr",
    name: "PBR",
    description: "현재 주가를 주당순자산(BPS)으로 나눈 값입니다. 기업의 자산가치 대비 주가 수준을 나타내며, 1 미만인 경우 주가가 장부가치보다 낮음을 의미합니다.",
    category: "filter",
    defaultParams: {
      operator: "<",
      value: 1,
    },
    paramSchema: {
      value: {
        type: "number",
        label: "기준값",
        min: 0,
        max: 100,
        step: 5,
        suffix: "배",
      },
      operator: {
        type: "select",
        label: "비교 연산자",
        options: [
          { value: "<", label: "미만" },
          { value: ">", label: "초과" },
          { value: "<=", label: "이하" },
          { value: ">=", label: "이상" },
        ],
      },
    },
  },

  dividend_yield: {
    id: "dividend_yield",
    name: "배당수익률",
    description: "주당 배당금을 현재 주가로 나눈 비율입니다. 투자 원금 대비 배당 수익의 수준을 나타냅니다.",
    category: "indicator",
    hidden: true,
    defaultParams: {
      operator: ">",
      value: 3,
      signalType: "buy",
    },
    paramSchema: {
      value: {
        type: "number",
        label: "기준값 (%)",
        min: 0,
        max: 50,
        step: 0.1,
      },
      operator: {
        type: "select",
        label: "비교 연산자",
        options: [
          { value: "<", label: "미만" },
          { value: ">", label: "초과" },
          { value: "<=", label: "이하" },
          { value: ">=", label: "이상" },
        ],
      },
      signalType: {
        type: "select",
        label: "신호 구분",
        options: [
          { value: "buy", label: "매수" },
          { value: "sell", label: "매도" },
        ],
      },
    },
  },

  psr: {
    id: "psr",
    name: "PSR",
    description: "현재 주가를 주당매출액으로 나눈 값입니다. 성장 초기 단계의 기업 가치 평가에 유용하게 쓰입니다.",
    category: "indicator",
    hidden: true,
    defaultParams: {
      operator: "<",
      value: 1,
      signalType: "buy",
    },
    paramSchema: {
      value: {
        type: "number",
        label: "기준값",
        min: 0,
        max: 100,
        step: 0.1,
      },
      operator: {
        type: "select",
        label: "비교 연산자",
        options: [
          { value: "<", label: "미만" },
          { value: ">", label: "초과" },
          { value: "<=", label: "이하" },
          { value: ">=", label: "이상" },
        ],
      },
      signalType: {
        type: "select",
        label: "신호 구분",
        options: [
          { value: "buy", label: "매수" },
          { value: "sell", label: "매도" },
        ],
      },
    },
  },

  revenue_growth: {
    id: "revenue_growth",
    name: "매출성장률",
    description: "전년 동기 대비 매출액의 증가 비율입니다. 기업의 외형 성장성을 나타냅니다.",
    category: "indicator",
    hidden: true,
    defaultParams: {
      operator: ">",
      value: 10,
      signalType: "buy",
    },
    paramSchema: {
      value: {
        type: "number",
        label: "기준값 (%)",
        min: -100,
        max: 1000,
        step: 1,
      },
      operator: {
        type: "select",
        label: "비교 연산자",
        options: [
          { value: "<", label: "미만" },
          { value: ">", label: "초과" },
          { value: "<=", label: "이하" },
          { value: ">=", label: "이상" },
        ],
      },
      signalType: {
        type: "select",
        label: "신호 구분",
        options: [
          { value: "buy", label: "매수" },
          { value: "sell", label: "매도" },
        ],
      },
    },
  },

  ev_ebitda: {
    id: "ev_ebitda",
    name: "EV/EBITDA",
    description: "기업가치(EV)를 세전 영업이익(EBITDA)으로 나눈 값입니다. 기업이 영업활동을 통해 창출하는 현금흐름 대비 기업가치가 어느 정도인지 나타냅니다.",
    category: "indicator",
    hidden: true,
    defaultParams: { operator: "<", value: 8, signalType: "buy" },
    paramSchema: {
      value: { type: "number", label: "기준값", min: 0, max: 200, step: 0.1 },
      operator: { type: "select", label: "비교 연산자", options: [{ value: "<", label: "미만" }, { value: ">", label: "초과" }, { value: "<=", label: "이하" }, { value: ">=", label: "이상" }] },
      signalType: { type: "select", label: "신호 구분", options: [{ value: "buy", label: "매수" }, { value: "sell", label: "매도" }] },
    },
  },

  pcf: {
    id: "pcf",
    name: "PCF (주가현금흐름비율)",
    description: "현재 주가를 주당영업현금흐름(CPS)으로 나눈 값입니다. 장부상 이익보다 실제 현금흐름을 중시하는 지표입니다.",
    category: "indicator",
    hidden: true,
    defaultParams: { operator: "<", value: 10, signalType: "buy" },
    paramSchema: {
      value: { type: "number", label: "기준값", min: 0, max: 500, step: 0.1 },
      operator: { type: "select", label: "비교 연산자", options: [{ value: "<", label: "미만" }, { value: ">", label: "초과" }, { value: "<=", label: "이하" }, { value: ">=", label: "이상" }] },
      signalType: { type: "select", label: "신호 구분", options: [{ value: "buy", label: "매수" }, { value: "sell", label: "매도" }] },
    },
  },

  roic: {
    id: "roic",
    name: "ROIC (투하자본수익률)",
    description: "투입한 자본 대비 얼마나 많은 이익을 냈는지 나타내며, 기업의 자금 운용 효율성을 보여줍니다.",
    category: "filter",
    hidden: true,
    defaultParams: { operator: ">", value: 10 },
    paramSchema: {
      value: { type: "number", label: "기준값 (%)", min: 0, max: 100, step: 0.1 },
      operator: { type: "select", label: "비교 연산자", options: [{ value: "<", label: "미만" }, { value: ">", label: "초과" }, { value: "<=", label: "이하" }, { value: ">=", label: "이상" }] },
    },
  },

  operating_margin: {
    id: "operating_margin",
    name: "영업이익률",
    description: "매출액 대비 영업이익의 비율입니다. 기업의 주된 사업 활동에서의 수익성을 나타냅니다.",
    category: "indicator",
    hidden: true,
    defaultParams: { operator: ">", value: 15, signalType: "buy" },
    paramSchema: {
      value: { type: "number", label: "기준값 (%)", min: -50, max: 100, step: 0.1 },
      operator: { type: "select", label: "비교 연산자", options: [{ value: "<", label: "미만" }, { value: ">", label: "초과" }, { value: "<=", label: "이하" }, { value: ">=", label: "이상" }] },
      signalType: { type: "select", label: "신호 구분", options: [{ value: "buy", label: "매수" }, { value: "sell", label: "매도" }] },
    },
  },

  debt_to_equity: {
    id: "debt_to_equity",
    name: "부채비율",
    description: "자기자본 대비 부채의 비율입니다. 기업의 재무적 안정성을 나타냅니다.",
    category: "risk",
    hidden: true,
    defaultParams: { operator: "<", value: 100, signalType: "buy" },
    paramSchema: {
      value: { type: "number", label: "기준값 (%)", min: 0, max: 2000, step: 1 },
      operator: { type: "select", label: "비교 연산자", options: [{ value: "<", label: "미만" }, { value: ">", label: "초과" }, { value: "<=", label: "이하" }, { value: ">=", label: "이상" }] },
      signalType: { type: "select", label: "신호 구분", options: [{ value: "buy", label: "매수" }, { value: "sell", label: "매도" }] },
    },
  },

  operating_profit_growth: {
    id: "operating_profit_growth",
    name: "영업이익성장률",
    description: "전년 동기 대비 영업이익의 증가 비율입니다.",
    category: "indicator",
    hidden: true,
    defaultParams: { operator: ">", value: 15, signalType: "buy" },
    paramSchema: {
      value: { type: "number", label: "기준값 (%)", min: -100, max: 2000, step: 1 },
      operator: { type: "select", label: "비교 연산자", options: [{ value: "<", label: "미만" }, { value: ">", label: "초과" }, { value: "<=", label: "이하" }, { value: ">=", label: "이상" }] },
      signalType: { type: "select", label: "신호 구분", options: [{ value: "buy", label: "매수" }, { value: "sell", label: "매도" }] },
    },
  },

  beta: {
    id: "beta",
    name: "베타 (Beta)",
    description: "시장 지수 변동 대비 개별 종목의 변동성 비율입니다. 1보다 크면 시장보다 변동성이 큽니다.",
    category: "risk",
    hidden: true,
    defaultParams: { operator: "<", value: 1.2, signalType: "buy" },
    paramSchema: {
      value: { type: "number", label: "기준값", min: 0, max: 10, step: 0.01 },
      operator: { type: "select", label: "비교 연산자", options: [{ value: "<", label: "미만" }, { value: ">", label: "초과" }, { value: "<=", label: "이하" }, { value: ">=", label: "이상" }] },
      signalType: { type: "select", label: "신호 구분", options: [{ value: "buy", label: "매수" }, { value: "sell", label: "매도" }] },
    },
  },

  foreigner_ownership: {
    id: "foreigner_ownership",
    name: "외국인 보유비중",
    description: "전체 주식 중 외국인 투자자가 보유한 비중입니다.",
    category: "filter",
    hidden: true,
    defaultParams: { operator: ">", value: 10 },
    paramSchema: {
      value: { type: "number", label: "기준값 (%)", min: 0, max: 100, step: 0.1 },
      operator: { type: "select", label: "비교 연산자", options: [{ value: "<", label: "미만" }, { value: ">", label: "초과" }, { value: "<=", label: "이하" }, { value: ">=", label: "이상" }] },
    },
  },
};

