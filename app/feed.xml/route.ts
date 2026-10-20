import { buildGuideRss } from "@/lib/guide/feeds";

export const dynamic = "force-static";

export function GET() {
  return new Response(buildGuideRss(), {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
}
