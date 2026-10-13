import Link from "next/link";
import {
  GUIDE_ARTICLES,
  GUIDE_DESCRIPTION,
  GUIDE_DISCLAIMER,
  GUIDE_TITLE,
  guideArticlePath,
} from "@/lib/guide/articles";
import { buildGuideIndexJsonLd } from "@/lib/guide/jsonLd";
import { serializeJsonLd } from "@/lib/seo/site";

// 백테스트 가이드 목록 — 한국어 전용 공개 페이지(서버 컴포넌트).
export function GuideIndexPage() {
  return (
    <main className="min-h-[100dvh] bg-[var(--background)] text-white">
      <script
        type="application/ld+json"
        data-testid="guide-structured-data"
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(buildGuideIndexJsonLd(GUIDE_ARTICLES)) }}
      />
      <section className="border-b border-white/[0.08] px-4 py-10 sm:px-6 sm:py-12">
        <div className="mx-auto max-w-3xl">
          <Link href="/" className="text-sm font-bold text-gray-400 transition-colors hover:text-white">
            널스탁으로 돌아가기
          </Link>
          <h1 className="mt-8 font-serif text-4xl font-bold tracking-normal text-white sm:text-5xl">
            {GUIDE_TITLE}
          </h1>
          <p className="mt-5 text-base font-medium leading-8 text-gray-300">{GUIDE_DESCRIPTION}</p>
        </div>
      </section>

      <section className="px-4 py-10 sm:px-6">
        <div className="mx-auto max-w-3xl">
          <ul className="divide-y divide-white/[0.08] border-y border-white/[0.08]">
            {GUIDE_ARTICLES.map((article) => (
              <li key={article.slug}>
                <Link
                  href={guideArticlePath(article.slug)}
                  className="block py-6 transition-colors duration-150 hover:bg-white/[0.02]"
                >
                  <h2 className="text-xl font-black tracking-normal text-white">{article.title}</h2>
                  <p className="mt-2 text-sm font-medium leading-7 text-gray-400">
                    {article.description}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
          <p className="mt-10 text-xs font-bold leading-relaxed text-[var(--text-label)]">{GUIDE_DISCLAIMER}</p>
        </div>
      </section>
    </main>
  );
}
