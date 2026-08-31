import type { Metadata } from "next";
import "./globals.css";
import TopMenuBar from "@/components/layout/TopMenuBar";
import ScrollToTop from "@/components/layout/ScrollToTop";
import QueryProvider from "@/components/providers/QueryProvider";
import { OrderAccountProvider } from "@/contexts/OrderAccountContext";
import ChunkErrorRecovery from "@/components/ChunkErrorRecovery";
import { LanguageProvider } from "@/lib/i18n/LanguageProvider";
import { getRequestLanguage } from "@/lib/i18n/server";
import { Inter, Outfit } from "next/font/google";
import { GoogleAnalytics } from "@next/third-parties/google";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });

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
    <html lang={language} className={`${inter.variable} ${outfit.variable}`}>
      <body className="page-transition bg-[#050505] text-white font-inter antialiased">
        <LanguageProvider initialLanguage={language}>
          <QueryProvider>
            <ChunkErrorRecovery />
            <ScrollToTop />
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
