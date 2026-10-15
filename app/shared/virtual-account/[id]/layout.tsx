import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "공개 가상계좌",
  robots: { index: false, follow: false },
};

export default function SharedVirtualAccountLayout({ children }: { children: ReactNode }) {
  return children;
}
