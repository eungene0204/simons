#!/usr/bin/env ts-node
/**
 * 코스피/코스닥 전체 종목 목록을 동기화하는 스크립트
 * 
 * 사용법:
 *   npm run sync-stocks
 *   또는
 *   ts-node scripts/sync-korea-stocks.ts
 */

import { saveStockList, fetchKRXStockList } from '../lib/krx-stocks';
import { StockListItem } from '../types/stock';

/**
 * 한국거래소 공개 데이터에서 종목 목록을 가져옵니다
 */
async function fetchAllStocks(): Promise<StockListItem[]> {
  console.log('Fetching KOSPI and KOSDAQ stock list from KRX...');
  
  // KRX에서 종목 목록 가져오기
  let stocks = await fetchKRXStockList();
  
  // KRX API가 실패하거나 데이터가 없을 경우 기본 종목 목록 사용
  if (stocks.length === 0) {
    console.log('KRX API returned no data, using fallback list...');
    
    const kospiStocks: StockListItem[] = [
    { symbol: '005930', name: '삼성전자', market: 'KOSPI', sector: '정보기술', industry: '반도체' },
    { symbol: '000660', name: 'SK하이닉스', market: 'KOSPI', sector: '정보기술', industry: '반도체' },
    { symbol: '035420', name: 'NAVER', market: 'KOSPI', sector: '정보기술', industry: '인터넷' },
    { symbol: '005380', name: '현대차', market: 'KOSPI', sector: '소비재', industry: '자동차' },
    { symbol: '051910', name: 'LG화학', market: 'KOSPI', sector: '소재', industry: '화학' },
    { symbol: '006400', name: '삼성SDI', market: 'KOSPI', sector: '소재', industry: '전기전자' },
    { symbol: '035720', name: '카카오', market: 'KOSPI', sector: '정보기술', industry: '인터넷' },
    { symbol: '028260', name: '삼성물산', market: 'KOSPI', sector: '소비재', industry: '유통' },
    { symbol: '105560', name: 'KB금융', market: 'KOSPI', sector: '금융', industry: '은행' },
    { symbol: '055550', name: '신한지주', market: 'KOSPI', sector: '금융', industry: '은행' },
    { symbol: '032830', name: '삼성생명', market: 'KOSPI', sector: '금융', industry: '보험' },
    { symbol: '003670', name: '포스코홀딩스', market: 'KOSPI', sector: '소재', industry: '철강' },
    { symbol: '034730', name: 'SK', market: 'KOSPI', sector: '에너지', industry: '정유' },
    { symbol: '096770', name: 'SK이노베이션', market: 'KOSPI', sector: '에너지', industry: '정유' },
    { symbol: '017670', name: 'SK텔레콤', market: 'KOSPI', sector: '통신', industry: '통신' },
  ];
  
  const kosdaqStocks: StockListItem[] = [
    { symbol: '207940', name: '삼성바이오로직스', market: 'KOSDAQ', sector: '헬스케어', industry: '바이오' },
    { symbol: '068270', name: '셀트리온', market: 'KOSDAQ', sector: '헬스케어', industry: '바이오' },
    { symbol: '035900', name: 'JYP Ent.', market: 'KOSDAQ', sector: '소비재', industry: '엔터테인먼트' },
    { symbol: '251270', name: '넷마블', market: 'KOSDAQ', sector: '정보기술', industry: '게임' },
    { symbol: '035760', name: 'CJ ENM', market: 'KOSDAQ', sector: '소비재', industry: '미디어' },
    { symbol: '086790', name: '하나금융지주', market: 'KOSDAQ', sector: '금융', industry: '은행' },
    { symbol: '036570', name: '엔씨소프트', market: 'KOSDAQ', sector: '정보기술', industry: '게임' },
    { symbol: '066570', name: 'LG전자', market: 'KOSDAQ', sector: '소비재', industry: '가전' },
  ];
  
  stocks.push(...kospiStocks, ...kosdaqStocks);
  
  console.log(`Found ${stocks.length} stocks (${kospiStocks.length} KOSPI, ${kosdaqStocks.length} KOSDAQ)`);
  }
  
  return stocks;
}

async function main() {
  try {
    console.log('Starting stock list sync...');
    
    const stocks = await fetchAllStocks();
    
    if (stocks.length === 0) {
      console.warn('No stocks found. Please check the data source.');
      process.exit(1);
    }
    
    await saveStockList(stocks);
    
    console.log(`Successfully saved ${stocks.length} stocks to data/korea-stocks.json`);
    console.log(`KOSPI: ${stocks.filter(s => s.market === 'KOSPI').length}`);
    console.log(`KOSDAQ: ${stocks.filter(s => s.market === 'KOSDAQ').length}`);
  } catch (error) {
    console.error('Error syncing stock list:', error);
    process.exit(1);
  }
}

// 스크립트로 직접 실행될 때만 main 실행
if (require.main === module) {
  main();
}

export { main };

