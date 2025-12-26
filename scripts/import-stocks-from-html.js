#!/usr/bin/env node
/**
 * HTML 형식의 Excel 파일에서 상장법인 목록을 가져와서 korea-stocks.json을 업데이트하는 스크립트
 * 
 * 사용법:
 *   node scripts/import-stocks-from-html.js /path/to/상장법인목록.xls
 */

const fs = require('fs').promises;
const path = require('path');

/**
 * HTML 파일에서 상장법인 목록을 읽어옵니다
 */
async function readStocksFromHTML(filePath) {
  console.log(`Reading HTML file: ${filePath}`);
  
  // HTML 파일 읽기 (euc-kr 인코딩)
  let html;
  try {
    const iconv = require('iconv-lite');
    const htmlBuffer = await fs.readFile(filePath);
    // euc-kr을 utf-8로 변환
    html = iconv.decode(htmlBuffer, 'euc-kr');
  } catch (e) {
    // iconv-lite가 없으면 시스템 명령어로 변환 시도
    console.log('iconv-lite not found, trying system iconv...');
    const { execSync } = require('child_process');
    try {
      const result = execSync(`iconv -f euc-kr -t utf-8 "${filePath}"`, { 
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024 // 10MB 버퍼
      });
      html = result;
    } catch (iconvError) {
      // 시스템 iconv도 실패하면 직접 변환 시도
      console.log('System iconv failed, trying manual conversion...');
      const buffer = await fs.readFile(filePath);
      // 간단한 euc-kr to utf-8 변환 (완벽하지 않지만 작동할 수 있음)
      html = buffer.toString('utf-8');
      // 만약 여전히 깨지면 원본 파일을 다시 읽어서 시도
      if (html.includes('')) {
        console.log('UTF-8 conversion failed, file may need manual encoding fix');
        throw new Error('Encoding conversion failed. Please install iconv-lite: npm install iconv-lite --save-dev');
      }
    }
  }
  
  // 테이블 데이터 추출
  const tableRegex = /<table[^>]*>([\s\S]*?)<\/table>/i;
  const tableMatch = html.match(tableRegex);
  
  if (!tableMatch) {
    throw new Error('No table found in HTML file');
  }
  
  const tableHtml = tableMatch[1];
  
  // 헤더 찾기
  const headerRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/i;
  const headerMatch = tableHtml.match(headerRegex);
  
  if (!headerMatch) {
    throw new Error('No header row found in table');
  }
  
  const headerHtml = headerMatch[1];
  const headerCells = headerHtml.match(/<th[^>]*>([\s\S]*?)<\/th>/gi) || headerHtml.match(/<td[^>]*>([\s\S]*?)<\/td>/gi) || [];
  
  // 헤더 매핑 찾기
  const headerMap = {};
  headerCells.forEach((cell, index) => {
    const cellText = cell.replace(/<[^>]*>/g, '').trim();
    const cellLower = cellText.toLowerCase();
    
    // 회사명, 종목명, 기업명
    if (cellLower.includes('회사명') || cellLower.includes('종목명') || cellLower.includes('기업명') || 
        cellText.includes('회사명') || cellText.includes('종목명') || cellText.includes('기업명')) {
      headerMap['name'] = index;
    }
    // 종목코드, 코드
    if (cellLower.includes('종목코드') || cellLower.includes('코드') || 
        cellText.includes('종목코드') || cellText.includes('코드')) {
      headerMap['symbol'] = index;
    }
    // 시장, 시장구분
    if (cellLower.includes('시장') || cellLower.includes('시장구분') || 
        cellText.includes('시장') || cellText.includes('시장구분')) {
      headerMap['market'] = index;
    }
    // 업종, 산업
    if (cellLower.includes('업종') || cellLower.includes('산업') || 
        cellText.includes('업종') || cellText.includes('산업')) {
      headerMap['industry'] = index;
    }
    // 섹터, 부문
    if (cellLower.includes('섹터') || cellLower.includes('부문') || 
        cellText.includes('섹터') || cellText.includes('부문')) {
      headerMap['sector'] = index;
    }
  });
  
  // 헤더가 제대로 매핑되지 않았으면 기본 순서 사용
  if (Object.keys(headerMap).length === 0) {
    console.log('Header mapping failed, using default order: 회사명, 시장구분, 종목코드, 업종');
    headerMap['name'] = 0;
    headerMap['market'] = 1;
    headerMap['symbol'] = 2;
    headerMap['industry'] = 3;
  }
  
  console.log('Header mapping:', headerMap);
  
  // 데이터 행 추출
  const rowRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  const rows = [];
  let match;
  
  while ((match = rowRegex.exec(tableHtml)) !== null) {
    const rowHtml = match[1];
    const cells = rowHtml.match(/<td[^>]*>([\s\S]*?)<\/td>/gi) || [];
    
    if (cells.length > 0) {
      rows.push(cells.map(cell => cell.replace(/<[^>]*>/g, '').trim()));
    }
  }
  
  console.log(`Found ${rows.length} data rows`);
  
  // 데이터 파싱
  const stocks = [];
  
  for (const row of rows) {
    if (row.length === 0) continue;
    
    const symbol = headerMap['symbol'] !== undefined ? row[headerMap['symbol']] || '' : '';
    const name = headerMap['name'] !== undefined ? row[headerMap['name']] || '' : '';
    
    // 종목 코드와 이름이 있어야 함
    if (!symbol || !name) continue;
    
    // 종목 코드 정규화 (6자리 숫자)
    const normalizedSymbol = symbol.replace(/[^0-9]/g, '').padStart(6, '0').substring(0, 6);
    if (normalizedSymbol.length !== 6 || normalizedSymbol === '000000') continue;
    
    // 시장 구분
    let market = 'KOSPI';
    if (headerMap['market'] !== undefined) {
      const marketStr = (row[headerMap['market']] || '').toUpperCase();
      if (marketStr.includes('KOSDAQ') || marketStr.includes('코스닥')) {
        market = 'KOSDAQ';
      } else if (marketStr.includes('KOSPI') || marketStr.includes('코스피')) {
        market = 'KOSPI';
      } else {
        // 종목 코드로 판단
        if (normalizedSymbol[0] !== '0' && normalizedSymbol[0] !== '1' && normalizedSymbol[0] !== '2') {
          market = 'KOSDAQ';
        }
      }
    }
    
    // 업종
    const industry = headerMap['industry'] !== undefined 
      ? (row[headerMap['industry']] || '').trim() 
      : undefined;
    
    // 섹터
    const sector = headerMap['sector'] !== undefined 
      ? (row[headerMap['sector']] || '').trim() 
      : undefined;
    
    stocks.push({
      symbol: normalizedSymbol,
      name: name.trim(),
      market: market,
      sector: sector || undefined,
      industry: industry || undefined,
    });
  }
  
  console.log(`Parsed ${stocks.length} stocks from HTML file`);
  
  // 중복 제거 (종목 코드 기준)
  const uniqueStocks = stocks.reduce((acc, stock) => {
    if (!acc.find(s => s.symbol === stock.symbol)) {
      acc.push(stock);
    }
    return acc;
  }, []);
  
  console.log(`After removing duplicates: ${uniqueStocks.length} stocks`);
  
  return uniqueStocks;
}

/**
 * 종목 목록을 파일에 저장합니다
 */
async function saveStockList(stocks) {
  const dataDir = path.join(process.cwd(), 'data');
  
  // data 디렉토리가 없으면 생성
  try {
    await fs.access(dataDir);
  } catch {
    await fs.mkdir(dataDir, { recursive: true });
  }
  
  const filePath = path.join(dataDir, 'korea-stocks.json');
  await fs.writeFile(filePath, JSON.stringify(stocks, null, 2), 'utf-8');
  console.log(`Saved ${stocks.length} stocks to ${filePath}`);
}

async function main() {
  try {
    const htmlFilePath = process.argv[2];
    
    if (!htmlFilePath) {
      console.error('Usage: node scripts/import-stocks-from-html.js <html-file-path>');
      process.exit(1);
    }
    
    // 파일 존재 확인
    try {
      await fs.access(htmlFilePath);
    } catch {
      console.error(`File not found: ${htmlFilePath}`);
      process.exit(1);
    }
    
    console.log('Starting stock list import from HTML...');
    
    // HTML 파일에서 종목 목록 읽기
    const stocks = await readStocksFromHTML(htmlFilePath);
    
    if (stocks.length === 0) {
      console.warn('No stocks found in HTML file. Please check the file format.');
      process.exit(1);
    }
    
    // 종목 목록 저장
    await saveStockList(stocks);
    
    console.log(`\nSuccessfully imported ${stocks.length} stocks from HTML file`);
    console.log(`KOSPI: ${stocks.filter(s => s.market === 'KOSPI').length}`);
    console.log(`KOSDAQ: ${stocks.filter(s => s.market === 'KOSDAQ').length}`);
    console.log(`\nSaved to: data/korea-stocks.json`);
  } catch (error) {
    console.error('Error importing stocks from HTML:', error);
    process.exit(1);
  }
}

// 스크립트로 직접 실행될 때만 main 실행
if (require.main === module) {
  main();
}

module.exports = { main, readStocksFromHTML };

