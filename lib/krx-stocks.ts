// KRX Stock List Fetcher
// 한국거래소 코스피/코스닥 종목 목록을 가져오는 유틸리티

export interface StockListItem {
  symbol: string; // 종목 코드 (예: 005930)
  name: string; // 종목명 (예: 삼성전자)
  market: 'KOSPI' | 'KOSDAQ'; // 시장 구분
  sector?: string; // 섹터
  industry?: string; // 업종
  marketCap?: number; // 시가총액
  listedDate?: string; // 상장일
}

/**
 * 한국거래소에서 코스피/코스닥 종목 목록을 가져옵니다
 * KRX 정보데이터시스템 공개 데이터 활용
 */
export async function fetchKRXStockList(): Promise<StockListItem[]> {
  const stocks: StockListItem[] = [];

  try {
    // KRX 정보데이터시스템 공개 데이터 URL
    const baseUrl = 'http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd';
    
    // 코스피 종목 목록
    const kospiParams = new URLSearchParams({
      bld: 'dbms/MDC/STAT/standard/MDCSTAT01501',
      locale: 'ko_KR',
      isuCd: '',
      isuCd2: '',
      strtDd: '',
      endDd: '',
      share: '1',
      money: '1',
    });

    // 코스닥 종목 목록
    const kosdaqParams = new URLSearchParams({
      bld: 'dbms/MDC/STAT/standard/MDCSTAT02501',
      locale: 'ko_KR',
      isuCd: '',
      isuCd2: '',
      strtDd: '',
      endDd: '',
      share: '1',
      money: '1',
    });

    // 코스피 종목 가져오기
    try {
      const kospiResponse = await fetch(`${baseUrl}?${kospiParams.toString()}`, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
      });
      
      if (kospiResponse.ok) {
        const kospiData = await kospiResponse.json();
        if (kospiData.OutBlock_1) {
          kospiData.OutBlock_1.forEach((item: any) => {
            stocks.push({
              symbol: item.ISU_SRT_CD || item.MKT_ID,
              name: item.ISU_ABBRV || item.ISU_NM,
              market: 'KOSPI',
              sector: item.IDX_IND_NM || '',
              industry: item.IDX_IND_CD_NM || '',
            });
          });
        }
      }
    } catch (error) {
      console.error('Failed to fetch KOSPI stocks:', error);
    }

    // 코스닥 종목 가져오기
    try {
      const kosdaqResponse = await fetch(`${baseUrl}?${kosdaqParams.toString()}`, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
      });
      
      if (kosdaqResponse.ok) {
        const kosdaqData = await kosdaqResponse.json();
        if (kosdaqData.OutBlock_1) {
          kosdaqData.OutBlock_1.forEach((item: any) => {
            stocks.push({
              symbol: item.ISU_SRT_CD || item.MKT_ID,
              name: item.ISU_ABBRV || item.ISU_NM,
              market: 'KOSDAQ',
              sector: item.IDX_IND_NM || '',
              industry: item.IDX_IND_CD_NM || '',
            });
          });
        }
      }
    } catch (error) {
      console.error('Failed to fetch KOSDAQ stocks:', error);
    }
    
    return stocks;
  } catch (error) {
    console.error('Failed to fetch KRX stock list:', error);
    return stocks;
  }
}

/**
 * 저장된 종목 목록을 읽어옵니다
 */
export async function loadStockList(): Promise<StockListItem[]> {
  try {
    const fs = await import('fs/promises');
    const path = await import('path');
    
    const filePath = path.join(process.cwd(), 'data', 'korea-stocks.json');
    const data = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Failed to load stock list:', error);
    return [];
  }
}

/**
 * 종목 목록을 파일에 저장합니다
 */
export async function saveStockList(stocks: StockListItem[]): Promise<void> {
  try {
    const fs = await import('fs/promises');
    const path = await import('path');
    
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
  } catch (error) {
    console.error('Failed to save stock list:', error);
    throw error;
  }
}

