import type { Language } from "@/lib/i18n";
import { buildHomeJsonLd, serializeJsonLd } from "@/lib/seo/site";

/** 홈 랜딩 전용 JSON-LD(Organization·WebSite·WebApplication). 서버 컴포넌트에서만 렌더한다. */
export function HomeStructuredData({ language }: { language: Language }) {
  return (
    <script
      type="application/ld+json"
      data-testid="home-structured-data"
      dangerouslySetInnerHTML={{ __html: serializeJsonLd(buildHomeJsonLd(language)) }}
    />
  );
}
