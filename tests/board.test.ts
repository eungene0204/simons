import { beforeEach, describe, expect, it, vi } from "vitest";
import { BoardError, field, moderate, password } from "@/lib/board/rules";

const database = vi.hoisted(() => ({
  boardPost: { findFirst: vi.fn(), findMany: vi.fn(), count: vi.fn(), create: vi.fn(), updateMany: vi.fn() },
  boardComment: { findMany: vi.fn(), count: vi.fn(), findFirst: vi.fn(), create: vi.fn(), updateMany: vi.fn() },
  boardReport: { create: vi.fn(), updateMany: vi.fn() },
  boardGuard: { upsert: vi.fn(), deleteMany: vi.fn() },
  $transaction: vi.fn(),
}));
const admin = vi.hoisted(() => vi.fn());
vi.mock("@/lib/prisma", () => ({ prisma: database }));
vi.mock("@/lib/server/adminAuth", () => ({ requireAdmin: admin }));
import { GET, POST } from "@/app/api/board/route";
import bcrypt from "bcryptjs";
import { identity } from "@/lib/board/server";

function request(input: Record<string, unknown>) {
  return new Request("http://localhost/api/board", { method: "POST", headers: { "Content-Type": "application/json", Origin: "http://localhost" }, body: JSON.stringify(input) });
}
const entry = { id: "post1", category: "자유", title: "질문입니다", nickname: "익명", body: "일반적인 본문입니다", status: "PUBLIC", updatedAt: new Date() };
beforeEach(() => {
  vi.resetAllMocks();
  process.env.BOARD_ABUSE_SECRET = "test-secret";
  delete process.env.BOARD_TRUSTED_IP_HEADER;
  database.boardGuard.upsert.mockResolvedValue({ count: 1 });
  database.boardGuard.deleteMany.mockResolvedValue({});
  database.boardReport.updateMany.mockResolvedValue({});
  database.boardPost.create.mockResolvedValue({ id: entry.id });
});

describe("board validation and moderation", () => {
  it("validates limits and bcrypt byte limit", () => {
    expect(() => field("", "제목", 120)).toThrow(BoardError);
    expect(() => field("a".repeat(121), "제목", 120)).toThrow();
    expect(() => password("가".repeat(25))).toThrow();
    expect(password("secure-password")).toBe("secure-password");
  });
  it("uses context and review instead of rejecting every keyword", () => {
    expect(moderate("광고에 대한 질문입니다")).toBe("PUBLIC");
    expect(moderate("카지노 관련 질문입니다")).toBeUndefined();
    expect(() => moderate("무료 가입 https://spam.example")).toThrow();
    expect(() => moderate("외국인을 말살하자")).toThrow();
    expect(() => moderate("<script>alert(1)</script>")).toThrow();
    expect(() => moderate("https://a https://b https://c https://d")).toThrow();
  });
  it("ignores spoofed forwarding headers by default", () => {
    expect(identity(new Request("http://localhost", { headers: { "x-forwarded-for": "1.1.1.1" } }))).toBe(identity(new Request("http://localhost")));
  });
});
describe("board API", () => {
  it("persists a bcrypt hash and does not return it", async () => {
    const response = await POST(request({ action: "create", ...entry, nickname: "", password: "password123" }));
    expect(response.status).toBe(201);
    const stored = database.boardPost.create.mock.calls[0][0].data;
    expect(stored.nickname).toBe("익명");
    expect(await bcrypt.compare("password123", stored.passwordHash)).toBe(true);
    expect(JSON.stringify(await response.json())).not.toContain("password");
  });
  it("rejects wrong passwords before writes", async () => {
    database.boardPost.findFirst.mockResolvedValue({ ...entry, passwordHash: await bcrypt.hash("correct123", 4) });
    const response = await POST(request({ action: "delete", id: entry.id, password: "wrong1234" }));
    expect(response.status).toBe(403);
    expect(database.boardPost.updateMany).not.toHaveBeenCalled();
  });
  it("allows correct password deletion", async () => {
    database.boardPost.findFirst.mockResolvedValue({ ...entry, passwordHash: await bcrypt.hash("correct123", 4) });
    database.boardPost.updateMany.mockResolvedValue({ count: 1 });
    expect((await POST(request({ action: "delete", id: entry.id, password: "correct123" }))).status).toBe(200);
    expect(database.boardPost.updateMany).toHaveBeenCalledWith(expect.objectContaining({ data: { status: "DELETED" } }));
  });
  it("does not expose hidden content", async () => {
    database.boardPost.findFirst.mockResolvedValue(null);
    expect((await GET(new Request("http://localhost/api/board?id=hidden"))).status).toBe(404);
    expect(database.boardPost.findFirst).toHaveBeenCalledWith(expect.objectContaining({ where: { id: "hidden", status: "PUBLIC" } }));
  });
  it("creates comments with a parent foreign key and safe projection", async () => {
    database.boardPost.findFirst.mockResolvedValue(entry);
    database.boardComment.create.mockResolvedValue({ id: "comment1" });
    const response = await POST(request({ action: "create", kind: "comment", postId: entry.id, body: "댓글 내용", password: "password123" }));
    expect(response.status).toBe(201);
    expect(database.boardComment.create).toHaveBeenCalledWith(expect.objectContaining({ data: expect.objectContaining({ postId: entry.id, nickname: "익명" }), select: { id: true } }));
    expect(JSON.stringify(await response.json())).not.toContain("passwordHash");
  });
  it("updates comments only after checking the password", async () => {
    database.boardComment.findFirst.mockResolvedValue({ ...entry, passwordHash: await bcrypt.hash("correct123", 4) });
    database.boardComment.updateMany.mockResolvedValue({ count: 1 });
    const response = await POST(request({ action: "update", kind: "comment", id: "comment1", body: "수정한 댓글", password: "correct123" }));
    expect(response.status).toBe(200);
    expect(database.boardComment.updateMany).toHaveBeenCalledWith(expect.objectContaining({ data: expect.objectContaining({ body: "수정한 댓글" }) }));
  });
  it("requires administrator authentication", async () => {
    admin.mockResolvedValue(null);
    expect((await GET(new Request("http://localhost/api/board?admin=1"))).status).toBe(404);
    expect((await POST(request({ action: "moderate", id: entry.id, status: "PUBLIC", reason: "검토" }))).status).toBe(404);
  });
  it("stores reports and limits repeated reports", async () => {
    database.boardPost.findFirst.mockResolvedValue(entry);
    database.boardReport.create.mockResolvedValue({});
    expect((await POST(request({ action: "report", id: entry.id, reason: "기타" }))).status).toBe(200);
    expect(database.boardReport.create).toHaveBeenCalledWith(expect.objectContaining({ data: expect.objectContaining({ postId: entry.id, reason: "기타" }) }));
    database.boardGuard.upsert.mockResolvedValue({ count: 100 });
    expect((await POST(request({ action: "report", id: entry.id, reason: "기타" }))).status).toBe(429);
  });
  it("rejects honeypots and cross-origin requests", async () => {
    expect((await POST(request({ website: "bot", action: "create" }))).status).toBe(400);
    expect((await POST(new Request("http://localhost/api/board", { method: "POST", headers: { Origin: "https://evil.example" } }))).status).toBe(403);
  });
  it("applies server filters, pagination and explicit public projection", async () => {
    database.boardPost.findMany.mockResolvedValue([]);
    database.boardPost.count.mockResolvedValue(0);
    database.$transaction.mockImplementation(async values => Promise.all(values));
    expect((await GET(new Request("http://localhost/api/board?page=2&category=질문&q=hello"))).status).toBe(200);
    const args = database.boardPost.findMany.mock.calls[0][0];
    expect(args.where).toMatchObject({ status: "PUBLIC", category: "질문", OR: [{ title: { contains: "hello", mode: "insensitive" } }, { body: { contains: "hello", mode: "insensitive" } }] });
    expect(args.skip).toBe(20);
    expect(args.select.passwordHash).toBeUndefined();
    expect(args.select._count.select.comments.where.status).toBe("PUBLIC");
  });
});
