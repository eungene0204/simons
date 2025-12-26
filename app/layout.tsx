import type { Metadata } from "next";
import "./globals.css";
import DrawerProviderWrapper from "@/components/drawer/DrawerProviderWrapper";
import DrawerPortal from "@/components/drawer/DrawerPortal";
import TopMenuBar from "@/components/layout/TopMenuBar";

export const metadata: Metadata = {
  title: "널스탁 - 주식투자 도움",
  description: "주식투자에 도움을 주는 웹사이트",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="page-transition bg-[#0f0f0f] text-white">
        <DrawerProviderWrapper>
          <TopMenuBar />
          {children}
          {/* Portal을 사용하여 drawer를 body에 직접 렌더링 - Context 리렌더링 영향 없음 */}
          <DrawerPortal />
        </DrawerProviderWrapper>
      </body>
    </html>
  );
}
