/**
 * 이미 본인 삭제된 계정의 이메일을 해제한다(1회성 백필, 2026-11-18).
 *
 *   npx ts-node --project tsconfig.scripts.json scripts/release-self-deleted-emails.ts [--dry-run]
 *
 * 대상: status=DELETED이고 이메일이 아직 해제되지 않았으며, 관리자 삭제 감사 기록
 * (AdminAuditLog action=USER_DELETE)이 없는 계정 = 본인 삭제 계정.
 * 관리자 삭제(제재) 계정은 건너뛴다 — 원래 이메일을 계속 점유해 재가입을 막는다.
 * 이미 해제된 행은 대상에서 빠지므로 여러 번 돌려도 안전하다.
 */
import { PrismaClient } from "@prisma/client";
import {
  isReleasedDeletedEmail,
  releasedDeletedEmail,
} from "../lib/server/deletedAccountEmail";

const prisma = new PrismaClient();

async function main() {
  const dryRun = process.argv.includes("--dry-run");

  const deleted = await prisma.user.findMany({
    where: { status: "DELETED" },
    select: { id: true, email: true },
  });
  const pending = deleted.filter((u) => !isReleasedDeletedEmail(u.email));

  const adminDeleted = await prisma.adminAuditLog.findMany({
    where: { action: "USER_DELETE", targetUserId: { in: pending.map((u) => u.id) } },
    select: { targetUserId: true },
  });
  const adminDeletedIds = new Set(adminDeleted.map((l) => l.targetUserId));
  const targets = pending.filter((u) => !adminDeletedIds.has(u.id));

  console.log(
    `삭제 계정 ${deleted.length}명 · 미해제 ${pending.length}명 · 관리자 삭제(건너뜀) ${pending.length - targets.length}명 · 해제 대상 ${targets.length}명`
  );
  for (const u of targets) console.log(`  user#${u.id}`);

  if (dryRun || targets.length === 0) {
    console.log(dryRun ? "(dry-run — 쓰지 않음)" : "바꿀 행이 없다.");
    return;
  }

  for (const u of targets) {
    await prisma.user.update({
      where: { id: u.id },
      data: { email: releasedDeletedEmail(u.id, u.email) },
    });
    console.log(`  user#${u.id} 해제 완료`);
  }
  console.log(`${targets.length}명 해제 완료.`);
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(() => prisma.$disconnect());
