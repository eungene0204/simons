"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { t } from "@/lib/i18n";
import { pct } from "./format";
import type { SimulationCurve } from "./SimulationMiniChart";

// 상세 누적 수익률 그래프 — 그래프는 하나이고, 방문자가 값을 바꾸면 같은 그래프에 수정본 선이 겹쳐진다.
export function SimulationReturnChart({ curve, modified }: { curve: SimulationCurve; modified?: SimulationCurve }) {
  // 수정본은 같은 창을 쓰므로 날짜로 맞춰 붙인다(없는 날은 비운다).
  const modifiedByDate = new Map(modified?.dates.map((d, i) => [d, modified.returnPct[i]]));
  const data = curve.dates.map((date, i) => ({ date, value: curve.returnPct[i], modified: modifiedByDate.get(date) }));
  return (
    <div className="h-64 w-full" role="img" aria-label={t("누적 수익률 그래프")}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#2a2926" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#a8a49a", fontSize: 11 }} minTickGap={48} tickFormatter={(d: string) => d.slice(0, 7)} />
          <YAxis tick={{ fill: "#a8a49a", fontSize: 11 }} width={48} tickFormatter={(v: number) => `${v}%`} />
          <ReferenceLine y={0} stroke="#8a867d" strokeDasharray="3 3" />
          <Tooltip
            contentStyle={{ background: "#1e1d1a", border: "1px solid rgba(244,241,234,0.12)", fontSize: 12 }}
            labelStyle={{ color: "#a8a49a" }}
            formatter={(v: number, name: string) => [pct(v), name === "modified" ? t("수정") : t("원본")]}
          />
          <Line type="monotone" dataKey="value" stroke="#f4f1ea" strokeWidth={1.8} dot={false} isAnimationActive={false} />
          {modified && <Line type="monotone" dataKey="modified" stroke="#e0805c" strokeWidth={1.8} dot={false} connectNulls isAnimationActive={false} />}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
