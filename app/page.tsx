import type { Metadata } from "next";
import StrategyLabPage from "./analytics/page";

export const metadata: Metadata = {
  title: "Simons | 전략연구소",
  description:
    "전략연구소 메인 화면에서 AI 투자 전략을 만들고 백테스트하고 개선하세요.",
  openGraph: {
    title: "Simons | 전략연구소",
    description:
      "전략연구소 메인 화면에서 전략 생성과 백테스트를 바로 시작하세요.",
    type: "website",
  },
};

export default function HomePage() {
  return <StrategyLabPage />;
}
