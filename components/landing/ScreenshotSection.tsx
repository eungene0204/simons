"use client";

import {
  ArrowsOutCardinal,
  ChartBar,
  ChatCircleDots,
  Command,
} from "phosphor-react";

const placeholders = [
  {
    title: "전략 생성 화면",
    description: "자연어 입력을 전략 DSL과 블록으로 구조화하는 메인 워크스페이스",
    icon: Command,
    accent: "from-sky-500/20 to-transparent",
  },
  {
    title: "백테스트 결과 화면",
    description: "CAGR, MDD, Sharpe Ratio를 중심으로 성과를 해석하는 결과 패널",
    icon: ChartBar,
    accent: "from-emerald-500/20 to-transparent",
  },
  {
    title: "AI 코치 화면",
    description: "전략 리스크와 개선 포인트를 요약하는 대화형 코치 패널",
    icon: ChatCircleDots,
    accent: "from-cyan-500/20 to-transparent",
  },
  {
    title: "종목 분석 화면",
    description: "개별 종목의 펀더멘털, 뉴스, 시나리오를 함께 보는 분석 화면",
    icon: ArrowsOutCardinal,
    accent: "from-blue-500/20 to-transparent",
  },
];

function ScreenshotPlaceholder({
  title,
  description,
  accent,
  icon: Icon,
}: (typeof placeholders)[number]) {
  return (
    <div className="relative overflow-hidden rounded-[28px] border border-white/10 bg-[#080808] p-5">
      <div className={`absolute inset-0 bg-gradient-to-br ${accent}`} />
      <div className="relative">
        <div className="flex items-center justify-between">
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
            <Icon className="h-5 w-5 text-white" weight="duotone" />
          </div>
          <span className="text-xs font-bold uppercase tracking-[0.24em] text-gray-500">
            Placeholder
          </span>
        </div>
        <div className="mt-6 rounded-[22px] border border-white/10 bg-black/50 p-4">
          <div className="grid gap-3">
            <div className="flex gap-2">
              <div className="h-2 w-10 rounded-full bg-white/10" />
              <div className="h-2 w-20 rounded-full bg-white/5" />
            </div>
            <div className="grid grid-cols-[1.1fr_0.9fr] gap-3">
              <div className="rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                <div className="h-24 rounded-xl bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.02))]" />
              </div>
              <div className="space-y-3 rounded-2xl border border-white/8 bg-white/[0.04] p-3">
                <div className="h-4 w-2/3 rounded-full bg-white/10" />
                <div className="h-12 rounded-xl bg-white/[0.03]" />
                <div className="h-12 rounded-xl bg-white/[0.03]" />
              </div>
            </div>
          </div>
        </div>
        <h3 className="mt-5 text-xl font-bold text-white">{title}</h3>
        <p className="mt-2 text-sm leading-6 text-gray-300">{description}</p>
      </div>
    </div>
  );
}

export default function ScreenshotSection() {
  return (
    <section aria-labelledby="landing-screenshots-title" className="space-y-8">
      <div className="max-w-2xl">
        <p className="text-xs font-bold uppercase tracking-[0.24em] text-gray-500">
          Product Preview
        </p>
        <h2
          id="landing-screenshots-title"
          className="mt-3 text-3xl font-black text-white sm:text-4xl"
        >
          실제 서비스 화면이 들어갈 자리를 먼저 설계했습니다.
        </h2>
        <p className="mt-3 text-base leading-7 text-gray-300">
          현재는 Placeholder 컴포넌트로 구성되어 있으며, 실제 스크린샷 자산만
          연결하면 그대로 운영에 사용할 수 있습니다.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {placeholders.map((placeholder) => (
          <ScreenshotPlaceholder key={placeholder.title} {...placeholder} />
        ))}
      </div>
    </section>
  );
}
