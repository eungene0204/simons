import { beforeEach, describe, expect, it, vi } from "vitest";
import { findOwnedAccountId } from "@/lib/server/accountOwnership";
import { refreshVirtualMarket } from "@/lib/server/virtual-market-refresh";
import { POST } from "./route";

vi.mock("@/lib/server/accountOwnership", () => ({
  findOwnedAccountId: vi.fn(),
}));

vi.mock("@/lib/server/virtual-market-refresh", () => ({
  refreshVirtualMarket: vi.fn(),
}));

vi.mock("@/lib/get-user", () => ({
  isUnauthorizedAccessError: () => false,
}));

const mockFindOwnedAccountId = vi.mocked(findOwnedAccountId);
const mockRefresh = vi.mocked(refreshVirtualMarket);

const params = { params: { accountId: "account-1" } };
const request = () =>
  new Request("http://localhost/api/virtual-market/account-1/refresh", { method: "POST" });

describe("/api/virtual-market/[accountId]/refresh 계좌 소유권", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRefresh.mockResolvedValue({ refreshed: true } as any);
  });

  it("남의 계좌는 새로고침하지 않고 404", async () => {
    mockFindOwnedAccountId.mockResolvedValue(null);

    const response = await POST(request(), params);

    expect(response.status).toBe(404);
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it("내 계좌는 그대로 새로고침한다", async () => {
    mockFindOwnedAccountId.mockResolvedValue("account-1");

    const response = await POST(request(), params);

    expect(response.status).toBe(200);
    expect(mockRefresh).toHaveBeenCalledWith("account-1");
  });
});
