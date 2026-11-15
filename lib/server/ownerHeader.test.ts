import { beforeEach, describe, expect, it, vi } from "vitest";

const getSessionUserId = vi.fn();
vi.mock("@/lib/get-user", () => ({ getSessionUserId: () => getSessionUserId() }));

import { ownerHeader } from "./ownerHeader";

describe("ownerHeader", () => {
  beforeEach(() => getSessionUserId.mockReset());

  it("sends the session user id to the backend", async () => {
    getSessionUserId.mockResolvedValue(42);
    expect(await ownerHeader()).toEqual({ "X-User-Id": "42" });
  });

  it("sends nothing for a visitor who is not logged in", async () => {
    getSessionUserId.mockResolvedValue(null);
    expect(await ownerHeader()).toEqual({});
  });
});
