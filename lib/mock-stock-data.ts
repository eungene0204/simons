// Mock Stock Data Generator
// 프로젝트 전체에서 사용할 실제 주가 데이터처럼 생성되는 mock 데이터 유틸리티

export interface OrderBookItem {
  price: number;
  quantity: number;
}

export interface OrderBookData {
  sellOrders: OrderBookItem[]; // 매도 호가 (높은 가격부터)
  buyOrders: OrderBookItem[]; // 매수 호가 (낮은 가격부터)
}

export interface StockPriceData {
  currentPrice: number;
  previousClose: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  change: number;
  changePercent: number;
}

/**
 * 종목별 미리 생성된 가격 데이터 캐시
 * 1일치 데이터를 1초 간격으로 생성 (6시간 * 3600초 = 21600개)
 */
const priceDataCache: Record<string, {
  prices: number[];
  basePrice: number;
  initialVolume: number;
  incrementPerSecond: number;
  previousClose: number;
  open: number;
  high: number;
  low: number;
  createdAt: number;
}> = {};

/**
 * 종목별 미리 생성된 가격 데이터를 생성합니다
 * 1일치 데이터를 1초 간격으로 생성 (장 시간: 9시 ~ 15시 30분 = 6.5시간 = 23400초)
 */
function generatePriceDataArray(
  symbol: string,
  basePrice: number
): {
  prices: number[];
  initialVolume: number;
  incrementPerSecond: number;
  previousClose: number;
  open: number;
  high: number;
  low: number;
} {
  const seed = symbol.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const prices: number[] = [];
  
  // 장 시간: 9시 ~ 15시 30분 = 6.5시간 = 23400초
  const marketDurationSeconds = 23400;
  
  // 시가 생성 (장 시작 시 가격)
  const openVariation = (Math.sin(seed * 100) * 10000) % 1;
  const initialChange = (openVariation - 0.5) * 0.02 * basePrice;
  let currentPrice = basePrice + initialChange;
  const open = currentPrice;
  
  // 전일 종가 (시가보다 약간 낮게)
  const previousClose = basePrice * (0.995 + (Math.sin(seed * 50) * 10000) % 1 * 0.01);
  
  let high = open;
  let low = open;
  
  // 랜덤 워크로 가격 데이터 생성
  const volatility = basePrice * 0.0001; // 초당 0.01% 변동성
  
  for (let i = 0; i < marketDurationSeconds; i++) {
    // 각 초마다 작은 변동 추가
    const stepSeed = seed + i * 1000;
    const x = Math.sin(stepSeed) * 10000;
    const random = x - Math.floor(x);
    
    // 각 스텝에서 -1% ~ +1% 범위의 작은 변동
    const stepChange = (random - 0.5) * 0.02;
    currentPrice += stepChange * volatility;
    
    // 가격이 너무 크게 변동하지 않도록 제한 (±5%)
    const minPrice = basePrice * 0.95;
    const maxPrice = basePrice * 1.05;
    currentPrice = Math.max(minPrice, Math.min(maxPrice, currentPrice));
    
    prices.push(Math.round(currentPrice));
    
    // 고가/저가 업데이트
    high = Math.max(high, currentPrice);
    low = Math.min(low, currentPrice);
  }
  
  // 거래량 초기값 생성 (심볼별로 고유하고 실제와 유사한 분포)
  // 심볼을 더 복잡하게 해싱하여 고유성 확보
  const volumeSeed = symbol.split("").reduce((acc, char, idx) => {
    return acc + char.charCodeAt(0) * (idx + 1) * 31;
  }, 0);
  
  // 심볼 길이와 문자 조합으로 더 고유한 값 생성
  const symbolHash = symbol.split("").reduce((acc, char) => acc * 31 + char.charCodeAt(0), 0);
  const combinedSeed = (volumeSeed * 1007 + symbolHash * 503) % 10000000;
  
  // 로그 스케일로 분포 (실제 주식 시장처럼)
  // 작은 값은 더 자주, 큰 값은 드물게
  const normalized = (Math.sin(combinedSeed) * 10000) % 1;
  const logValue = Math.pow(10, normalized * 4 - 1); // 0.1 ~ 1000 범위를 로그 스케일로
  
  // 실제 주식 거래량 범위로 변환 (10만 ~ 1억 주)
  // 대형주는 많고, 소형주는 적게
  const minVolume = 100000; // 10만 주
  const maxVolume = 100000000; // 1억 주
  const volumeRange = maxVolume - minVolume;
  
  // 로그 분포를 선형 범위로 변환
  const initialVolume = Math.floor(minVolume + (logValue / 1000) * volumeRange);
  
  // 가격대에 따라 거래량 조정 (고가주는 거래량이 적을 수 있음)
  const priceFactor = basePrice > 100000 ? 0.5 : basePrice > 50000 ? 0.7 : 1.0;
  const adjustedInitialVolume = Math.floor(initialVolume * priceFactor);
  
  // 1초당 증가량: 초기 거래량의 0.01% ~ 0.1% 정도 (더 다양하게)
  const incrementFactor = 0.0001 + ((combinedSeed % 10) * 0.00001);
  const incrementPerSecond = adjustedInitialVolume * incrementFactor;
  
  return {
    prices,
    initialVolume: adjustedInitialVolume,
    incrementPerSecond,
    previousClose: Math.round(previousClose),
    open: Math.round(open),
    high: Math.round(high),
    low: Math.round(low),
  };
}

/**
 * 종목별 미리 생성된 가격 데이터를 가져옵니다
 * 캐시에 없으면 생성하고, 있으면 재사용합니다
 */
function getPriceData(symbol: string, basePrice: number) {
  const cacheKey = symbol;
  
  // 캐시에 없거나 하루가 지났으면 재생성
  if (!priceDataCache[cacheKey] || Date.now() - priceDataCache[cacheKey].createdAt > 86400000) {
    const data = generatePriceDataArray(symbol, basePrice);
    priceDataCache[cacheKey] = {
      ...data,
      basePrice,
      createdAt: Date.now(),
    };
  }
  
  return priceDataCache[cacheKey];
}

/**
 * 종목별 기본 가격 데이터
 * 실제 주가와 유사한 가격대를 사용
 */
const STOCK_BASE_PRICES: Record<string, number> = {
  "005930": 72500, // 삼성전자
  "000660": 142000, // SK하이닉스
  "035420": 198500, // NAVER
  "035720": 54600, // 카카오
  "005380": 234000, // 현대차
  "051910": 456000, // LG화학
  "006400": 412000, // 삼성SDI
  "028260": 123000, // 삼성물산
  "105560": 65000, // KB금융
  "055550": 45000, // 신한지주
  "032830": 89000, // 삼성생명
  "003670": 456000, // 포스코홀딩스
  "034730": 198000, // SK
  "096770": 156000, // SK이노베이션
  "017670": 52000, // SK텔레콤
  "207940": 890000, // 삼성바이오로직스
  "068270": 185000, // 셀트리온
  "035900": 65000, // JYP Ent.
  "251270": 78000, // 넷마블
  "035760": 98000, // CJ ENM
  "086790": 52000, // 하나금융지주
  "036570": 580000, // 엔씨소프트
  "066570": 105000, // LG전자
  // 로봇 관련주
  "454910": 45000, // 두산로보틱스
  "090710": 32000, // 로보티즈
  "056080": 28000, // 유진로봇
  "117730": 85000, // 티로보틱스
  "058610": 42000, // 에스피지
  "277810": 15000, // 레인보우로보틱스
  "238490": 18000, // 하이로봇
  "208710": 12000, // 엔젤로봇
  "270660": 35000, // 현대로보틱스
  "090360": 25000, // 로보스타
  "238200": 22000, // 비피도
  "108320": 55000, // LX세미콘
};

/**
 * 종목의 기본 가격을 가져옵니다
 */
export function getBasePrice(symbol: string): number {
  return STOCK_BASE_PRICES[symbol] || 50000;
}

/**
 * 실제 주가처럼 변동하는 가격을 생성합니다
 * 미리 생성된 가격 데이터 배열에서 시간 기반으로 가져옵니다
 */
export function generateRealisticPrice(
  basePrice: number,
  symbol: string,
  timestamp?: number
): number {
  const now = timestamp || Date.now();
  
  // 미리 생성된 가격 데이터 가져오기
  const priceData = getPriceData(symbol, basePrice);
  
  // 장 시작 시간 (오전 9시) 기준으로 경과 초 계산
  const today = new Date(now);
  today.setHours(9, 0, 0, 0);
  const marketStartTime = today.getTime();
  const elapsedSeconds = Math.max(0, Math.floor((now - marketStartTime) / 1000));
  
  // 장 시간: 9시 ~ 15시 30분 = 6.5시간 = 23400초
  const marketDurationSeconds = 23400;
  
  // 경과 초가 장 시간을 넘으면 마지막 가격 사용
  const index = Math.min(elapsedSeconds, marketDurationSeconds - 1);
  
  // 미리 생성된 가격 데이터 배열에서 가져오기
  return priceData.prices[index] || priceData.prices[priceData.prices.length - 1];
}

/**
 * 실제 주가 데이터를 생성합니다
 * 미리 생성된 가격 데이터 배열에서 시간 기반으로 가져옵니다
 */
export function generateStockPriceData(
  symbol: string,
  basePrice?: number
): StockPriceData {
  const base = basePrice || getBasePrice(symbol);
  const now = Date.now();
  
  // 미리 생성된 가격 데이터 가져오기
  const priceData = getPriceData(symbol, base);
  
  // 장 시작 시간 (오전 9시) 기준으로 경과 초 계산
  const today = new Date(now);
  today.setHours(9, 0, 0, 0);
  const marketStartTime = today.getTime();
  const elapsedSeconds = Math.max(0, Math.floor((now - marketStartTime) / 1000));
  
  // 장 시간: 9시 ~ 15시 30분 = 6.5시간 = 23400초
  const marketDurationSeconds = 23400;
  
  // 경과 초가 장 시간을 넘으면 마지막 가격 사용
  const index = Math.min(elapsedSeconds, marketDurationSeconds - 1);
  
  // 현재가: 미리 생성된 가격 데이터 배열에서 가져오기
  const currentPrice = priceData.prices[index] || priceData.prices[priceData.prices.length - 1];
  
  // 전일 종가, 시가, 고가, 저가는 미리 생성된 데이터 사용
  const previousClose = priceData.previousClose;
  const open = priceData.open;
  
  // 고가/저가: 장 시작 이후 현재까지의 최고/최저가 계산
  let high = open;
  let low = open;
  
  // 현재까지의 가격 데이터를 확인하여 고가/저가 업데이트
  for (let i = 0; i <= index; i += 10) { // 10초 간격으로 체크 (성능 최적화)
    const priceAtTime = priceData.prices[i] || priceData.prices[priceData.prices.length - 1];
    high = Math.max(high, priceAtTime);
    low = Math.min(low, priceAtTime);
  }
  
  // 현재가도 고가/저가에 반영
  high = Math.max(high, currentPrice);
  low = Math.min(low, currentPrice);
  
  // 거래량: 초기값 + 경과 초에 따른 누적 거래량 (오직 증가만)
  const accumulatedVolume = elapsedSeconds * priceData.incrementPerSecond;
  const volume = Math.floor(priceData.initialVolume + accumulatedVolume);
  
  // 변동 계산
  const change = currentPrice - previousClose;
  const changePercent = (change / previousClose) * 100;
  
  return {
    currentPrice: Math.round(currentPrice),
    previousClose: Math.round(previousClose),
    open: Math.round(open),
    high: Math.round(high),
    low: Math.round(low),
    volume,
    change: Math.round(change),
    changePercent: Math.round(changePercent * 100) / 100,
  };
}

/**
 * 한국 주식 시장 호가 단위를 반환합니다
 * - 1,000원 미만: 1원 단위
 * - 1,000원 이상 5,000원 미만: 5원 단위
 * - 5,000원 이상 10,000원 미만: 10원 단위
 * - 10,000원 이상 50,000원 미만: 50원 단위
 * - 50,000원 이상 100,000원 미만: 100원 단위
 * - 100,000원 이상: 500원 단위
 */
function getTickSize(price: number): number {
  if (price < 1000) return 1;
  if (price < 5000) return 5;
  if (price < 10000) return 10;
  if (price < 50000) return 50;
  if (price < 100000) return 100;
  return 500;
}

/**
 * 호가 단위에 맞춰 가격을 조정합니다
 */
function roundToTick(price: number, tickSize: number): number {
  return Math.floor(price / tickSize) * tickSize;
}

/**
 * 실제 호가창 데이터를 생성합니다
 * 현재가를 기준으로 매도/매수 호가를 생성
 * 한국 주식 시장의 호가 단위를 고려합니다
 * 시간에 따라 수량이 변동합니다
 */
export function generateOrderBook(
  symbol: string,
  currentPrice?: number,
  levels: number = 10
): OrderBookData {
  // 현재가가 없으면 기본 가격으로 생성
  const basePrice = currentPrice || generateRealisticPrice(getBasePrice(symbol), symbol);
  const tickSize = getTickSize(basePrice);
  const sellOrders: OrderBookItem[] = [];
  const buyOrders: OrderBookItem[] = [];
  
  // 심볼 기반 시드로 일관된 호가 생성
  const seed = symbol.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const now = Date.now();
  const timeSeed = Math.floor(now / 1000); // 1초 단위로 변동
  
  // 매도 호가 생성 (현재가보다 높은 가격)
  for (let i = 1; i <= levels; i++) {
    // 호가 단위에 맞춰 가격 간격 설정
    const tickMultiplier = i; // 1틱, 2틱, 3틱...
    const priceOffset = tickSize * tickMultiplier;
    const rawPrice = basePrice + priceOffset;
    
    // 호가 단위에 맞춰 가격 조정
    const price = roundToTick(rawPrice, tickSize);
    
    // 수량 생성 (심볼 기반 일관성 유지, 시간에 따라 변동)
    const qtySeed = (seed + i * 1000 + timeSeed * 100) % 1000000;
    const baseQty = 10000 + (qtySeed % 500000);
    // 수량에 시간 기반 변동 추가 (70% ~ 130%)
    const timeVariation = 0.7 + (Math.sin(qtySeed + timeSeed) * 0.6);
    const quantity = Math.floor(baseQty * timeVariation);
    
    sellOrders.push({
      price,
      quantity,
    });
  }
  
  // 매수 호가 생성 (현재가보다 낮은 가격)
  for (let i = 1; i <= levels; i++) {
    // 호가 단위에 맞춰 가격 간격 설정
    const tickMultiplier = i; // 1틱, 2틱, 3틱...
    const priceOffset = tickSize * tickMultiplier;
    const rawPrice = basePrice - priceOffset;
    
    // 호가 단위에 맞춰 가격 조정
    const price = roundToTick(rawPrice, tickSize);
    
    // 수량 생성 (심볼 기반 일관성 유지, 시간에 따라 변동)
    const qtySeed = (seed + i * 2000 + timeSeed * 100) % 1000000;
    const baseQty = 10000 + (qtySeed % 500000);
    // 수량에 시간 기반 변동 추가 (70% ~ 130%)
    const timeVariation = 0.7 + (Math.sin(qtySeed + timeSeed) * 0.6);
    const quantity = Math.floor(baseQty * timeVariation);
    
    buyOrders.push({
      price,
      quantity,
    });
  }
  
  // 가격 순으로 정렬
  sellOrders.sort((a, b) => b.price - a.price); // 높은 가격부터
  buyOrders.sort((a, b) => b.price - a.price); // 높은 가격부터
  
  return { sellOrders, buyOrders };
}

/**
 * 캔들스틱 차트 데이터를 생성합니다
 */
export function generateCandleData(
  symbol: string,
  basePrice: number,
  days: number = 365
): Array<{
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}> {
  const candleData: Array<{
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }> = [];
  
  const seed = symbol.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  let currentClose = basePrice * 0.9; // 시작 가격 (10% 낮게)
  
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    const dateStr = date.toISOString().split("T")[0];
    
    // 트렌드를 basePrice로 향하도록 설정
    const progress = (days - i) / days;
    const targetPrice = basePrice * (0.9 + progress * 0.1);
    
    // 일일 변동성 (2-5%)
    const volatility = basePrice * (0.02 + Math.random() * 0.03);
    
    // 시드 기반 일관된 변동
    const daySeed = (seed + i * 100) % 10000;
    const randomFactor = (Math.sin(daySeed) * 10000) % 1;
    
    const open = i === days - 1 ? currentClose : candleData[candleData.length - 1].close;
    
    // 종가 생성 (트렌드 + 랜덤 변동)
    const trendFactor = (targetPrice - currentClose) * 0.1;
    const randomChange = (randomFactor - 0.5) * volatility * 2;
    const close = Math.max(1000, open + trendFactor + randomChange);
    
    // 고가/저가 생성
    const highVariation = Math.random() * volatility * 0.5;
    const lowVariation = Math.random() * volatility * 0.5;
    const high = Math.max(open, close) + highVariation;
    const low = Math.min(open, close) - lowVariation;
    
    // 거래량 생성
    const volumeSeed = (seed + i * 200) % 1000000;
    const baseVolume = 500000 + (volumeSeed % 2000000);
    const volume = Math.floor(baseVolume * (0.7 + Math.random() * 0.6));
    
    candleData.push({
      date: dateStr,
      open: Math.round(open),
      high: Math.round(high),
      low: Math.round(low),
      close: Math.round(close),
      volume,
    });
    
    currentClose = close;
  }
  
  return candleData;
}

/**
 * 시간 시리즈 데이터를 생성합니다
 */
export function generateTimeSeries(
  symbol: string,
  basePrice: number,
  days: number = 30
): Array<{ date: string; value: number }> {
  const candleData = generateCandleData(symbol, basePrice, days);
  return candleData.map((candle) => ({
    date: candle.date,
    value: candle.close,
  }));
}

