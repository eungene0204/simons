import type { Metadata } from "next";
import StrategyLabPage from "./analytics/page";

export const metadata: Metadata = {
  title: "nullStock",
  description: "투자 아이디어를 전략으로 만들고 전략을 시뮬레이션 하세요",
  openGraph: {
    title: "nullStock",
    description: "투자 아이디어를 전략으로 만들고 전략을 시뮬레이션 하세요",
    type: "website",
  },
};

export default function HomePage() {
  return <StrategyLabPage />;
}
