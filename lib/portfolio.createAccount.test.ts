import { afterEach, describe, expect, it, vi } from "vitest";

import { createAccount } from "@/lib/portfolio";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("createAccount", () => {
  it("생성 실패 응답을 계좌로 삼지 않고 서버 사유를 던진다", async () => {
    // 조용히 성공처럼 넘기면 사용자에게는 "계좌가 안 만들어진다"로만 보인다.
    stubFetch(
      new Response(
        JSON.stringify({
          error: "Account limit reached",
          message: "현재 플랜의 가상계좌 수 한도에 도달했습니다.",
        }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      )
    );

    await expect(createAccount("계좌", 10_000_000)).rejects.toThrow(
      "현재 플랜의 가상계좌 수 한도에 도달했습니다."
    );
  });

  it("사유 문구가 없는 서버 오류도 실패로 던진다", async () => {
    stubFetch(
      new Response(JSON.stringify({ error: "Failed to create account" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      })
    );

    await expect(createAccount("계좌", 10_000_000)).rejects.toThrow(
      "Failed to create account"
    );
  });

  it("성공 응답은 계좌를 그대로 돌려준다", async () => {
    stubFetch(
      new Response(JSON.stringify({ id: "acc-1", name: "계좌", currency: "USD" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    await expect(createAccount("계좌", 10_000)).resolves.toMatchObject({
      id: "acc-1",
      currency: "USD",
    });
  });
});
