import { NextRequest, NextResponse } from 'next/server'
import { 
  getMockKoreanIndices, 
  getMockUSIndices,
  getMockJapaneseIndices,
  getMockChineseIndices,
  getMockVIX,
  generateMockTimeSeries, 
  getMockExchangeRate, 
  getMockGoldPrice, 
  getMockOilPrice,
  getMockSilverPrice,
  getMockNaturalGasPrice,
  getMockCopperPrice,
  getMockWheatPrice
} from '@/lib/stock-api/korean-indices'
import { cache } from '@/lib/cache'

export async function GET(request: NextRequest) {
  try {
    // Check cache first
    const cacheKey = 'market:indices:all'
    const cached = cache.get(cacheKey)
    if (cached) {
      console.log('Returning cached indices data')
      return NextResponse.json(cached)
    }

    console.log('Generating mock indices data...')

    // Generate mock data with time series
    const koreanIndices = getMockKoreanIndices()
    const usIndices = getMockUSIndices()
    const japaneseIndices = getMockJapaneseIndices()
    const chineseIndices = getMockChineseIndices()
    const vix = getMockVIX()
    const exchangeRate = getMockExchangeRate()
    const goldPrice = getMockGoldPrice()
    const oilPrice = getMockOilPrice()
    const silverPrice = getMockSilverPrice()
    const naturalGasPrice = getMockNaturalGasPrice()
    const copperPrice = getMockCopperPrice()
    const wheatPrice = getMockWheatPrice()
    
    // Add time series data to all indices
    const response = {
      // Korean indices
      kospi: {
        ...koreanIndices.kospi,
        timeSeries: generateMockTimeSeries(koreanIndices.kospi.value, 30),
      },
      kosdaq: {
        ...koreanIndices.kosdaq,
        timeSeries: generateMockTimeSeries(koreanIndices.kosdaq.value, 30),
      },
      // US indices
      nasdaq: {
        ...usIndices.nasdaq,
        timeSeries: generateMockTimeSeries(usIndices.nasdaq.value, 30),
      },
      dow: {
        ...usIndices.dow,
        timeSeries: generateMockTimeSeries(usIndices.dow.value, 30),
      },
      sp500: {
        ...usIndices.sp500,
        timeSeries: generateMockTimeSeries(usIndices.sp500.value, 30),
      },
      // VIX index
      vix: {
        ...vix,
        timeSeries: generateMockTimeSeries(vix.value, 30),
      },
      // Japanese indices
      nikkei: {
        ...japaneseIndices.nikkei,
        timeSeries: generateMockTimeSeries(japaneseIndices.nikkei.value, 30),
      },
      topix: {
        ...japaneseIndices.topix,
        timeSeries: generateMockTimeSeries(japaneseIndices.topix.value, 30),
      },
      // Chinese indices
      shanghai: {
        ...chineseIndices.shanghai,
        timeSeries: generateMockTimeSeries(chineseIndices.shanghai.value, 30),
      },
      shenzhen: {
        ...chineseIndices.shenzhen,
        timeSeries: generateMockTimeSeries(chineseIndices.shenzhen.value, 30),
      },
      // Exchange rate and commodities
      exchangeRate: {
        ...exchangeRate,
        timeSeries: generateMockTimeSeries(exchangeRate.value, 30),
      },
      goldPrice: {
        ...goldPrice,
        timeSeries: generateMockTimeSeries(goldPrice.value, 30),
      },
      oilPrice: {
        ...oilPrice,
        timeSeries: generateMockTimeSeries(oilPrice.value, 30),
      },
      silverPrice: {
        ...silverPrice,
        timeSeries: generateMockTimeSeries(silverPrice.value, 30),
      },
      naturalGasPrice: {
        ...naturalGasPrice,
        timeSeries: generateMockTimeSeries(naturalGasPrice.value, 30),
      },
      copperPrice: {
        ...copperPrice,
        timeSeries: generateMockTimeSeries(copperPrice.value, 30),
      },
      wheatPrice: {
        ...wheatPrice,
        timeSeries: generateMockTimeSeries(wheatPrice.value, 30),
      },
    }

    // Cache mock data for 30 seconds
    cache.set(cacheKey, response, 30)
    return NextResponse.json(response)
  } catch (error) {
    console.error('Market indices API error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch market indices' },
      { status: 500 }
    )
  }
}
