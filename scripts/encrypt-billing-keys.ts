/**
 * 평문으로 저장된 토스 빌링키를 암호화한다(1회성 백필).
 *
 *   npx ts-node --project tsconfig.scripts.json scripts/encrypt-billing-keys.ts [--dry-run]
 *
 * 이미 `enc:v1:` 접두사가 붙은 행은 건너뛴다 — 여러 번 돌려도 안전하다.
 * FIELD_ENCRYPTION_KEY가 없으면 아무것도 하지 않고 멈춘다.
 */
import { PrismaClient } from "@prisma/client";
import { encryptField, isEncryptedField } from "../lib/server/fieldCrypto";

const prisma = new PrismaClient();

async function main() {
  const dryRun = process.argv.includes("--dry-run");

  const users = await prisma.user.findMany({
    where: { tossBillingKey: { not: null } },
    select: { id: true, tossBillingKey: true },
  });

  const plaintext = users.filter((u) => !isEncryptedField(u.tossBillingKey!));
  console.log(
    `빌링키 보유 ${users.length}명 · 평문 ${plaintext.length}명 · 이미 암호화 ${users.length - plaintext.length}명`
  );

  if (dryRun || plaintext.length === 0) {
    console.log(dryRun ? "(dry-run — 쓰지 않음)" : "바꿀 행이 없다.");
    return;
  }

  for (const user of plaintext) {
    await prisma.user.update({
      where: { id: user.id },
      data: { tossBillingKey: encryptField(user.tossBillingKey!) },
    });
    console.log(`  user#${user.id} 암호화 완료`);
  }
  console.log(`${plaintext.length}명 백필 완료.`);
}

main()
  .catch((err) => {
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => prisma.$disconnect());
