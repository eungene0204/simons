import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SimulationBrowser } from "@/components/strategy-simulation/SimulationBrowser";
import { getRequestRegion } from "@/lib/geo/server";
import { buildOpenGraph } from "@/lib/seo/site";

const TITLE = "전략 시뮬레이션";
const DESCRIPTION = "공개된 전략의 최근 3년 과거 데이터 백테스트 결과를 로그인 없이 살펴보고, 지표 값을 바꿔 결과가 어떻게 달라지는지 확인합니다.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  openGraph: buildOpenGraph("ko", { title: TITLE, description: DESCRIPTION, url: "/strategy-simulation" }),
  alternates: { canonical: "/strategy-simulation" },
};

// 한국 전략만 다루는 화면이라 미국 지역(/us) 주소로 직접 들어와도 열지 않는다(메뉴도 숨김).
export default function StrategySimulationPage() {
  if (getRequestRegion() === "us") notFound();
  return (
    <main className="flex min-h-[100dvh] flex-col bg-[var(--background)] text-white">
      <section className="border-b border-white/[0.08] px-4 pb-8 pt-24 sm:px-6 sm:pt-28">
        <div className="mx-auto max-w-5xl">
          <h1 className="text-3xl font-black tracking-normal sm:text-4xl">{TITLE}</h1>
          <p className="mt-4 text-sm font-medium leading-7 text-gray-300">{DESCRIPTION}</p>
        </div>
      </section>
      <section className="flex-1 px-4 py-8 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <SimulationBrowser />
        </div>
      </section>
      <footer className="border-t border-white/[0.08] px-4 py-10 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <p className="text-xs font-bold leading-relaxed text-[var(--text-label)]">
            모든 결과는 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다. 카드는 이름순으로 나열되며 성과 순위나 투자 추천이 아닙니다.
          </p>
        </div>
      </footer>
    </main>
  );
}
