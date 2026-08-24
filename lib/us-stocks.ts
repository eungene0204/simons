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
