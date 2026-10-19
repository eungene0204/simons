"use client";

import { ChartLineUp, ChatCircleText, DiceFive, Flask, Funnel, GitBranch, ShieldCheck } from "phosphor-react";

// phosphor-react는 내부에서 createContext를 써서 서버 컴포넌트가 직접 import 하면 500이 난다
// (2026-10-19 실측). 소개 페이지(서버 컴포넌트)는 아이콘 이름만 넘기고 그리기는 여기서 한다.
const ICONS = { ChartLineUp, ChatCircleText, DiceFive, Flask, Funnel, GitBranch, ShieldCheck } as const;

export type LandingIconName = keyof typeof ICONS;

export function LandingIcon({ name, size = 24, className }: { name: LandingIconName; size?: number; className?: string }) {
  const Icon = ICONS[name];
  return <Icon size={size} weight="regular" className={className} aria-hidden="true" />;
}
