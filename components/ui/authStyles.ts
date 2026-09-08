// 로그인·가입 폼 공통 스타일 — 다크 전용(UI_GUIDELINES §2·§6·§10).
// 조건부 `dark:` 색은 쓰지 않는다: 기기 색상 설정이 라이트인 사용자에게 `bg-white` 폴백이
// 그대로 나가 흰 배경에 흰 글자가 되던 결함(2026-09-08).
export const AUTH_INPUT_CLASS =
  "w-full rounded-xl border border-white/[0.1] bg-white/[0.04] px-4 py-3 text-sm font-bold text-white " +
  "placeholder:text-[var(--text-placeholder)] transition-colors focus:border-[var(--chat-accent)] focus-visible:outline-none";

export const AUTH_LABEL_CLASS = "mb-1.5 block text-xs font-bold text-[var(--text-label)]";

export const AUTH_PRIMARY_BUTTON_CLASS =
  "w-full rounded-xl bg-[var(--chat-accent)] py-3 text-sm font-black text-[var(--chat-accent-ink)] " +
  "transition-colors hover:bg-[#f5c04a] disabled:cursor-not-allowed disabled:opacity-50";

export const AUTH_GOOGLE_BUTTON_CLASS =
  "flex w-full items-center justify-center gap-2 rounded-xl border border-white/[0.08] bg-white px-4 py-3 " +
  "text-sm font-black text-black transition-colors hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60";

export const AUTH_LINK_CLASS = "font-black text-[var(--chat-accent)] hover:underline";

export const AUTH_ERROR_CLASS =
  "mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm font-bold text-red-400";

export const AUTH_NOTICE_CLASS =
  "mb-4 rounded-xl border border-white/[0.1] bg-white/[0.04] p-3 text-sm font-bold text-gray-200";
