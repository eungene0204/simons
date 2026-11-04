import type { Metadata } from "next";
import { GuideArticlePage } from "@/components/guide/GuideArticlePage";
import { METHODOLOGY_ARTICLE, METHODOLOGY_COLLECTION, METHODOLOGY_PATH } from "@/lib/methodology/methodology";
import { buildOpenGraph } from "@/lib/seo/site";

// 백테스트 방법론 — 연구노트·가이드가 링크하는 계산 가정·데이터 출처 페이지(비로그인 공개, 한국어 전용).
export const metadata: Metadata = {
  title: METHODOLOGY_ARTICLE.title,
  description: METHODOLOGY_ARTICLE.description,
  openGraph: buildOpenGraph("ko", {
    title: METHODOLOGY_ARTICLE.title,
    description: METHODOLOGY_ARTICLE.description,
    url: METHODOLOGY_PATH,
  }),
  alternates: { canonical: METHODOLOGY_PATH },
};

export default function MethodologyPage() {
  return <GuideArticlePage article={METHODOLOGY_ARTICLE} collection={METHODOLOGY_COLLECTION} />;
}
