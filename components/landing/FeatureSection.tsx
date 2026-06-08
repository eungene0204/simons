"use client";

import {
  Activity,
  ChartLineUp,
  ShieldCheck,
  WarningCircle,
} from "phosphor-react";

const features = [
  {
    icon: Activity,
    title: "자연어 전략 생성",
    description:
      "사람이 말하듯 전략을 작성하면 실행 가능한 전략으로 변환합니다.",
    footer: "Prompt → DSL → Rule Set",
  },
  {
    icon: ChartLineUp,
    title: "즉시 백테스트",
    description: "과거 데이터를 기반으로 전략 성과를 검증합니다.",
    metrics: ["CAGR", "MDD", "Sharpe Ratio", "Calmar Ratio"],
  },
  {
    icon: ShieldCheck,
    title: "AI 전략 코치",
    description: "전략의 위험 요소를 분석하고 개선 방향을 제안합니다.",
    metrics: ["과최적화 위험", "유동성 부족", "거래 빈도 과다", "리스크 과다"],
  },
];

export default function FeatureSection() {
  return (
    <section aria-labelledby="landing-features-title" className="space-y-8">
      <div className="max-w-2xl">
        <p className="text-xs font-bold uppercase tracking-[0.24em] text-gray-500">
          Core Features
        </p>
        <h2
          id="landing-features-title"
          className="mt-3 text-3xl font-black text-white sm:text-4xl"
        >
          전략 생성부터 성과 검증, 리스크 리뷰까지 연결합니다.
        </h2>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {features.map((feature, index) => {
          const Icon = feature.icon;

          return (
            <article
              key={feature.title}
              className="flex h-full flex-col rounded-[28px] border border-white/10 bg-white/[0.03] p-6"
            >
              <div className="flex items-center justify-between">
                <div className="rounded-2xl border border-white/10 bg-black/40 p-3">
                  <Icon className="h-6 w-6 text-white" weight="duotone" />
                </div>
                <span className="text-xs font-bold uppercase tracking-[0.22em] text-gray-500">
                  0{index + 1}
                </span>
              </div>
              <h3 className="mt-6 text-2xl font-bold text-white">
                {feature.title}
              </h3>
              <p className="mt-3 text-sm leading-6 text-gray-300">
                {feature.description}
              </p>

              {feature.metrics ? (
                <div className="mt-6 grid grid-cols-2 gap-2">
                  {feature.metrics.map((metric) => (
                    <div
                      key={metric}
                      className="rounded-2xl border border-white/8 bg-black/40 px-3 py-3 text-sm font-medium text-gray-200"
                    >
                      <span className="inline-flex items-center gap-2">
                        <WarningCircle
                          className="h-4 w-4 text-gray-500"
                          weight="fill"
                        />
                        {metric}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-6 rounded-2xl border border-sky-500/15 bg-sky-500/10 px-4 py-3 text-sm text-sky-100">
                  {feature.footer}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
