import type { Metadata, Viewport } from "next";
import "./globals.css";
import TopMenuBar from "@/components/layout/TopMenuBar";
import ScrollToTop from "@/components/layout/ScrollToTop";
import VisualViewportInset from "@/components/layout/VisualViewportInset";
import QueryProvider from "@/components/providers/QueryProvider";
import { OrderAccountProvider } from "@/contexts/OrderAccountContext";
import ChunkErrorRecovery from "@/components/ChunkErrorRecovery";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import { getRequestLanguage } from "@/lib/i18n/server";
import { GoogleAnalytics } from "@next/third-parties/google";

// viewport-fit=cover가 있어야 env(safe-area-inset-*)이 0이 아닌 값을 준다 — 하단 고정 요소가
// iOS 홈 인디케이터 위에 머무는 전제(2026-09-08).
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export function generateMetadata(): Metadata {
  const isGlobal = getRequestLanguage() === "en";
  return {
    metadataBase: new URL(
      process.env.DOMAIN ? `https://${process.env.DOMAIN}` : "https://www.nullstock.im"
    ),
    title: isGlobal
      ? "NullStock | Quantitative Investing Platform for U.S. Stocks"
      : "퀀트 백테스트 | 널스탁",
    description: isGlobal
      ? "Design, backtest, and simulate your own U.S. stock strategies."
      : "나만의 주식 투자 전략을 설계하고 백테스트로 검증하세요.",
  };
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const language = getRequestLanguage();

  return (
    <html lang={language}>
      <body className="page-transition bg-[var(--background)] text-white font-inter antialiased">
        <LanguageProvider initialLanguage={language}>
          <QueryProvider>
            <ChunkErrorRecovery />
            <ScrollToTop />
            <VisualViewportInset />
            <OrderAccountProvider>
              <TopMenuBar />
              {children}
            </OrderAccountProvider>
          </QueryProvider>
        </LanguageProvider>
        {process.env.NEXT_PUBLIC_GA_ID && (
          <GoogleAnalytics gaId={process.env.NEXT_PUBLIC_GA_ID} />
        )}
      </body>
    </html>
  );
}
