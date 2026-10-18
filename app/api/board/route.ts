import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { createHash } from "crypto";
import { prisma } from "@/lib/prisma";
import { requireAdmin } from "@/lib/server/adminAuth";
import { BoardError, categories, reasons, field, password, moderate } from "@/lib/board/rules";
import { cleanup, identity, limit, postFields, publicFields } from "@/lib/board/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const headers = { "Cache-Control": "no-store" };
function json(data: unknown, status = 200) { return NextResponse.json(data, { status, headers }); }
function failure(error: unknown) {
  return json({ error: error instanceof BoardError ? error.message : "처리하지 못했습니다. 잠시 후 다시 시도해 주세요." }, error instanceof BoardError ? error.status : 503);
}
async function visiblePost(id: string) {
  const post = await prisma.boardPost.findFirst({ where: { id, status: "PUBLIC" }, select: postFields });
  if (!post) throw new BoardError("게시글을 찾을 수 없습니다.", 404);
  return post;
}

export async function GET(request: Request) {
  try {
    const params = new URL(request.url).searchParams;
    if (params.get("admin") === "1") {
      if (!await requireAdmin()) return json({ error: "Not Found" }, 404);
      const page = Math.min(10000, Math.max(1, Math.floor(Number(params.get("page")) || 1)));
      const reports = await prisma.boardReport.findMany({ where: { status: "OPEN" }, select: { id: true, postId: true, commentId: true, reason: true, createdAt: true, post: { select: postFields }, comment: { select: publicFields } }, take: 30, skip: (page - 1) * 30, orderBy: { createdAt: "desc" } });
      return json({ reports });
    }
    const id = params.get("id");
    if (id) {
      const commentPage = Math.max(1, Math.min(10000, Math.floor(Number(params.get("commentPage")) || 1)));
      const [post, comments, count] = await Promise.all([
        visiblePost(id),
        prisma.boardComment.findMany({ where: { postId: id, status: "PUBLIC" }, select: publicFields, orderBy: [{ createdAt: "asc" }, { id: "asc" }], skip: (commentPage - 1) * 30, take: 30 }),
        prisma.boardComment.count({ where: { postId: id, status: "PUBLIC" } }),
      ]);
      return json({ post, comments, count });
    }
    const pageValue = Number(params.get("page") || 1);
    const page = Number.isInteger(pageValue) ? Math.max(1, Math.min(10000, pageValue)) : 1;
    const query = (params.get("q") || "").slice(0, 120);
    const category = params.get("category") || "";
    if (category && !categories.includes(category as typeof categories[number])) throw new BoardError("분류가 올바르지 않습니다.");
    const where = { status: "PUBLIC", ...(category ? { category } : {}), ...(query ? { OR: [{ title: { contains: query, mode: "insensitive" as const } }, { body: { contains: query, mode: "insensitive" as const } }] } : {}) };
    const posts = await prisma.boardPost.findMany({ where, select: { ...postFields, _count: { select: { comments: { where: { status: "PUBLIC" } } } } }, orderBy: [{ createdAt: "desc" }, { id: "desc" }], skip: (page - 1) * 20, take: 21 });
    return json({ posts: posts.slice(0, 20), hasNext: posts.length > 20, page });
  } catch (error) { return failure(error); }
}

export async function POST(request: Request) {
  try {
    const origin = request.headers.get("origin");
    if (origin && origin !== new URL(request.url).origin) throw new BoardError("허용되지 않은 요청입니다.", 403);
    if (!request.headers.get("content-type")?.includes("application/json")) throw new BoardError("JSON 요청이 필요합니다.");
    const raw = await request.text();
    if (Buffer.byteLength(raw) > 50000) throw new BoardError("입력 크기를 초과했습니다.", 413);
    let input;
    try { input = JSON.parse(raw); } catch { throw new BoardError("입력이 올바르지 않습니다."); }
    if (!input || typeof input !== "object" || Array.isArray(input)) throw new BoardError("입력이 올바르지 않습니다.");
    if (input.website) throw new BoardError("요청을 처리할 수 없습니다.");
    await cleanup();
    const actor = identity(request);
    await limit("write:" + actor, 40);
    const action = field(input.action, "작업", 20);
    const kind = input.kind === "comment" ? "comment" : "post";
    if (action === "moderate") {
      const admin = await requireAdmin();
      if (!admin) return json({ error: "Not Found" }, 404);
      const id = field(input.id, "ID", 100);
      const reason = field(input.reason, "조치 사유", 500);
      const status = field(input.status, "상태", 10);
      if (!["PUBLIC", "HIDDEN", "DELETED"].includes(status)) throw new BoardError("상태가 올바르지 않습니다.");
      await prisma.$transaction(async (tx) => {
        if (kind === "post") await tx.boardPost.update({ where: { id }, data: { status } });
        else await tx.boardComment.update({ where: { id }, data: { status } });
        await tx.boardReport.updateMany({ where: kind === "post" ? { postId: id } : { commentId: id }, data: { status: "RESOLVED" } });
        await tx.boardAudit.create({ data: { adminId: admin.id, targetId: id, targetType: kind, action: status, reason } });
      });
      return json({ ok: true });
    }
    if (!["create", "update", "delete", "report"].includes(action)) throw new BoardError("작업이 올바르지 않습니다.");
    const id = action === "create" ? undefined : field(input.id, "ID", 100);
    const existing = id ? kind === "post"
      ? await prisma.boardPost.findFirst({ where: { id, status: "PUBLIC" } })
      : await prisma.boardComment.findFirst({ where: { id, status: "PUBLIC", post: { status: "PUBLIC" } } }) : null;
    if (id && !existing) throw new BoardError("콘텐츠를 찾을 수 없습니다.", 404);
    if (action === "report") {
      const reason = field(input.reason, "신고 사유", 20);
      if (!reasons.includes(reason as typeof reasons[number])) throw new BoardError("신고 사유가 올바르지 않습니다.");
      await limit("report:" + actor, 10, 86400);
      await limit("report-target:" + actor + ":" + id, 1, 86400);
      await prisma.boardReport.create({ data: { ...(kind === "post" ? { postId: id } : { commentId: id }), reason, reporter: actor, expiresAt: new Date(Date.now() + 86400000) } });
      return json({ ok: true });
    }
    const secret = password(input.password);
    if (existing) {
      await limit("password:" + actor, 10);
      await limit("password-target:" + id, 30);
      if (!await bcrypt.compare(secret, existing.passwordHash)) throw new BoardError("비밀번호가 올바르지 않습니다.", 403);
    }
    if (action === "delete") {
      const result = kind === "post"
        ? await prisma.boardPost.updateMany({ where: { id, status: "PUBLIC", updatedAt: existing!.updatedAt }, data: { status: "DELETED" } })
        : await prisma.boardComment.updateMany({ where: { id, status: "PUBLIC", updatedAt: existing!.updatedAt }, data: { status: "DELETED" } });
      if (!result.count) throw new BoardError("내용이 변경되었습니다. 새로고침 후 다시 시도해 주세요.", 409);
      return json({ ok: true });
    }
    const nickname = input.nickname === "" || input.nickname === undefined ? "익명" : field(input.nickname, "닉네임", 24);
    const body = field(input.body, "본문", kind === "post" ? 10000 : 2000);
    const title = kind === "post" ? field(input.title, "제목", 120) : "";
    const category = input.category ?? "자유";
    if (kind === "post" && !categories.includes(category)) throw new BoardError("분류가 올바르지 않습니다.");
    moderate(title + "\n" + nickname + "\n" + body);
    const fingerprint = createHash("sha256").update((title + body).normalize("NFKC").replace(/\s/g, "").toLowerCase()).digest("hex");
    const previousTitle = existing && "title" in existing ? existing.title : "";
    if (!existing || existing.body !== body || previousTitle !== title) await limit("duplicate:" + fingerprint, 1, 300);
    const data = { nickname, body, status };
    if (action === "update") {
      const result = kind === "post"
        ? await prisma.boardPost.updateMany({ where: { id, status: "PUBLIC", updatedAt: existing!.updatedAt }, data: { ...data, title, category } })
        : await prisma.boardComment.updateMany({ where: { id, status: "PUBLIC", updatedAt: existing!.updatedAt }, data });
      if (!result.count) throw new BoardError("내용이 변경되었습니다. 새로고침 후 다시 시도해 주세요.", 409);
      return json({ id, status: "PUBLIC" });
    }
    await limit("create:" + actor, 8);
    const passwordHash = await bcrypt.hash(secret, 12);
    if (kind === "comment") {
      const postId = field(input.postId, "게시글 ID", 100);
      await visiblePost(postId);
      const comment = await prisma.boardComment.create({ data: { ...data, passwordHash, postId }, select: { id: true } });
      return json({ ...comment, status: "PUBLIC" }, 201);
    }
    const post = await prisma.boardPost.create({ data: { ...data, title, category, passwordHash }, select: { id: true } });
    return json({ ...post, status: "PUBLIC" }, 201);
  } catch (error) { return failure(error); }
}
