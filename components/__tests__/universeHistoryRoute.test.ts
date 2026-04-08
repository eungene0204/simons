// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockLoadUniverseHistory = vi.fn();
const mockGetUniverseOverview = vi.fn();

vi.mock("@/lib/universe-history", () => ({
  loadUniverseHistory: mockLoadUniverseHistory,
  getUniverseOverview: mockGetUniverseOverview,
}));

const { GET } = await import("@/app/api/universe/history/route");

describe("GET /api/universe/history", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("유니버스 이력과 overview를 함께 반환해야 함", async () => {
    mockLoadUniverseHistory.mockResolvedValue({
      updatedAt: "2026-04-07T00:00:00+09:00",
      entries: [{ date: "2026-04-07", totalCount: 2617 }],
    });
    mockGetUniverseOverview.mockResolvedValue({
      currentTotal: 2617,
      currentKospi: 837,
      currentKosdaq: 1780,
      latest: { date: "2026-04-07", totalCount: 2617 },
      recent: [{ date: "2026-04-07", totalCount: 2617 }],
    });

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.updatedAt).toBe("2026-04-07T00:00:00+09:00");
    expect(body.overview.currentTotal).toBe(2617);
    expect(body.latest.date).toBe("2026-04-07");
    expect(body.history).toHaveLength(1);
  });
});
