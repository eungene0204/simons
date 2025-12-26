// Market Index Types

export interface MarketIndex {
  name: string; // "코스피", "코스닥"
  symbol: string; // "KOSPI", "KOSDAQ"
  value: number; // 현재 지수 값
  change: number; // 전일 대비 변동
  changePercent: number; // 전일 대비 변동률
  volume: number; // 거래량
  high: number; // 최고가
  low: number; // 최저가
  open: number; // 시가
  previousClose: number; // 전일 종가
  timestamp: Date;
}

export interface MarketIndices {
  kospi: MarketIndex;
  kosdaq: MarketIndex;
}


