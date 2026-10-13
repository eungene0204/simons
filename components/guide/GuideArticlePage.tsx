import Link from "next/link";
import {
  GUIDE_BASE_PATH,
  GUIDE_DISCLAIMER,
  GUIDE_TITLE,
  getGuideArticle,
  guideArticlePath,
  type GuideArticle,
} from "@/lib/guide/articles";
import { buildGuideArticleJsonLd } from "@/lib/guide/jsonLd";
import { serializeJsonLd } from "@/lib/seo/site";

// 백테스트 가이드 글 한 편 — 한국어 전용 공개 페이지(서버 컴포넌트). 약관 페이지와 같은 문서형 레이아웃.
export function GuideArticlePage({ article }: { article: GuideArticle }) {
  const related = article.related
    .map((slug) => getGuideArticle(slug))
    .filter((item): item is GuideArticle => item !== undefined);

  return (
    <main className="min-h-[100dvh] bg-[var(--background)] text-white">
      <script
        type="application/ld+json"
        data-testid="guide-structured-data"
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(buildGuideArticleJsonLd(article)) }}
      />
      <section className="border-b border-white/[0.08] px-4 py-10 sm:px-6 sm:py-12">
        <div className="mx-auto max-w-3xl">
          <nav aria-label="경로" className="text-sm font-bold text-gray-400">
            <Link href="/" className="transition-colors hover:text-white">
              널스탁
            </Link>
            <span aria-hidden="true" className="mx-2 text-gray-600">
              /
            </span>
            <Link href={GUIDE_BASE_PATH} className="transition-colors hover:text-white">
              {GUIDE_TITLE}
            </Link>
          </nav>
          <h1 className="mt-8 font-serif text-3xl font-bold tracking-normal text-white sm:text-4xl">
            {article.title}
          </h1>
          <p className="mt-4 text-sm font-bold text-[var(--text-label)]">
            <time dateTime={article.updated}>{article.updated.replace(/-/g, ".")}</time> 업데이트
          </p>
          <p className="mt-6 border-l-2 border-[var(--chat-accent)] pl-4 text-base font-bold leading-8 text-gray-300">
            {article.summary}
          </p>
        </div>
      </section>

      <section className="px-4 py-10 sm:px-6">
        <div className="mx-auto max-w-3xl">
          <nav aria-label="목차" className="border border-white/[0.08] p-5">
            <p className="text-sm font-black text-white">목차</p>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm font-bold text-gray-400">
              {article.sections.map((section, index) => (
                <li key={section.heading}>
                  <a
                    href={`#section-${index + 1}`}
                    className="transition-colors hover:text-white"
                  >
                    {section.heading}
                  </a>
                </li>
              ))}
            </ol>
          </nav>

          <div className="mt-4">
            {article.sections.map((section, index) => (
              <article
                key={section.heading}
                id={`section-${index + 1}`}
                className="scroll-mt-20 border-b border-white/[0.08] py-8"
              >
                <h2 className="text-xl font-black tracking-normal text-white">{section.heading}</h2>
                {section.paragraphs.map((paragraph) => (
                  <p
                    key={paragraph}
                    className="mt-4 text-base font-medium leading-8 text-gray-300"
                  >
                    {paragraph}
                  </p>
                ))}
                {section.bullets && (
                  <ul className="mt-4 list-disc space-y-3 pl-5 text-base font-medium leading-8 text-gray-300 marker:text-gray-600">
                    {section.bullets.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </div>

          <div className="mt-10 flex flex-col gap-4 border border-white/[0.08] p-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm font-bold leading-6 text-gray-300">
              떠오른 전략 아이디어를 문장으로 입력하면 과거 데이터로 백테스트해 볼 수 있습니다.
            </p>
            <Link
              href="/"
              className="inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-xl bg-[var(--chat-accent)] px-4 py-2 text-sm font-bold text-[var(--chat-accent-ink)] transition-colors duration-200 hover:brightness-110 active:translate-y-[1px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent)]/50"
            >
              전략 백테스트하기
            </Link>
          </div>

          {related.length > 0 && (
            <nav aria-label="함께 읽을 글" className="mt-10">
              <h2 className="text-base font-black text-white">함께 읽을 글</h2>
              <ul className="mt-3 divide-y divide-white/[0.06] border-y border-white/[0.06]">
                {related.map((item) => (
                  <li key={item.slug}>
                    <Link
                      href={guideArticlePath(item.slug)}
                      className="block py-3 text-sm font-bold text-gray-300 transition-colors duration-150 hover:bg-white/[0.02] hover:text-white"
                    >
                      {item.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          )}

          <p className="mt-10 text-xs font-bold leading-relaxed text-[var(--text-label)]">{GUIDE_DISCLAIMER}</p>
        </div>
      </section>
    </main>
  );
}
