import { beforeEach, describe, expect, it, vi } from "vitest";

const getOwnershipContext = vi.fn();
const findUnique = vi.fn();
const update = vi.fn();

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: () => getOwnershipContext(),
  isUnauthorizedAccessError: () => false,
}));
vi.mock("@/lib/prisma", () => ({ prisma: { user: { findUnique: (a: any) => findUnique(a), update: (a: any) => update(a) } } }));
vi.mock("@/lib/server/strategyReport", () => ({ REPORT_PLANS: ["PRO", "PREMIUM"] }));
let mailerConfigured = true;
vi.mock("@/lib/server/mailer", () => ({ isMailerConfigured: () => mailerConfigured }));

const { GET, PUT } = await import("./route");

const put = (body: unknown) =>
  PUT(new Request("http://localhost/api/user/strategy-report", { method: "PUT", body: JSON.stringify(body) }));

describe("/api/user/strategy-report", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getOwnershipContext.mockResolvedValue({ userId: 1 });
  });

  it("비로그인은 401", async () => {
    getOwnershipContext.mockResolvedValue({ userId: null });
    expect((await GET()).status).toBe(401);
  });

  it("Free 플랜은 켤 수 없다", async () => {
    findUnique.mockResolvedValue({ email: "a@example.com", planTier: "FREE", strategyReportOptIn: false });
    const res = await put({ optIn: true });
    expect(res.status).toBe(403);
    expect(update).not.toHaveBeenCalled();
  });

  it("게스트 계정은 PREMIUM이어도 켤 수 없다", async () => {
    findUnique.mockResolvedValue({ email: "g@guest.nullstock.im", planTier: "PREMIUM", strategyReportOptIn: false });
    expect((await put({ optIn: true })).status).toBe(403);
  });

  it("Pro는 켤 수 있다", async () => {
    findUnique.mockResolvedValue({ email: "a@example.com", planTier: "PRO", strategyReportOptIn: false });
    const res = await put({ optIn: true });
    expect(res.status).toBe(200);
    expect(update).toHaveBeenCalledWith({ where: { id: 1 }, data: { strategyReportOptIn: true } });
  });

  it("플랜을 내린 뒤에도 끌 수는 있다", async () => {
    findUnique.mockResolvedValue({ email: "a@example.com", planTier: "FREE", strategyReportOptIn: true });
    expect((await put({ optIn: false })).status).toBe(200);
    expect(update).toHaveBeenCalledWith({ where: { id: 1 }, data: { strategyReportOptIn: false } });
  });

  it("메일 발송 계정이 없으면 Pro도 켤 수 없다", async () => {
    mailerConfigured = false;
    findUnique.mockResolvedValue({ email: "a@example.com", planTier: "PRO", strategyReportOptIn: false });
    const res = await put({ optIn: true });
    mailerConfigured = true;
    expect(res.status).toBe(403);
  });

  it("optIn이 불리언이 아니면 400", async () => {
    expect((await put({ optIn: "yes" })).status).toBe(400);
  });
});
