import type { Metadata } from "next";
import { GuideIndexPage } from "@/components/guide/GuideIndexPage";
import { GUIDE_BASE_PATH, GUIDE_DESCRIPTION, GUIDE_TITLE } from "@/lib/guide/articles";
import { buildOpenGraph } from "@/lib/seo/site";

export function generateMetadata(): Metadata {
  return {
    title: GUIDE_TITLE,
    description: GUIDE_DESCRIPTION,
    openGraph: buildOpenGraph("ko", {
      title: GUIDE_TITLE,
      description: GUIDE_DESCRIPTION,
      url: GUIDE_BASE_PATH,
    }),
    alternates: { canonical: GUIDE_BASE_PATH },
  };
}

export default function GuidePage() {
  return <GuideIndexPage />;
}
