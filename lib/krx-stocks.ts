// i18n-ignore-file — 개발자용 폐기 안내(사용자 노출 없음)
// KRX Stock List Fetcher
// 한국거래소 코스피/코스닥 종목 목록을 가져오는 유틸리티

import { StockListItem } from "@/types/stock";

/**
 * ⚠️  DEPRECATED — 이 함수는 사용하지 마세요.
 *
 * KRX 비공식 통계 API(MDCSTAT01501/02501)를 직접 호출하는 방식은
 * 이름-코드 매핑이 잘못 반환되는 문제가 확인되었습니다.
 * (예: 000100이 유한양행이 아닌 엉뚱한 종목으로 매핑)
 *
 * 종목 목록 동기화는 반드시 Python 백엔드의 /sync-stocks endpoint를 사용하세요.
 * 해당 endpoint는 FinanceDataReader(FDR)로 올바른 KRX 데이터를 가져옵니다.
 *
 *   CLI:  python3 scripts/sync_data.py --symbols-only
 *   API:  POST /api/stocks/sync  (백엔드 서버 실행 필요)
 */
export async function fetchKRXStockList(): Promise<StockListItem[]> {
  throw new Error(
    "fetchKRXStockList()는 더 이상 사용되지 않습니다. " +
    "POST /api/stocks/sync 또는 `python3 scripts/sync_data.py --symbols-only`를 사용하세요."
  );
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
 * 종목 코드→이름 매핑을 캐시하여 반환합니다.
 * global 객체에 보관하여 Next.js HMR로 모듈이 재로드되어도 유지되고,
 * 동시에 들어오는 여러 요청이 같은 Promise를 공유하도록 합니다 (deduplication).
 * 종목명은 매일 사명 변경을 반영해 제자리 갱신되므로(backend/scripts/refresh_stock_names.py)
 * 파일 수정 시각이 바뀌면 다시 읽는다 — 프로세스 수명 캐시면 재시작 전까지 옛 이름이 나간다.
 */
declare global {
  // eslint-disable-next-line no-var
  var __stockNameMapCache:
    | { mtimeMs: number; map: Promise<Record<string, string>> }
    | undefined;
}

export async function getStockNameMap(): Promise<Record<string, string>> {
  const fs = await import('fs/promises');
  const path = await import('path');
  let mtimeMs = -1;
  try {
    mtimeMs = (await fs.stat(path.join(process.cwd(), 'data', 'korea-stocks.json'))).mtimeMs;
  } catch {
    // 파일이 없으면 loadStockList가 실패를 기록하고 빈 목록을 돌려준다
  }
  const cached = global.__stockNameMapCache;
  if (cached && cached.mtimeMs === mtimeMs) return cached.map;
  const map = loadStockList().then((stocks) =>
    Object.fromEntries(stocks.map((s) => [s.symbol, s.name]))
  );
  global.__stockNameMapCache = { mtimeMs, map };
  return map;
}

/**
 * 상폐 종목까지 포함한 코드→이름 매핑을 stock-master.json에서 읽어옵니다.
 * korea-stocks.json은 현재 상장분만 담고 있어, 상폐 종목은 이름 대신 코드가 노출된다.
 * (생존편향 제거로 백테스트에 상폐 종목이 편입되므로 거래내역에 이름이 필요함.)
 */
export async function loadStockMasterNameMap(): Promise<Record<string, string>> {
  try {
    const fs = await import('fs/promises');
    const path = await import('path');

    const filePath = path.join(process.cwd(), 'data', 'stock-master.json');
    const data = await fs.readFile(filePath, 'utf-8');
    const parsed = JSON.parse(data) as { stocks?: Array<{ symbol: string; name: string }> };
    const map: Record<string, string> = {};
    (parsed.stocks ?? []).forEach((s) => {
      if (s.symbol && s.name) map[s.symbol] = s.name;
    });
    return map;
  } catch {
    // 파일이 아직 없으면(스크립트 미실행) 빈 맵 — 현재 상장분 이름은 그대로 동작
    return {};
  }
}

/**
 * ETF 코드→이름 매핑을 etf-master.json에서 읽어옵니다.
 * korea-stocks.json / stock-master.json은 주식만 담고 있어, ETF 유니버스 백테스트의
 * 거래내역에는 이름 대신 코드(예: 0151S0, 091160)가 노출된다.
 */
export async function loadEtfMasterNameMap(): Promise<Record<string, string>> {
  try {
    const fs = await import('fs/promises');
    const path = await import('path');

    const filePath = path.join(process.cwd(), 'data', 'etf-master.json');
    const data = await fs.readFile(filePath, 'utf-8');
    const parsed = JSON.parse(data) as { etfs?: Array<{ symbol: string; name: string }> };
    const map: Record<string, string> = {};
    (parsed.etfs ?? []).forEach((e) => {
      if (e.symbol && e.name) map[e.symbol] = e.name;
    });
    return map;
  } catch {
    // 파일이 아직 없으면(백필 미실행) 빈 맵 — 주식 이름은 그대로 동작
    return {};
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

