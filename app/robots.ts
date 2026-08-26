import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const base = process.env.DOMAIN ? `https://${process.env.DOMAIN}` : "https://www.nullstock.im";
  return {
    rules: [{ userAgent: "*", disallow: ["/api/", "/console"] }],
    sitemap: `${base}/sitemap.xml`,
  };
}
