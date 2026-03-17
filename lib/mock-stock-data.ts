/**
 * Mock Stock Data Generator
 * ==========================
 * GBM(Geometric Brownian Motion) 기반으로 실제 주식시장과 유사한 데이터를 생성합니다.
 * - 완전 재현 가능 (seed 기반 PRNG, Math.random() 미사용)
 * - 한국 시장 호가 단위 반영
 * - 시나리오별 시장 국면 지원 (bull / bear / sideways / volatile / crash_recovery / realistic)
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export interface OrderBookItem {
  price: number;
  quantity: number;
}

export interface OrderBookData {
  sellOrders: OrderBookItem[]; // 매도 호가 (높은 가격부터)
  buyOrders: OrderBookItem[];  // 매수 호가 (높은 가격부터)
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

export interface CandleData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type MarketScenario =
  | "bull"
  | "bear"
  | "sideways"
  | "volatile"
  | "crash_recovery"
  | "realistic";

// ─── Seeded PRNG (mulberry32) ────────────────────────────────────────────────
// Math.random() 대신 완전 재현 가능한 PRNG 사용

function mulberry32(seed: number) {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function makePrng(symbolSeed: number, extra: number = 0) {
  return mulberry32((symbolSeed * 1_000_003 + extra * 6_364_136) >>> 0);
}

function symbolSeed(symbol: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < symbol.length; i++) {
    h ^= symbol.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

// ─── Korean Market Constants ─────────────────────────────────────────────────

const DAILY_LIMIT = 0.30; // ±30% 상하한가

function tickSize(price: number): number {
  if (price < 1_000)   return 1;
  if (price < 5_000)   return 5;
  if (price < 10_000)  return 10;
  if (price < 50_000)  return 50;
  if (price < 100_000) return 100;
  if (price < 500_000) return 500;
  return 1_000;
}

function roundToTick(price: number): number {
  const tick = tickSize(price);
  return Math.max(tick, Math.round(price / tick) * tick);
}

// ─── Scenario / Regime Configuration ─────────────────────────────────────────

interface RegimeParams {
  annualDrift: number;  // 연간 drift
  annualVol: number;    // 연간 변동성
}

const REGIME_PARAMS: Record<string, RegimeParams> = {
  bull:      { annualDrift:  0.30, annualVol: 0.18 },
  bear:      { annualDrift: -0.25, annualVol: 0.25 },
  sideways:  { annualDrift:  0.01, annualVol: 0.13 },
  volatile:  { annualDrift:  0.05, annualVol: 0.45 },
  crash:     { annualDrift: -0.70, annualVol: 0.65 },
  recovery:  { annualDrift:  0.25, annualVol: 0.30 },
};

type RegimeName = keyof typeof REGIME_PARAMS;

const SCENARIO_REGIMES: Record<MarketScenario, Array<[number, RegimeName]>> = {
  bull:            [[252, "bull"]],
  bear:            [[252, "bear"]],
  sideways:        [[252, "sideways"]],
  volatile:        [[252, "volatile"]],
  crash_recovery:  [[60, "bull"], [15, "crash"], [177, "recovery"]],
  realistic:       [[50, "bull"], [30, "sideways"], [40, "bear"], [30, "sideways"], [52, "bull"], [50, "sideways"]],
};

function buildRegimeArrays(
  scenario: MarketScenario,
  totalDays: number
): { drifts: number[]; vols: number[] } {
  const drifts = new Array(totalDays).fill(0);
  const vols   = new Array(totalDays).fill(0);
  const regimes = SCENARIO_REGIMES[scenario];

  let idx = 0;
  for (const [regimeDays, regime] of regimes) {
    const end = Math.min(idx + regimeDays, totalDays);
    const { annualDrift, annualVol } = REGIME_PARAMS[regime];
    for (let i = idx; i < end; i++) {
      drifts[i] = annualDrift;
      vols[i]   = annualVol;
    }
    idx = end;
    if (idx >= totalDays) break;
  }

  // 나머지를 마지막 regime으로 채우기
  if (idx < totalDays) {
    const [, lastRegime] = regimes[regimes.length - 1];
    const { annualDrift, annualVol } = REGIME_PARAMS[lastRegime];
    for (let i = idx; i < totalDays; i++) {
      drifts[i] = annualDrift;
      vols[i]   = annualVol;
    }
  }

  return { drifts, vols };
}

// ─── Standard Normal via Box-Muller ──────────────────────────────────────────

function randNormal(rng: () => number): number {
  let u = 0, v = 0;
  while (u === 0) u = rng();
  while (v === 0) v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// ─── GBM Daily Candle Generator ──────────────────────────────────────────────

/**
 * GBM 기반 일봉 캔들 데이터 생성 (완전 재현 가능)
 */
export function generateCandleData(
  symbol: string,
  basePrice: number,
  days: number = 252,
  startDate?: Date,
  scenario: MarketScenario = "realistic"
): CandleData[] {
  const seed = symbolSeed(symbol);
  const rng  = makePrng(seed, days);
  const dt   = 1.0 / 252;

  const { drifts, vols } = buildRegimeArrays(scenario, days);

  // 시작일 계산
  const start = startDate ? new Date(startDate) : (() => {
    const d = new Date();
    d.setDate(d.getDate() - days);
    return d;
  })();

  const candles: CandleData[] = [];
  let prevClose = basePrice;

  for (let i = 0; i < days; i++) {
    const mu    = drifts[i];
    const sigma = vols[i];

    // GBM 스텝
    const z = randNormal(rng);
    const logRet = (mu - 0.5 * sigma * sigma) * dt + sigma * Math.sqrt(dt) * z;
    let close = prevClose * Math.exp(logRet);

    // 상하한가 클리핑
    close = Math.max(prevClose * (1 - DAILY_LIMIT), Math.min(prevClose * (1 + DAILY_LIMIT), close));

    // 시가: 전일 종가 ± 갭
    const gapZ = randNormal(rng);
    let open = prevClose * (1 + 0.005 * gapZ);
    open = Math.max(prevClose * (1 - DAILY_LIMIT), Math.min(prevClose * (1 + DAILY_LIMIT), open));

    // 인트라데이 노이즈로 고/저가
    const intradaySigma = sigma * Math.sqrt(dt) * 0.7;
    const highNoise = Math.abs(randNormal(rng)) * intradaySigma * Math.max(open, close);
    const lowNoise  = Math.abs(randNormal(rng)) * intradaySigma * Math.min(open, close);
    const high = Math.max(open, close) + highNoise;
    const low  = Math.min(open, close) - lowNoise;

    // 거래량: 변동성 클수록 증가
    const absRet = Math.abs(close - prevClose) / prevClose;
    const volBase = basePrice * 500;
    const volNoise = Math.exp(randNormal(rng) * 0.4);
    const volume = Math.max(1000, Math.round(volBase * (1 + 5 * absRet) * volNoise));

    // 날짜 계산 (영업일 근사: 주말 스킵)
    const date = new Date(start);
    let tradingDayCount = 0;
    let calendarDay = 0;
    while (tradingDayCount <= i) {
      const d = new Date(start);
      d.setDate(start.getDate() + calendarDay);
      const dow = d.getDay();
      if (dow !== 0 && dow !== 6) {
        if (tradingDayCount === i) {
          date.setTime(d.getTime());
        }
        tradingDayCount++;
      }
      calendarDay++;
    }

    candles.push({
      date: date.toISOString().split("T")[0],
      open:   roundToTick(open),
      high:   roundToTick(high),
      low:    roundToTick(low),
      close:  roundToTick(close),
      volume,
    });

    prevClose = close;
  }

  return candles;
}

// ─── Intraday (1-second) Price Generator ─────────────────────────────────────

interface IntradayCache {
  prices: number[];
  basePrice: number;
  previousClose: number;
  open: number;
  high: number;
  low: number;
  initialVolume: number;
  incrementPerSecond: number;
  createdAt: number;
}

const intradayCache: Record<string, IntradayCache> = {};

function generateIntradayData(symbol: string, basePrice: number): IntradayCache {
  const seed = symbolSeed(symbol);
  const rng  = makePrng(seed, 9999);

  // 장 시간: 9:00 ~ 15:30 = 23,400초
  const MARKET_SECONDS = 23_400;
  const SIGMA_PER_SEC  = basePrice * 0.00008; // 초당 변동성

  const prevClose = basePrice * (0.995 + rng() * 0.01);
  const open      = prevClose * (1 + (rng() - 0.5) * 0.02);

  let price = open;
  let high  = open;
  let low   = open;
  const prices: number[] = [];

  for (let i = 0; i < MARKET_SECONDS; i++) {
    const z  = randNormal(rng);
    price   += z * SIGMA_PER_SEC;
    // ±5% 범위 내 유지
    price    = Math.max(basePrice * 0.95, Math.min(basePrice * 1.05, price));
    prices.push(roundToTick(price));
    high  = Math.max(high, price);
    low   = Math.min(low, price);
  }

  // 거래량 계산
  const volumeSeed = (seed * 1_007 + 503) % 10_000_000;
  const logVol     = Math.pow(10, (Math.sin(volumeSeed) * 10_000 % 1) * 4 - 1);
  const priceFactor = basePrice > 100_000 ? 0.5 : basePrice > 50_000 ? 0.7 : 1.0;
  const initialVolume = Math.floor(
    (100_000 + (logVol / 1_000) * (100_000_000 - 100_000)) * priceFactor
  );
  const incrementPerSecond = initialVolume * (0.0001 + (volumeSeed % 10) * 0.00001);

  return {
    prices,
    basePrice,
    previousClose: roundToTick(prevClose),
    open:  roundToTick(open),
    high:  roundToTick(high),
    low:   roundToTick(low),
    initialVolume,
    incrementPerSecond,
    createdAt: Date.now(),
  };
}

function getIntradayData(symbol: string, basePrice: number): IntradayCache {
  const key = `${symbol}_${basePrice}`;
  if (!intradayCache[key] || Date.now() - intradayCache[key].createdAt > 86_400_000) {
    intradayCache[key] = generateIntradayData(symbol, basePrice);
  }
  return intradayCache[key];
}

// ─── Korean Stock Base Prices ─────────────────────────────────────────────────

const STOCK_BASE_PRICES: Record<string, number> = {
  "005930": 72_500,   // 삼성전자
  "000660": 142_000,  // SK하이닉스
  "035420": 198_500,  // NAVER
  "035720": 54_600,   // 카카오
  "005380": 234_000,  // 현대차
  "051910": 456_000,  // LG화학
  "006400": 412_000,  // 삼성SDI
  "028260": 123_000,  // 삼성물산
  "105560": 65_000,   // KB금융
  "055550": 45_000,   // 신한지주
  "032830": 89_000,   // 삼성생명
  "003670": 456_000,  // 포스코홀딩스
  "034730": 198_000,  // SK
  "096770": 156_000,  // SK이노베이션
  "017670": 52_000,   // SK텔레콤
  "207940": 890_000,  // 삼성바이오로직스
  "068270": 185_000,  // 셀트리온
  "035900": 65_000,   // JYP Ent.
  "251270": 78_000,   // 넷마블
  "035760": 98_000,   // CJ ENM
  "086790": 52_000,   // 하나금융지주
  "036570": 580_000,  // 엔씨소프트
  "066570": 105_000,  // LG전자
  // 로봇 관련주
  "454910": 45_000,   // 두산로보틱스
  "090710": 32_000,   // 로보티즈
  "056080": 28_000,   // 유진로봇
  "117730": 85_000,   // 티로보틱스
  "058610": 42_000,   // 에스피지
  "277810": 15_000,   // 레인보우로보틱스
  "238490": 18_000,   // 하이로봇
  "208710": 12_000,   // 엔젤로봇
  "270660": 35_000,   // 현대로보틱스
  "090360": 25_000,   // 로보스타
};

export function getBasePrice(symbol: string): number {
  return STOCK_BASE_PRICES[symbol] ?? 50_000;
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * 현재 시각 기준 실시간 주가 반환 (인트라데이 mock)
 */
export function generateRealisticPrice(
  basePrice: number,
  symbol: string,
  timestamp?: number
): number {
  const now  = timestamp ?? Date.now();
  const data = getIntradayData(symbol, basePrice);

  const today = new Date(now);
  today.setHours(9, 0, 0, 0);
  const elapsed = Math.max(0, Math.floor((now - today.getTime()) / 1000));
  const idx = Math.min(elapsed, data.prices.length - 1);
  return data.prices[idx];
}

/**
 * 현재 시각 기준 주가 데이터 반환
 */
export function generateStockPriceData(
  symbol: string,
  basePrice?: number
): StockPriceData {
  const base = basePrice ?? getBasePrice(symbol);
  const data = getIntradayData(symbol, base);
  const now  = Date.now();

  const today = new Date(now);
  today.setHours(9, 0, 0, 0);
  const elapsed = Math.max(0, Math.floor((now - today.getTime()) / 1000));
  const idx = Math.min(elapsed, data.prices.length - 1);
  const currentPrice = data.prices[idx];

  let high = data.open;
  let low  = data.open;
  for (let i = 0; i <= idx; i += 10) {
    const p = data.prices[i];
    high = Math.max(high, p);
    low  = Math.min(low, p);
  }
  high = Math.max(high, currentPrice);
  low  = Math.min(low, currentPrice);

  const volume = Math.floor(data.initialVolume + elapsed * data.incrementPerSecond);
  const change = currentPrice - data.previousClose;
  const changePercent = (change / data.previousClose) * 100;

  return {
    currentPrice,
    previousClose: data.previousClose,
    open:   data.open,
    high:   roundToTick(high),
    low:    roundToTick(low),
    volume,
    change: roundToTick(change),
    changePercent: Math.round(changePercent * 100) / 100,
  };
}

/**
 * 호가창 데이터 생성
 */
export function generateOrderBook(
  symbol: string,
  currentPrice?: number,
  levels: number = 10
): OrderBookData {
  const base = currentPrice ?? generateRealisticPrice(getBasePrice(symbol), symbol);
  const tick = tickSize(base);
  const seed = symbolSeed(symbol);
  const rng  = makePrng(seed, Math.floor(Date.now() / 1000));

  const makeOrders = (direction: 1 | -1): OrderBookItem[] =>
    Array.from({ length: levels }, (_, i) => ({
      price:    roundToTick(base + direction * tick * (i + 1)),
      quantity: Math.max(1000, Math.floor(10_000 + rng() * 490_000)),
    }));

  const sellOrders = makeOrders(1).sort((a, b) => b.price - a.price);
  const buyOrders  = makeOrders(-1).sort((a, b) => b.price - a.price);

  return { sellOrders, buyOrders };
}

/**
 * 시간 시리즈 데이터 반환 (close 기준)
 */
export function generateTimeSeries(
  symbol: string,
  basePrice: number,
  days: number = 30,
  scenario: MarketScenario = "realistic"
): Array<{ date: string; value: number }> {
  return generateCandleData(symbol, basePrice, days, undefined, scenario).map((c) => ({
    date:  c.date,
    value: c.close,
  }));
}
