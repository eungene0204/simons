import { Fragment, type ReactNode } from "react";
import Link from "next/link";
import { AdSlot } from "@/components/ads/AdSlot";
import { AD_SLOTS } from "@/lib/ads/adsense";
import {
  GUIDE_COLLECTION,
  getGuideArticle,
  guideArticlePath,
  type ArticleCollection,
  type GuideArticle,
} from "@/lib/guide/articles";
import { buildGuideArticleJsonLd, type BacktestDataset } from "@/lib/guide/jsonLd";
import { METHODOLOGY_PATH } from "@/lib/methodology/methodology";
import { serializeJsonLd } from "@/lib/seo/site";

// 가이드·연구노트 글 한 편 — 한국어 전용 공개 페이지(서버 컴포넌트). 약관 페이지와 같은 문서형 레이아웃.
// 함께 읽을 글은 자기 묶음에서 먼저 찾고, 없으면 가이드에서 찾는다(연구노트 → 가이드 개념 글 연결).
// openHref가 있으면 하단 버튼이 글에 적은 입력 문장을 그대로 채워 여는 링크가 된다(재현).
// headerAction은 요약 아래에 붙는 도구 자리다(연구노트의 로컬 전용 블로그 복사 버튼).
// collection.showsAds면 광고 칸을 둘째 단락 뒤(단락이 셋 이상일 때)와 함께 읽을 글 뒤에 둔다 —
// "이 전략 그대로 열기" 버튼과는 떼어 놓는다(오클릭 유도 배치 금지).
// 넓은 화면(xl 이상)에서는 글 양옆에 160×600 세로 광고가 스크롤을 따라온다 — 본문(max-w-3xl) 밖 여백에만 놓여 글을 가리지 않는다.
const SIDE_AD_SIZE = { width: 160, height: 600 };

export function GuideArticlePage({
  article,
  collection = GUIDE_COLLECTION,
  dataset,
  openHref,
  headerAction,
}: {
  article: GuideArticle;
  collection?: ArticleCollection;
  dataset?: BacktestDataset;
  openHref?: string;
  headerAction?: ReactNode;
}) {
  const related = article.related
    .map((slug) => {
      const own = collection.find(slug);
      if (own) return { slug, title: own.title, href: `${collection.basePath}/${slug}` };
      const guide = getGuideArticle(slug);
      return guide ? { slug, title: guide.title, href: guideArticlePath(slug) } : undefined;
    })
    .filter((item): item is { slug: string; title: string; href: string } => item !== undefined);

  return (
    <main className="relative min-h-[100dvh] bg-[var(--background)] text-white">
      {collection.showsAds && (
        <>
          <div className="absolute inset-y-0 left-[calc(50%_-_26rem_-_160px)] hidden w-[160px] pt-28 xl:block">
            <AdSlot key={`${article.slug}-left`} slot={AD_SLOTS.sideLeft} size={SIDE_AD_SIZE} className="sticky top-24" />
          </div>
          <div className="absolute inset-y-0 right-[calc(50%_-_26rem_-_160px)] hidden w-[160px] pt-28 xl:block">
            <AdSlot key={`${article.slug}-right`} slot={AD_SLOTS.sideRight} size={SIDE_AD_SIZE} className="sticky top-24" />
          </div>
        </>
      )}
      <script
        type="application/ld+json"
        data-testid="guide-structured-data"
        dangerouslySetInnerHTML={{
          __html: serializeJsonLd(buildGuideArticleJsonLd(article, undefined, collection, dataset)),
        }}
      />
      <section className="border-b border-white/[0.08] px-4 pb-10 pt-24 sm:px-6 sm:pb-12 sm:pt-28">
        <div className="mx-auto max-w-3xl">
          <nav aria-label="경로" className="text-sm font-bold text-gray-400">
            <Link href="/" className="transition-colors hover:text-white">
              널스탁
            </Link>
            {collection.basePath && (
              <>
                <span aria-hidden="true" className="mx-2 text-gray-600">
                  /
                </span>
                <Link href={collection.basePath} className="transition-colors hover:text-white">
                  {collection.title}
                </Link>
              </>
            )}
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
          {collection.summaryNote && (
            <p className="mt-3 pl-4 text-sm font-bold text-[var(--text-label)]">{collection.summaryNote}</p>
          )}
          {headerAction}
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
              <Fragment key={section.heading}>
              <article
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
                {section.table && (
                  <div className="mt-5 overflow-x-auto">
                    <table className="w-full min-w-[32rem] border-collapse text-sm">
                      <caption className="pb-2 text-left text-sm font-black text-white">{section.table.caption}</caption>
                      <thead>
                        <tr className="border-y border-white/[0.12] text-gray-400">
                          {section.table.headers.map((header) => (
                            <th key={header} scope="col" className="px-3 py-2 text-right font-bold first:text-left">
                              {header}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {section.table.rows.map((row) => (
                          <tr key={row.join("|")} className="border-b border-white/[0.06] text-gray-300">
                            {row.map((cell, index) => (
                              <td
                                key={`${section.table?.headers[index]}-${cell}`}
                                className="px-3 py-2 text-right font-medium tabular-nums first:text-left first:font-bold"
                              >
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {section.table.footnote && (
                      <p className="mt-2 text-xs font-bold leading-relaxed text-[var(--text-label)]">
                        {section.table.footnote}
                      </p>
                    )}
                  </div>
                )}
                {section.bullets && (
                  <ul className="mt-4 list-disc space-y-3 pl-5 text-base font-medium leading-8 text-gray-300 marker:text-gray-600">
                    {section.bullets.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
              </article>
              {collection.showsAds && index === 1 && article.sections.length > 2 && (
                <AdSlot key={`${article.slug}-mid`} slot={AD_SLOTS.articleMid} className="py-8" />
              )}
              </Fragment>
            ))}
          </div>

          {article.faq && article.faq.length > 0 && (
            <section aria-labelledby="guide-faq-heading" className="mt-10">
              <h2 id="guide-faq-heading" className="text-xl font-black tracking-normal text-white">
                자주 묻는 질문
              </h2>
              <dl className="mt-4 divide-y divide-white/[0.06] border-y border-white/[0.06]">
                {article.faq.map((item) => (
                  <div key={item.question} className="py-5">
                    <dt className="text-base font-black text-white">{item.question}</dt>
                    <dd className="mt-2 text-base font-medium leading-8 text-gray-300">{item.answer}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <div className="mt-10 flex flex-col gap-4 border border-white/[0.08] p-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm font-bold leading-6 text-gray-300">
              {openHref
                ? "이 글에 적은 입력 문장을 전략 입력창에 채워 같은 규칙으로 다시 계산해 볼 수 있습니다."
                : "떠오른 전략 아이디어를 문장으로 입력하면 과거 데이터로 백테스트해 볼 수 있습니다."}
            </p>
            <Link
              href={openHref ?? "/"}
              className="inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-xl bg-[var(--chat-accent)] px-4 py-2 text-sm font-bold text-[var(--chat-accent-ink)] transition-colors duration-200 hover:brightness-110 active:translate-y-[1px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent)]/50"
            >
              {openHref ? "이 전략 그대로 열기" : "전략 백테스트하기"}
            </Link>
          </div>

          {collection.linksMethodology && (
            <p className="mt-6 text-sm font-bold leading-6 text-gray-400">
              데이터 출처와 수수료·세금·체결 가정은{" "}
              <Link href={METHODOLOGY_PATH} className="text-gray-200 underline underline-offset-4 hover:text-white">
                백테스트 방법론
              </Link>
              에 정리했습니다.
            </p>
          )}

          {related.length > 0 && (
            <nav aria-label="함께 읽을 글" className="mt-10">
              <h2 className="text-base font-black text-white">함께 읽을 글</h2>
              <ul className="mt-3 divide-y divide-white/[0.06] border-y border-white/[0.06]">
                {related.map((item) => (
                  <li key={item.slug}>
                    <Link
                      href={item.href}
                      className="block py-3 text-sm font-bold text-gray-300 transition-colors duration-150 hover:bg-white/[0.02] hover:text-white"
                    >
                      {item.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          )}

          {collection.showsAds && (
            <AdSlot key={`${article.slug}-end`} slot={AD_SLOTS.articleEnd} className="mt-10" />
          )}

          <p className="mt-10 text-xs font-bold leading-relaxed text-[var(--text-label)]">{collection.disclaimer}</p>
        </div>
      </section>
    </main>
  );
}
