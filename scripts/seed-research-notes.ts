/**
 * 연구노트 시드 — `lib/notes/notes.ts`의 SEED_NOTES(DB 이관 전 정본)를 ResearchNote 테이블에 넣는다.
 *
 *   npx ts-node --project tsconfig.scripts.json scripts/seed-research-notes.ts            # dry-run(기본)
 *   npx ts-node --project tsconfig.scripts.json scripts/seed-research-notes.ts --apply
 *   npx ts-node --project tsconfig.scripts.json scripts/seed-research-notes.ts --apply --overwrite
 *   npx ts-node --project tsconfig.scripts.json scripts/seed-research-notes.ts --apply --overwrite --slug-prefix=kospi-3y-,kosdaq-3y-
 *
 * - 기본은 dry-run이다. --apply가 있어야 DB에 쓴다.
 * - slug가 이미 있으면 건너뛴다(DB에서 고친 내용을 덮지 않는다). 시드 값으로 덮으려면 --overwrite.
 * - --slug-prefix=a,b가 있으면 그 접두사로 시작하는 노트만 다룬다(다른 노트를 덮지 않도록 범위를 좁힌다).
 * - DATABASE_URL이 가리키는 DB에 바로 쓴다(로컬 .env가 prod를 가리키면 prod에 들어간다).
 * - 새 노트는 이 스크립트가 아니라 DB에 직접 넣는다.
 */
import { PrismaClient } from "@prisma/client";
import { SEED_NOTES } from "../lib/notes/notes";
import { noteToCreateInput } from "../lib/notes/noteRow";

async function main() {
  const apply = process.argv.includes("--apply");
  const overwrite = process.argv.includes("--overwrite");
  const prefixArg = process.argv.find((arg) => arg.startsWith("--slug-prefix="));
  const prefixes = prefixArg ? prefixArg.slice("--slug-prefix=".length).split(",").filter(Boolean) : [];
  const inScope = (slug: string) => prefixes.length === 0 || prefixes.some((prefix) => slug.startsWith(prefix));
  const prisma = new PrismaClient();
  try {
    const existing = new Set((await prisma.researchNote.findMany({ select: { slug: true } })).map((row) => row.slug));
    let created = 0;
    let updated = 0;
    let skipped = 0;
    for (const [index, note] of SEED_NOTES.entries()) {
      if (!inScope(note.slug)) continue;
      const input = noteToCreateInput(note, index);
      if (existing.has(note.slug)) {
        if (!overwrite) {
          skipped += 1;
          continue;
        }
        updated += 1;
        if (apply) {
          const { slug: _slug, ...data } = input;
          await prisma.researchNote.update({ where: { slug: note.slug }, data });
        }
      } else {
        created += 1;
        if (apply) await prisma.researchNote.create({ data: input });
      }
    }
    const scope = prefixes.length ? `, 접두사 ${prefixes.join("·")}` : "";
    console.log(`${apply ? "적용" : "dry-run"}: 신규 ${created} · 덮어쓰기 ${updated} · 건너뜀 ${skipped} (시드 ${SEED_NOTES.length}편${scope})`);
    if (!apply) console.log("DB에 쓰려면 --apply를 붙인다.");
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
