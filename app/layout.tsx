import type { Metadata } from "next";
import "./globals.css";
import DrawerProviderWrapper from "@/components/drawer/DrawerProviderWrapper";
import DrawerPortal from "@/components/drawer/DrawerPortal";
import TopMenuBar from "@/components/layout/TopMenuBar";
import ScrollToTop from "@/components/layout/ScrollToTop";
import QueryProvider from "@/components/providers/QueryProvider";
import { Inter, Outfit } from "next/font/google";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });

export const metadata: Metadata = {
  title: "널스탁",
  description: "",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" className={`${inter.variable} ${outfit.variable}`}>
      <body className="page-transition bg-[#050505] text-white font-inter antialiased">
        <QueryProvider>
          <ScrollToTop />
          <DrawerProviderWrapper>
            <TopMenuBar />
            {children}
            {/* Portal을 사용하여 drawer를 body에 직접 렌더링 - Context 리렌더링 영향 없음 */}
            <DrawerPortal />
          </DrawerProviderWrapper>
        </QueryProvider>
      </body>
    </html>
  );
}
