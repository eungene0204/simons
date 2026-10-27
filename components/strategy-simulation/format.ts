// 전략 시뮬레이션 화면 공용 표기 — 원화·부호 있는 %·방향 색.
export const won = (v: number) => `${v < 0 ? "-" : ""}₩${Math.abs(Math.round(v)).toLocaleString("ko-KR")}`;
export const pct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
export const signTone = (v: number) =>
  v > 0 ? "text-[var(--main-red)]" : v < 0 ? "text-[var(--main-blue)]" : "text-white";
