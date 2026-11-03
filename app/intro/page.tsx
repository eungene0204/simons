import type { Metadata } from "next";
import Image from "next/image";
import { buildOpenGraph } from "@/lib/seo/site";

// 널스탁 소개 이미지(전단지) 한 장을 공개 주소로 보여주는 페이지.
// 원본은 docs/marketing/flyer_intro_dark.html 이고, 여기 쓰는 PNG는 그것을 렌더한 결과다.
const TITLE = "널스탁 소개";
const DESCRIPTION =
  "떠오른 투자 아이디어를 말로 설명하면 과거 데이터로 검증하고 모의투자까지 돌려보는 투자 연구·백테스트 플랫폼, 널스탁 소개.";

export function generateMetadata(): Metadata {
  return {
    title: TITLE,
    description: DESCRIPTION,
    openGraph: buildOpenGraph("ko", { title: TITLE, description: DESCRIPTION, url: "/intro" }),
    alternates: { canonical: "/intro" },
  };
}

export default function IntroPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center bg-[#0E0E0D] px-4 py-8 sm:px-6 sm:py-12">
      {/* 소개 내용이 전부 그림 안에 있으면 검색엔진이 읽을 글이 없다 — 전단지 첫 문구를 글로도 싣는다. */}
      <header className="mb-8 w-full max-w-[1240px] text-center">
        <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{TITLE}</h1>
        <p className="mt-3 text-sm leading-7 text-gray-300 sm:text-base">
          떠오른 투자 아이디어, 과거 데이터로 직접 검증해 보세요. 코딩도, 조건식 문법도 필요 없습니다.
          글로 쓰면 백테스트가 됩니다. 워크포워드와 몬테카를로로 과최적화까지 확인합니다.
        </p>
      </header>
      <Image
        src="/intro.png"
        alt="널스탁 소개 — 자연어로 전략을 입력하면 과거 데이터로 백테스트하고 가상계좌로 모의투자까지 할 수 있는 투자 연구 플랫폼"
        width={2480}
        height={3508}
        priority
        className="h-auto w-full max-w-[1240px] rounded-xl"
      />
      <a
        href="https://www.nullstock.im"
        className="mt-8 text-sm font-semibold tracking-tight text-[#E08B63] hover:underline"
      >
        www.nullstock.im 바로가기
      </a>
    </main>
  );
}
