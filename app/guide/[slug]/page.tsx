import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { GuideArticlePage } from "@/components/guide/GuideArticlePage";
import { GUIDE_ARTICLES, getGuideArticle, guideArticlePath } from "@/lib/guide/articles";
import { buildOpenGraph } from "@/lib/seo/site";
import { strategyOpenHref } from "@/lib/strategy/strategyOpenLink";

type GuideArticleRouteProps = { params: { slug: string } };

// 목록에 없는 slug는 렌더하지 않고 404 — 빌드 시점에 글 전체를 정적 생성한다.
export const dynamicParams = false;

export function generateStaticParams() {
  return GUIDE_ARTICLES.map((article) => ({ slug: article.slug }));
}

export function generateMetadata({ params }: GuideArticleRouteProps): Metadata {
  const article = getGuideArticle(params.slug);
  if (!article) return {};
  const path = guideArticlePath(article.slug);
  return {
    title: article.title,
    description: article.description,
    openGraph: {
      ...buildOpenGraph("ko", { title: article.title, description: article.description, url: path }),
      type: "article",
      publishedTime: article.published,
      modifiedTime: article.updated,
    },
    alternates: { canonical: path },
  };
}

export default function GuideArticleRoute({ params }: GuideArticleRouteProps) {
  const article = getGuideArticle(params.slug);
  if (!article) notFound();
  // 지표 사전 글은 본문에 인용한 전략 예시 문장을 입력창에 채워 여는 버튼을 단다(utm: guide / 글 slug).
  const openHref = article.openPrompt ? strategyOpenHref(article.openPrompt, "guide", article.slug) : undefined;
  return <GuideArticlePage article={article} openHref={openHref} />;
}
