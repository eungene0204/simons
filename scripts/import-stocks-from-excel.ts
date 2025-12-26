#!/usr/bin/env ts-node
/**
 * Excel 파일에서 상장법인 목록을 가져와서 korea-stocks.json을 업데이트하는 스크립트
 * 
 * 사용법:
 *   ts-node scripts/import-stocks-from-excel.ts /path/to/상장법인목록.xls
 */

const XLSX = require('xlsx');
import { saveStockList, StockListItem } from '../lib/krx-stocks';
import { promises as fs } from 'fs';
import * as path from 'path';

/**
 * Excel 파일에서 상장법인 목록을 읽어옵니다
 */
async function readStocksFromExcel(filePath: string): Promise<StockListItem[]> {
  console.log(`Reading Excel file: ${filePath}`);
  
  // Excel 파일 읽기
  const workbook = XLSX.readFile(filePath);
  const sheetName = workbook.SheetNames[0]; // 첫 번째 시트 사용
  const worksheet = workbook.Sheets[sheetName];
  
  // JSON으로 변환
  const data = XLSX.utils.sheet_to_json(worksheet, { header: 1 }) as any[][];
  
  console.log(`Found ${data.length} rows in Excel file`);
  
  // 헤더 찾기 (보통 첫 번째 또는 두 번째 행)
  let headerRow = 0;
  const headerKeywords = ['종목코드', '종목명', '회사명', '시장', '시장구분', '업종', '섹터'];
  
  for (let i = 0; i < Math.min(5, data.length); i++) {
    const row = data[i];
    if (Array.isArray(row)) {
      const rowStr = row.map(cell => String(cell || '')).join(' ').toLowerCase();
      if (headerKeywords.some(keyword => rowStr.includes(keyword.toLowerCase()))) {
        headerRow = i;
        break;
      }
    }
  }
  
  console.log(`Header row found at index: ${headerRow}`);
  
  // 헤더 매핑 찾기
  const header = data[headerRow] as string[];
  const headerMap: Record<string, number> = {};
  
  header.forEach((cell, index) => {
    const cellStr = String(cell || '').toLowerCase();
    if (cellStr.includes('종목코드') || cellStr.includes('코드')) {
      headerMap['symbol'] = index;
    }
    if (cellStr.includes('종목명') || cellStr.includes('회사명') || cellStr.includes('기업명')) {
      headerMap['name'] = index;
    }
    if (cellStr.includes('시장') || cellStr.includes('시장구분')) {
      headerMap['market'] = index;
    }
    if (cellStr.includes('업종') || cellStr.includes('산업')) {
      headerMap['industry'] = index;
    }
    if (cellStr.includes('섹터') || cellStr.includes('부문')) {
      headerMap['sector'] = index;
    }
  });
  
  console.log('Header mapping:', headerMap);
  
  // 데이터 파싱
  const stocks: StockListItem[] = [];
  
  for (let i = headerRow + 1; i < data.length; i++) {
    const row = data[i];
    if (!Array.isArray(row) || row.length === 0) continue;
    
    const symbol = headerMap['symbol'] !== undefined ? String(row[headerMap['symbol']] || '').trim() : '';
    const name = headerMap['name'] !== undefined ? String(row[headerMap['name']] || '').trim() : '';
    
    // 종목 코드와 이름이 있어야 함
    if (!symbol || !name) continue;
    
    // 종목 코드 정규화 (6자리 숫자)
    const normalizedSymbol = symbol.replace(/[^0-9]/g, '').padStart(6, '0').substring(0, 6);
    if (normalizedSymbol.length !== 6 || normalizedSymbol === '000000') continue;
    
    // 시장 구분
    let market: 'KOSPI' | 'KOSDAQ' = 'KOSPI';
    if (headerMap['market'] !== undefined) {
      const marketStr = String(row[headerMap['market']] || '').toUpperCase();
      if (marketStr.includes('KOSDAQ') || marketStr.includes('코스닥')) {
        market = 'KOSDAQ';
      } else if (marketStr.includes('KOSPI') || marketStr.includes('코스피')) {
        market = 'KOSPI';
      } else {
        // 종목 코드로 판단 (코스닥은 보통 6자리 숫자이지만, 일부는 구분이 필요)
        // 일반적으로 코스닥은 0으로 시작하지 않는 경우가 많음
        if (normalizedSymbol[0] !== '0' && normalizedSymbol[0] !== '1' && normalizedSymbol[0] !== '2') {
          market = 'KOSDAQ';
        }
      }
    }
    
    // 업종
    const industry = headerMap['industry'] !== undefined 
      ? String(row[headerMap['industry']] || '').trim() 
      : undefined;
    
    // 섹터
    const sector = headerMap['sector'] !== undefined 
      ? String(row[headerMap['sector']] || '').trim() 
      : undefined;
    
    stocks.push({
      symbol: normalizedSymbol,
      name: name,
      market: market,
      sector: sector || undefined,
      industry: industry || undefined,
    });
  }
  
  console.log(`Parsed ${stocks.length} stocks from Excel file`);
  
  // 중복 제거 (종목 코드 기준)
  const uniqueStocks = stocks.reduce((acc, stock) => {
    if (!acc.find(s => s.symbol === stock.symbol)) {
      acc.push(stock);
    }
    return acc;
  }, [] as StockListItem[]);
  
  console.log(`After removing duplicates: ${uniqueStocks.length} stocks`);
  
  return uniqueStocks;
}

async function main() {
  try {
    const excelFilePath = process.argv[2];
    
    if (!excelFilePath) {
      console.error('Usage: ts-node scripts/import-stocks-from-excel.ts <excel-file-path>');
      process.exit(1);
    }
    
    // 파일 존재 확인
    try {
      await fs.access(excelFilePath);
    } catch {
      console.error(`File not found: ${excelFilePath}`);
      process.exit(1);
    }
    
    console.log('Starting stock list import from Excel...');
    
    // Excel 파일에서 종목 목록 읽기
    const stocks = await readStocksFromExcel(excelFilePath);
    
    if (stocks.length === 0) {
      console.warn('No stocks found in Excel file. Please check the file format.');
      process.exit(1);
    }
    
    // 종목 목록 저장
    await saveStockList(stocks);
    
    console.log(`\nSuccessfully imported ${stocks.length} stocks from Excel file`);
    console.log(`KOSPI: ${stocks.filter(s => s.market === 'KOSPI').length}`);
    console.log(`KOSDAQ: ${stocks.filter(s => s.market === 'KOSDAQ').length}`);
    console.log(`\nSaved to: data/korea-stocks.json`);
  } catch (error) {
    console.error('Error importing stocks from Excel:', error);
    process.exit(1);
  }
}

// 스크립트로 직접 실행될 때만 main 실행
if (require.main === module) {
  main();
}

export { main, readStocksFromExcel };

