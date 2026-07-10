// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 결제 주문 생성 가드:
// - 결제 금액은 클라이언트가 아니라 서버의 플랜 정의(lib/plans.ts)에서 계산
// - customerKey는 유추 불가능한 UUID를 사용자당 1회 생성해 재사용

const getCurrentUser = vi.fn();
const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const orderCreate = vi.fn();

vi.mock("@/lib/get-user", () => ({
  getCurrentUser: (...a) => getCurrentUser(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: (...a) => userFindUnique(...a),
      update: (...a) => userUpdate(...a),
    },
    paymentOrder: {
      create: (...a) => orderCreate(...a),
    },
  },
}));

let POST;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ POST } = await import("./route"));
  getCurrentUser.mockResolvedValue({ id: 7, email: "u@example.com", name: "유저" });
  userUpdate.mockResolvedValue({});
  orderCreate.mockImplementation(async ({ data }) => data);
});

function req(body) {
  return { json: async () => body };
}

describe("/api/payment/order", () => {
  it("미로그인 요청은 401", async () => {
    getCurrentUser.mockResolvedValue(null);
    const res = await POST(req({ planId: "PRO" }));
    expect(res.status).toBe(401);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("FREE 플랜은 결제 주문을 만들 수 없다", async () => {
    const res = await POST(req({ planId: "FREE" }));
    expect(res.status).toBe(400);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("잘못된 planId는 400", async () => {
    const res = await POST(req({ planId: "ULTRA" }));
    expect(res.status).toBe(400);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("PRO 주문은 서버 정의 금액(25,000원)으로 생성된다 — 클라이언트 금액 무시", async () => {
    userFindUnique.mockResolvedValue({ tossCustomerKey: "existing-key-1" });
    const res = await POST(req({ planId: "PRO", amount: 100 }));
    expect(res.status).toBe(200);
    const body = await res.json();

    expect(body.amount).toBe(25000);
    expect(body.customerKey).toBe("existing-key-1");
    expect(body.orderName).toBe("널스탁 Pro 플랜 월 이용료");
    expect(orderCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ userId: 7, planId: "PRO", amount: 25000 }),
      })
    );
    // 기존 customerKey가 있으면 새로 만들지 않는다
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("customerKey가 없으면 UUID를 생성해 저장한다 (이메일 등 유추 가능한 값 금지)", async () => {
    userFindUnique.mockResolvedValue({ tossCustomerKey: null });
    const res = await POST(req({ planId: "PREMIUM" }));
    expect(res.status).toBe(200);
    const body = await res.json();

    expect(body.amount).toBe(49000);
    expect(body.customerKey).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
    );
    expect(body.customerKey).not.toBe("u@example.com");
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 7 },
        data: { tossCustomerKey: body.customerKey },
      })
    );
  });
});
