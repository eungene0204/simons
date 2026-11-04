/**
 * 연구노트 원본 결과 업로드 — research_classic_techniques.py의 결과 JSON을 ResearchNoteResult에 slug별로 넣는다.
 * 결과 JSON 하나는 한 시장(market, 없으면 KOSPI)의 규칙들이다 — 시장·규칙으로 기록 slug를 찾는다.
 *
 *   npx ts-node -r dotenv/config --project tsconfig.scripts.json scripts/upload-research-note-results.ts <결과 JSON>          # dry-run(기본)
 *   npx ts-node -r dotenv/config --project tsconfig.scripts.json scripts/upload-research-note-results.ts <결과 JSON> --apply
 *
 * - 기본은 dry-run이다. --apply가 있어야 DB에 쓴다(같은 slug는 덮어쓴다 — 원본은 다시 계산한 결과가 정본).
 * - DATABASE_URL이 가리키는 DB에 바로 쓴다(로컬 .env가 prod를 가리키면 prod에 들어간다).
 */
import { readFileSync } from "fs";
import { PrismaClient, type Prisma } from "@prisma/client";
import { classicNoteSlug } from "../lib/notes/classicNotes";

type ResultFile = {
  engine_version: string;
  market?: string;
  rows: Record<string, { request: Prisma.InputJsonObject; result: Prisma.InputJsonObject }>;
  sensitivity?: Record<string, Record<string, Prisma.InputJsonObject>>;
};

async function main() {
  const path = process.argv[2];
  if (!path || path.startsWith("--")) throw new Error("결과 JSON 경로가 필요하다");
  const apply = process.argv.includes("--apply");
  const data = JSON.parse(readFileSync(path, "utf-8")) as ResultFile;
  const rows = Object.entries(data.rows).map(([rule, row]) => {
    const slug = classicNoteSlug(data.market ?? "KOSPI", rule);
    if (!slug) throw new Error(`노트가 없는 규칙: ${rule}`);
    // 시작일별 요약은 규칙 단위로 묶어 둔다 — {시작일: 지표}.
    const sensitivity: Prisma.InputJsonObject = Object.fromEntries(
      Object.entries(data.sensitivity ?? {}).flatMap(([start, byRule]) => (byRule[rule] ? [[start, byRule[rule]]] : [])),
    );
    return { slug, engineVersion: data.engine_version, request: row.request, result: row.result, sensitivity };
  });
  const prisma = new PrismaClient();
  try {
    for (const row of rows) {
      if (apply) {
        const { slug, ...fields } = row;
        await prisma.researchNoteResult.upsert({ where: { slug }, create: row, update: fields });
      }
      console.log(`${row.slug}: 결과 ${JSON.stringify(row.result).length.toLocaleString()}자 · 시작일 ${Object.keys(row.sensitivity).length}개`);
    }
    console.log(`${apply ? "적용" : "dry-run"}: ${rows.length}건 (엔진 v${data.engine_version})`);
    if (!apply) console.log("DB에 쓰려면 --apply를 붙인다.");
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
