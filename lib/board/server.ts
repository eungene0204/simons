import { createHmac } from "crypto";
import { isIP } from "net";
import { prisma } from "@/lib/prisma";
import { BoardError } from "./rules";

export const publicFields = { id: true, nickname: true, body: true, createdAt: true, updatedAt: true } as const;
export const postFields = { ...publicFields, title: true, category: true } as const;

export function identity(request: Request): string {
  const secret = process.env.BOARD_ABUSE_SECRET || process.env.JWT_SECRET;
  if (!secret) throw new BoardError("게시판 보안 설정이 필요합니다.", 503);
  const header = process.env.BOARD_TRUSTED_IP_HEADER;
  const candidate = header ? request.headers.get(header)?.trim() : undefined;
  const address = candidate && isIP(candidate) ? candidate : "shared-untrusted";
  return createHmac("sha256", secret).update(new Date().toISOString().slice(0, 10) + ":" + address).digest("hex");
}

export async function limit(key: string, max: number, seconds = 600) {
  const bucket = Math.floor(Date.now() / (seconds * 1000));
  const row = await prisma.boardGuard.upsert({
    where: { key: key + ":" + bucket },
    create: { key: key + ":" + bucket, expiresAt: new Date((bucket + 1) * seconds * 1000) },
    update: { count: { increment: 1 } },
  });
  if (row.count > max) throw new BoardError("요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.", 429);
}

export async function cleanup() {
  await prisma.boardGuard.deleteMany({ where: { expiresAt: { lt: new Date() } } });
  await prisma.boardReport.updateMany({ where: { expiresAt: { lt: new Date() }, reporter: { not: null } }, data: { reporter: null } });
}
