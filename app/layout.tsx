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
import { t } from "@/lib/i18n";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });

export function generateMetadata(): Metadata {
  return {
    title: getRequestLanguage() === "en" ? "nullstock" : t("널스탁"),
    description: "",
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
      </body>
    </html>
  );
}
