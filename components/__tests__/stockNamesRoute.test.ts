// @ts-nocheck
/**
 * GET /api/stocks/names 회귀 테스트
 *
 * 생존편향 제거로 백테스트에 상폐 종목이 편입되는데, korea-stocks.json(현재 상장분)만
 * 보던 이름 맵은 상폐 종목 이름을 못 찾아 거래내역에 코드(예: 042670)가 노출됐다.
 * stock-master.json(상폐 포함)의 이름을 병합해 상폐 종목도 이름이 나오도록 수정.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cache } from "@/lib/cache";

vi.mock("@/lib/krx-stocks", () => ({
  loadStockList: vi.fn().mockResolvedValue([
    { symbol: "005930", name: "삼성전자", sector: "반도체", industry: "반도체", market: "KOSPI" },
  ]),
  loadStockMasterNameMap: vi.fn().mockResolvedValue({
    "005930": "삼성전자",
    "042670": "HD현대인프라코어", // 상폐 — korea-stocks엔 없음
    "115390": "락앤락", // 상폐(인수)
  }),
  loadEtfMasterNameMap: vi.fn().mockResolvedValue({
    "091160": "KODEX 반도체", // ETF — 주식 마스터엔 없음
    "381180": "TIGER 미국필라델피아반도체나스닥",
  }),
}));

const { GET } = await import("@/app/api/stocks/names/route");

async function getMap() {
  const res = await GET(new Request("http://test/api/stocks/names"));
  return res.json();
}

describe("GET /api/stocks/names", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cache.clear();
  });

  it("상폐 종목도 코드가 아니라 이름을 반환한다", async () => {
    const map = await getMap();
    expect(map["042670"]?.name).toBe("HD현대인프라코어");
    expect(map["115390"]?.name).toBe("락앤락");
  });

  it("현재 상장 종목은 sector 등 풍부한 메타가 유지된다 (master 위에 덮어씀)", async () => {
    const map = await getMap();
    expect(map["005930"]).toEqual({ name: "삼성전자", sector: "반도체" });
  });

  it("ETF 종목도 코드가 아니라 이름을 반환한다", async () => {
    const map = await getMap();
    expect(map["091160"]?.name).toBe("KODEX 반도체");
    expect(map["381180"]?.name).toBe("TIGER 미국필라델피아반도체나스닥");
  });
});
