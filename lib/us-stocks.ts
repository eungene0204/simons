// US Stock List Loader
// scripts/backfill_us_stocks.py가 생성하는 data/us-stocks.json을 읽는 유틸리티

import { UsStockListItem } from "@/types/stock";

/**
 * 저장된 미국 종목 목록을 읽어옵니다.
 * 파일이 아직 없으면(백필 미실행) 빈 배열 — 한국 종목 검색은 그대로 동작한다.
 */
export async function loadUsStockList(): Promise<UsStockListItem[]> {
  try {
    const fs = await import('fs/promises');
    const path = await import('path');

    const filePath = path.join(process.cwd(), 'data', 'us-stocks.json');
    const data = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Failed to load US stock list:', error);
    return [];
  }
}

/**
 * 미국 ETF 티커→이름 매핑을 us-etf-master.json에서 읽어옵니다.
 * us-stocks.json은 주식만 담고 있어, ETF 백테스트 거래내역에는
 * 이름 대신 티커(예: SPY)만 노출된다.
 */
export async function loadUsEtfMasterNameMap(): Promise<Record<string, string>> {
  try {
    const fs = await import('fs/promises');
    const path = await import('path');

    const filePath = path.join(process.cwd(), 'data', 'us-etf-master.json');
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
