// @ts-nocheck
/**
 * app/api/virtual-account/route.ts 및 [id]/route.ts 회귀 테스트
 *
 * 수정 내용:
 * - VirtualAccount.id에 @default 없음 → create 시 id를 명시적으로 제공해야 함
 * - VirtualAccount.updatedAt에 @default/@updatedAt 없음 → create/update 시 명시적 제공 필요
 * - 위 두 문제로 계좌 개설 시 Prisma 오류 → 계좌가 DB에 저장되지 않는 버그 발생
 *
 * 검증 항목:
 * 1. POST: id(UUID)와 updatedAt(Date)을 명시적으로 create에 전달
 * 2. POST: name/initialAmount/strategyId 없을 때 400 반환
 * 3. POST: 성공 시 매핑된 계좌 반환
 * 4. PATCH: updatedAt을 명시적으로 update에 전달
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ── Prisma mock ──────────────────────────────────────────────────────────────
const mockAccountCreate = vi.fn();
const mockAccountUpdate = vi.fn();
const mockAccountDelete = vi.fn();
const mockAccountFindUnique = vi.fn();
const mockAccountFindMany = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: {
      create: mockAccountCreate,
      update: mockAccountUpdate,
      delete: mockAccountDelete,
      findUnique: mockAccountFindUnique,
      findMany: mockAccountFindMany,
    },
  },
}));

// ── route 핸들러 import (mock 이후) ─────────────────────────────────────────
const { POST, GET } = await import("@/app/api/virtual-account/route");
const { PATCH } = await import("@/app/api/virtual-account/[id]/route");

// ── 헬퍼: Request 생성 ────────────────────────────────────────────────────
function makePostRequest(body: object): Request {
  return new Request("http://localhost/api/virtual-account", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function makePatchRequest(id: string, body: object): Request {
  return new Request(`http://localhost/api/virtual-account/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── 픽스처 ──────────────────────────────────────────────────────────────────
const MOCK_DB_ACCOUNT = {
  id: "test-uuid-1234",
  name: "테스트 계좌",
  initialCash: 1000000,
  currentCash: 1000000,
  strategyId: "strategy-123",
  strategyName: "모멘텀 전략",
  tradingMode: "manual",
  createdAt: new Date("2026-01-01"),
  updatedAt: new Date("2026-01-01"),
  VirtualPosition: [],
};

const VALID_POST_BODY = {
  name: "테스트 계좌",
  initialAmount: 1000000,
  strategyId: "strategy-123",
  strategyName: "모멘텀 전략",
  tradingMode: "manual",
};

// ── POST /api/virtual-account ────────────────────────────────────────────────

describe("POST /api/virtual-account", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAccountCreate.mockResolvedValue(MOCK_DB_ACCOUNT);
  });

  // ── 핵심 회귀: id/updatedAt 명시적 전달 ──────────────────────────────────

  it("create 호출 시 id를 UUID 문자열로 명시적으로 전달해야 함", async () => {
    await POST(makePostRequest(VALID_POST_BODY));

    expect(mockAccountCreate).toHaveBeenCalledOnce();
    const createArg = mockAccountCreate.mock.calls[0][0];

    // id가 존재하고 비어있지 않아야 함
    expect(createArg.data).toHaveProperty("id");
    expect(typeof createArg.data.id).toBe("string");
    expect(createArg.data.id.length).toBeGreaterThan(0);
  });

  it("create 호출 시 UUID 형식의 id를 전달해야 함", async () => {
    await POST(makePostRequest(VALID_POST_BODY));

    const createArg = mockAccountCreate.mock.calls[0][0];
    const uuidRegex =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    expect(createArg.data.id).toMatch(uuidRegex);
  });

  it("create 호출 시 updatedAt을 Date 객체로 명시적으로 전달해야 함", async () => {
    await POST(makePostRequest(VALID_POST_BODY));

    const createArg = mockAccountCreate.mock.calls[0][0];

    // updatedAt이 존재하고 Date 객체여야 함
    expect(createArg.data).toHaveProperty("updatedAt");
    expect(createArg.data.updatedAt).toBeInstanceOf(Date);
  });

  it("create 호출마다 고유한 id가 생성되어야 함", async () => {
    await POST(makePostRequest(VALID_POST_BODY));
    await POST(makePostRequest(VALID_POST_BODY));

    const id1 = mockAccountCreate.mock.calls[0][0].data.id;
    const id2 = mockAccountCreate.mock.calls[1][0].data.id;
    expect(id1).not.toBe(id2);
  });

  // ── 유효성 검사 ────────────────────────────────────────────────────────────

  it("name이 없으면 400 반환", async () => {
    const res = await POST(
      makePostRequest({ initialAmount: 1000000, strategyId: "s-1" })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBeTruthy();
    expect(mockAccountCreate).not.toHaveBeenCalled();
  });

  it("initialAmount가 없으면 400 반환", async () => {
    const res = await POST(
      makePostRequest({ name: "테스트", strategyId: "s-1" })
    );
    expect(res.status).toBe(400);
    expect(mockAccountCreate).not.toHaveBeenCalled();
  });

  it("strategyId가 없으면 400 반환", async () => {
    const res = await POST(
      makePostRequest({ name: "테스트", initialAmount: 1000000 })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBeTruthy();
    expect(mockAccountCreate).not.toHaveBeenCalled();
  });

  // ── 성공 케이스 ────────────────────────────────────────────────────────────

  it("성공 시 200과 매핑된 계좌 반환", async () => {
    const res = await POST(makePostRequest(VALID_POST_BODY));
    expect(res.status).toBe(200);

    const body = await res.json();
    expect(body.id).toBe(MOCK_DB_ACCOUNT.id);
    expect(body.name).toBe(MOCK_DB_ACCOUNT.name);
    expect(body.initialAmount).toBe(MOCK_DB_ACCOUNT.initialCash);
    expect(body.currentBalance).toBe(MOCK_DB_ACCOUNT.currentCash);
  });

  it("성공 시 totalValue(현금 + 포지션)를 포함한 응답 반환", async () => {
    const res = await POST(makePostRequest(VALID_POST_BODY));
    const body = await res.json();

    // 포지션이 없으므로 totalValue = currentCash
    expect(body.totalValue).toBe(MOCK_DB_ACCOUNT.currentCash);
  });

  it("tradingMode 기본값은 manual", async () => {
    const { tradingMode: _tm, ...bodyWithoutMode } = VALID_POST_BODY;
    await POST(makePostRequest(bodyWithoutMode));

    const createArg = mockAccountCreate.mock.calls[0][0];
    expect(createArg.data.tradingMode).toBe("manual");
  });

  // ── Prisma 오류 처리 ────────────────────────────────────────────────────────

  it("Prisma 오류 발생 시 500 반환", async () => {
    mockAccountCreate.mockRejectedValue(new Error("DB connection failed"));

    const res = await POST(makePostRequest(VALID_POST_BODY));
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toBeTruthy();
  });
});

// ── PATCH /api/virtual-account/[id] ─────────────────────────────────────────

describe("PATCH /api/virtual-account/[id]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAccountUpdate.mockResolvedValue(MOCK_DB_ACCOUNT);
  });

  // ── 핵심 회귀: updatedAt 명시적 전달 ──────────────────────────────────────

  it("update 호출 시 updatedAt을 Date 객체로 명시적으로 전달해야 함", async () => {
    await PATCH(makePatchRequest("test-uuid-1234", { tradingMode: "auto" }), {
      params: { id: "test-uuid-1234" },
    });

    expect(mockAccountUpdate).toHaveBeenCalledOnce();
    const updateArg = mockAccountUpdate.mock.calls[0][0];

    expect(updateArg.data).toHaveProperty("updatedAt");
    expect(updateArg.data.updatedAt).toBeInstanceOf(Date);
  });

  it("tradingMode 업데이트 시 해당 값이 전달됨", async () => {
    await PATCH(makePatchRequest("test-uuid-1234", { tradingMode: "auto" }), {
      params: { id: "test-uuid-1234" },
    });

    const updateArg = mockAccountUpdate.mock.calls[0][0];
    expect(updateArg.data.tradingMode).toBe("auto");
    expect(updateArg.where.id).toBe("test-uuid-1234");
  });

  it("currentBalance 업데이트 시 currentCash로 변환되어 전달됨", async () => {
    await PATCH(
      makePatchRequest("test-uuid-1234", { currentBalance: 500000 }),
      { params: { id: "test-uuid-1234" } }
    );

    const updateArg = mockAccountUpdate.mock.calls[0][0];
    expect(updateArg.data.currentCash).toBe(500000);
  });

  it("성공 시 200과 매핑된 계좌 반환", async () => {
    const res = await PATCH(
      makePatchRequest("test-uuid-1234", { tradingMode: "manual" }),
      { params: { id: "test-uuid-1234" } }
    );
    expect(res.status).toBe(200);

    const body = await res.json();
    expect(body.id).toBe(MOCK_DB_ACCOUNT.id);
  });
});
