/**
 * 게스트(테스터) 계정 발급 — PREMIUM 플랜 User 행을 만들고 아이디·비밀번호를 출력한다.
 *
 *   npx ts-node --project tsconfig.scripts.json scripts/create-guest-accounts.ts [--count 10] [--dry-run]
 *
 * - 아이디: guest_ + 네 자리 난수. DB에 이미 있으면 다시 뽑는다.
 * - 비밀번호: 소문자·숫자 5자. 원문은 DB에 남지 않고(bcrypt) 출력과
 *   `guest-accounts.local.json`(gitignore, 누적 기록)에만 적힌다.
 * - 입장은 /guest 페이지(→ /api/guest/login). 콘솔 Users 탭의 '게스트 계정' 필터로 활동을 본다.
 * - DATABASE_URL이 가리키는 DB에 바로 쓴다(로컬 .env가 prod를 가리키면 prod에 생긴다).
 */
import { PrismaClient } from "@prisma/client";
import { existsSync, readFileSync, writeFileSync } from "fs";
import path from "path";
import { hashPassword } from "../lib/auth";
import {
  generateGuestId,
  generateGuestPassword,
  guestEmailFromId,
} from "../lib/server/guestAccounts";

const prisma = new PrismaClient();
const OUTPUT_FILE = path.join(process.cwd(), "guest-accounts.local.json");

type IssuedAccount = { guestId: string; password: string; email: string; createdAt: string };

function argValue(flag: string): string | null {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? (process.argv[index + 1] ?? null) : null;
}

async function pickUnusedGuestId(taken: Set<string>): Promise<string> {
  for (let attempt = 0; attempt < 100; attempt++) {
    const guestId = generateGuestId();
    if (taken.has(guestId)) continue;
    const exists = await prisma.user.findUnique({
      where: { email: guestEmailFromId(guestId) },
      select: { id: true },
    });
    if (!exists) return guestId;
  }
  throw new Error("빈 게스트 아이디를 100회 안에 찾지 못했다.");
}

async function main() {
  const count = Number(argValue("--count") ?? 10);
  const dryRun = process.argv.includes("--dry-run");
  if (!Number.isInteger(count) || count < 1 || count > 100) {
    throw new Error(`--count는 1~100 사이 정수여야 한다: ${count}`);
  }

  const issued: IssuedAccount[] = [];
  const taken = new Set<string>();
  const now = new Date();

  for (let i = 0; i < count; i++) {
    const guestId = await pickUnusedGuestId(taken);
    taken.add(guestId);
    const password = generateGuestPassword();
    const email = guestEmailFromId(guestId);

    if (!dryRun) {
      await prisma.user.create({
        data: {
          email,
          name: guestId,
          password: await hashPassword(password),
          planTier: "PREMIUM",
          planStartDate: now,
          updatedAt: now,
        },
      });
    }
    issued.push({ guestId, password, email, createdAt: now.toISOString() });
  }

  console.log(dryRun ? `(dry-run — 쓰지 않음) ${count}개 미리보기` : `${count}개 발급 완료 (PREMIUM)`);
  console.log("");
  console.log("아이디        비밀번호");
  for (const account of issued) {
    console.log(`${account.guestId}    ${account.password}`);
  }

  if (!dryRun) {
    const previous: IssuedAccount[] = existsSync(OUTPUT_FILE)
      ? JSON.parse(readFileSync(OUTPUT_FILE, "utf8"))
      : [];
    writeFileSync(OUTPUT_FILE, JSON.stringify([...previous, ...issued], null, 2) + "\n");
    console.log("");
    console.log(`기록: ${OUTPUT_FILE}`);
  }
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(() => prisma.$disconnect());
