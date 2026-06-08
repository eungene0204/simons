"use client";

import { CheckCircle, Sparkle, TrendUp } from "phosphor-react";
import GoogleLoginButton from "./GoogleLoginButton";

const valuePoints = [
  "자연어로 전략 아이디어를 입력",
  "전략 DSL과 백테스트를 즉시 생성",
  "AI 코치로 리스크와 개선 포인트 확인",
];

export default function HeroSection() {
  return (
    <section
      aria-labelledby="landing-hero-title"
      className="relative overflow-hidden rounded-[32px] border border-white/10 bg-[#0a0a0a] px-5 py-8 sm:px-8 sm:py-12 lg:px-12 lg:py-16"
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.18),transparent_32%),radial-gradient(circle_at_top_right,rgba(16,185,129,0.12),transparent_28%)]" />
      <div className="relative grid gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)] lg:items-end">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] font-bold uppercase tracking-[0.24em] text-gray-300">
            <Sparkle className="h-3.5 w-3.5 text-sky-400" weight="fill" />
            AI Investment Research Platform
          </div>
          <h1
            id="landing-hero-title"
            className="mt-6 text-4xl font-black leading-[1.05] text-white sm:text-5xl lg:text-6xl"
          >
            AI가 투자 전략을 설계하고
            <br />
            백테스트하고
            <br />
            검증합니다.
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-gray-300 sm:text-lg">
            몇 분 안에 투자 전략을 만들고, 과거 데이터를 기반으로 검증하고,
            AI 코치의 조언을 받아 개선할 수 있습니다.
          </p>
          <div className="mt-8 flex flex-col items-start gap-4">
            <GoogleLoginButton />
            <div className="flex flex-wrap items-center gap-3 text-sm text-gray-300">
              <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1">
                <CheckCircle className="h-4 w-4 text-emerald-400" weight="fill" />
                무료 전략 생성
              </span>
              <span className="inline-flex items-center gap-2 rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1">
                <CheckCircle className="h-4 w-4 text-sky-400" weight="fill" />
                무료 백테스트 제공
              </span>
            </div>
          </div>
        </div>

        <div className="rounded-[28px] border border-white/10 bg-white/[0.03] p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between border-b border-white/10 pb-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-gray-500">
                Research Flow
              </p>
              <p className="mt-2 text-lg font-bold text-white">
                아이디어에서 검증까지 한 화면
              </p>
            </div>
            <div className="rounded-full border border-sky-500/20 bg-sky-500/10 p-3">
              <TrendUp className="h-5 w-5 text-sky-400" weight="bold" />
            </div>
          </div>
          <div className="mt-5 space-y-4">
            {valuePoints.map((point, index) => (
              <div
                key={point}
                className="rounded-2xl border border-white/8 bg-black/40 px-4 py-4"
              >
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-gray-500">
                  Step 0{index + 1}
                </p>
                <p className="mt-2 text-sm font-medium leading-6 text-gray-200">
                  {point}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
