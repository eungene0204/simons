import { describe, expect, it } from "vitest";
import {
  calculateUnreadSignalCount,
  getLatestSignalMarker,
  getSignalReadStorageKey,
} from "@/lib/virtual-market-unread";
import type { VirtualMarketLog } from "@/lib/virtual-market";

const logs: VirtualMarketLog[] = [
  {
    id: "3",
    accountId: "acc-1",
    date: "2026-04-09",
    symbol: "005930",
    stockName: "삼성전자",
    signalType: "entry",
    reason: "돌파",
    price: 70000,
    action: "notified",
    orderId: null,
    createdAt: "2026-04-09T09:03:00.000Z",
  },
  {
    id: "2",
    accountId: "acc-1",
    date: "2026-04-09",
    symbol: "000660",
    stockName: "SK하이닉스",
    signalType: "exit",
    reason: "이탈",
    price: 180000,
    action: "notified",
    orderId: null,
    createdAt: "2026-04-09T09:02:00.000Z",
  },
  {
    id: "1",
    accountId: "acc-1",
    date: "2026-04-09",
    symbol: "035420",
    stockName: "NAVER",
    signalType: "entry",
    reason: null,
    price: 200000,
    action: "auto_executed",
    orderId: "order-1",
    createdAt: "2026-04-09T09:01:00.000Z",
  },
];

describe("virtual-market unread helpers", () => {
  it("계좌별 읽음 저장 키를 안정적으로 생성해야 함", () => {
    expect(getSignalReadStorageKey("abc")).toBe("virtual-market:last-read-log:abc");
  });

  it("마지막 로그 마커는 최신 로그 createdAt 이어야 함", () => {
    expect(getLatestSignalMarker(logs)).toBe("3");
  });

  it("읽음 마커가 없으면 전체 로그를 미확인으로 계산해야 함", () => {
    expect(calculateUnreadSignalCount(logs, null)).toBe(3);
  });

  it("읽음 마커 이후의 로그만 미확인으로 계산해야 함", () => {
    expect(calculateUnreadSignalCount(logs, "1")).toBe(2);
  });

  it("최신 로그를 읽었으면 미확인 개수는 0 이어야 함", () => {
    expect(calculateUnreadSignalCount(logs, "3")).toBe(0);
  });
});
