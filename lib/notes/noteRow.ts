// 연구노트 DB 행 ↔ GuideArticle 변환 — 순수 함수(next·prisma 인스턴스 의존 없음)라 시드 스크립트도 쓴다.

import type { Prisma, ResearchNote } from "@prisma/client";
import type { GuideArticle, GuideFaq, GuideSection } from "../guide/articles";

export function rowToNote(row: ResearchNote): GuideArticle {
  return {
    slug: row.slug,
    title: row.title,
    description: row.description,
    summary: row.summary,
    published: row.published,
    updated: row.updated,
    sections: row.sections as unknown as GuideSection[],
    related: row.related as unknown as string[],
    ...(row.faq ? { faq: row.faq as unknown as GuideFaq[] } : {}),
  };
}

export function noteToCreateInput(note: GuideArticle, sortKey: number): Prisma.ResearchNoteCreateInput {
  return {
    slug: note.slug,
    title: note.title,
    description: note.description,
    summary: note.summary,
    published: note.published,
    updated: note.updated,
    sections: note.sections as unknown as Prisma.InputJsonValue,
    related: note.related as unknown as Prisma.InputJsonValue,
    ...(note.faq ? { faq: note.faq as unknown as Prisma.InputJsonValue } : {}),
    sortKey,
  };
}
