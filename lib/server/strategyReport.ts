// 저장 전략 월간 재검증 리포트(2026-11-26) — 유료 플랜 사용자가 켜 두면, 매달 1일 저장한 전략을
// 최신 데이터로 다시 백테스트해 결과 수치를 메일로 보낸다.
//
// 규제 안전 원칙(CLAUDE.md): 사용자가 직접 만든 전략의 과거 시뮬레이션 수치만 전한다.
// 전략 간 우열·추천·전망·행동 제안 문구를 쓰지 않는다(정렬도 저장 순서이지 성과 순이 아니다).
//
// - 수신은 사용자가 설정에서 켠 경우만(User.strategyReportOptIn, 기본 꺼짐).
// - 저장된 settings는 저장 당시의 실행 요청이다(save-with-backtest) — 그대로 엔진에 다시 보낸다.
//   기간이 '최근 N년' 같은 상대 기간이면 최신 데이터까지 반영되고, 날짜를 고정한 전략은 같은 창을 다시 계산한다.
// - 월 백테스트 한도를 쓰지 않는다(사용자가 실행한 백테스트가 아니다).
// - 스케줄러가 프로세스마다 돌 수 있어, 발송 전에 주기 키를 조건부로 선점해 같은 달 중복 발송을 막는다.

import type { PrismaClient } from "@prisma/client";
import { fetchBackend } from "@/lib/server/backend";
import { isMailerConfigured, sendStrategyReportEmail } from "@/lib/server/mailer";
import { currentUsageMonth } from "@/lib/server/planLimits";
import { siteUrl } from "@/lib/seo/site";
import { isGuestEmail } from "@/lib/server/guestAccounts";

/** 한 사용자당 리포트에 담는 저장 전략 수 상한 — 엔진 부하를 묶는다(최근 수정순). */
export const REPORT_MAX_STRATEGIES = 5;
export const REPORT_PLANS = ["PRO", "PREMIUM"] as const;
const BACKTEST_TIMEOUT_MS = 600_000;

export interface StrategyReportLine {
  name: string;
  /** 계산 실패면 null — 메일에는 '이번 달 계산 실패'로 적는다 */
  metrics: {
    startDate: string | null;
    endDate: string | null;
    totalReturn: number | null;
    cagr: number | null;
    maxDrawdown: number | null;
    trades: number | null;
  } | null;
}

export interface StrategyReportSummary {
  sent: number;
  skipped: number;
  failed: number;
}

/** 엔진 SSE 본문에서 result 이벤트의 data를 꺼낸다(없으면 null). 형식 추출만 한다. */
export function extractSseResult(body: string): any | null {
  let result: any = null;
  for (const block of body.split(/\r?\n\r?\n/)) {
    for (const line of block.split(/\r?\n/)) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        const event = JSON.parse(payload);
        if (event?.type === "result" && event.data) result = event.data;
        if (event?.type === "error") return null;
      } catch {
        // 깨진 이벤트 한 줄은 건너뛴다 — result가 없으면 실패로 처리된다.
      }
    }
  }
  return result;
}

function finiteOrNull(value: unknown): number | null {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** 엔진 결과 → 메일에 쓰는 수치(엔진 단위 그대로: 수익률·CAGR·MDD는 %). */
export function toReportMetrics(result: any): StrategyReportLine["metrics"] {
  if (!result || typeof result !== "object") return null;
  const dates: unknown[] = Array.isArray(result.dates) ? result.dates : [];
  return {
    startDate: typeof dates[0] === "string" ? (dates[0] as string) : null,
    endDate: typeof dates[dates.length - 1] === "string" ? (dates[dates.length - 1] as string) : null,
    totalReturn: finiteOrNull(result.totalReturn),
    cagr: finiteOrNull(result.cagr),
    maxDrawdown: finiteOrNull(result.maxDrawdown),
    trades: finiteOrNull(result.trades),
  };
}

async function runSavedStrategy(settings: string): Promise<StrategyReportLine["metrics"]> {
  let request: unknown;
  try {
    request = JSON.parse(settings);
  } catch {
    return null;
  }
  const res = await fetchBackend("/strategy/backtest-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    cache: "no-store",
    timeoutMs: BACKTEST_TIMEOUT_MS,
  });
  if (!res.ok) return null;
  return toReportMetrics(extractSseResult(await res.text()));
}

function pct(value: number | null): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

/** 메일 본문 — 사실 수치만. 우열·추천·전망 표현 금지(테스트가 금지어를 검사한다). */
export function buildStrategyReportText(
  userName: string,
  periodKey: string,
  lines: StrategyReportLine[],
  settingsUrl: string
): string {
  const body: string[] = [
    `${userName}님, ${periodKey} 저장 전략 재계산 결과입니다.`,
    "저장할 때의 설정 그대로 최신 데이터까지 다시 백테스트했습니다.",
    "",
  ];
  for (const line of lines) {
    body.push(`■ ${line.name}`);
    if (!line.metrics) {
      body.push("  이번 달은 계산하지 못했습니다. 전략연구소에서 직접 다시 실행해 주세요.");
    } else {
      const m = line.metrics;
      if (m.startDate && m.endDate) body.push(`  기간: ${m.startDate} ~ ${m.endDate}`);
      body.push(`  누적 수익률 ${pct(m.totalReturn)} · CAGR ${pct(m.cagr)} · 최대 낙폭 ${pct(m.maxDrawdown)}`);
      if (m.trades != null) body.push(`  거래 ${m.trades.toLocaleString("ko-KR")}회`);
    }
    body.push("");
  }
  body.push(
    "위 수치는 과거 데이터 기반 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다.",
    "이 리포트는 월 백테스트 횟수에서 차감되지 않습니다.",
    `수신을 끄려면 널스탁 설정 > 요금제의 '저장 전략 월간 리포트'를 해제해 주세요: ${settingsUrl}`
  );
  return body.join("\n");
}


/** 이번 달(KST) 리포트를 아직 받지 않은 수신 동의 유료 사용자에게 보낸다. */
export async function processMonthlyStrategyReports(
  prisma: PrismaClient,
  now: Date = new Date(),
  runStrategy: (settings: string) => Promise<StrategyReportLine["metrics"]> = runSavedStrategy,
  send: (to: string, subject: string, text: string) => Promise<void> = sendStrategyReportEmail,
  mailerReady: () => boolean = isMailerConfigured
): Promise<StrategyReportSummary> {
  const periodKey = currentUsageMonth(now);
  const summary: StrategyReportSummary = { sent: 0, skipped: 0, failed: 0 };
  // 메일 발송 계정(SMTP)이 없으면 아무것도 하지 않는다 — 백테스트를 돌린 뒤 발송만 실패해
  // 매일 엔진을 헛돌리는 일을 막는다. 설정 API도 이때는 토글을 켜지 못하게 한다.
  if (!mailerReady()) return summary;

  const recipients = await prisma.user.findMany({
    where: {
      strategyReportOptIn: true,
      planTier: { in: [...REPORT_PLANS] },
      status: "ACTIVE",
      OR: [{ strategyReportLastSentKey: null }, { strategyReportLastSentKey: { not: periodKey } }],
    },
    select: { id: true, email: true, name: true, strategyReportLastSentKey: true },
  });

  for (const user of recipients) {
    // 게스트 계정은 실제 메일함이 없다(@guest.nullstock.im) — 설정 API도 켜지 못하게 막는다.
    if (isGuestEmail(user.email)) {
      summary.skipped += 1;
      continue;
    }
    // 선점 — 다른 프로세스가 먼저 가져갔으면 count=0이다.
    const claim = await prisma.user.updateMany({
      where: { id: user.id, strategyReportLastSentKey: user.strategyReportLastSentKey },
      data: { strategyReportLastSentKey: periodKey },
    });
    if (claim.count === 0) {
      summary.skipped += 1;
      continue;
    }

    try {
      const strategies = await prisma.strategy.findMany({
        where: { userId: user.id, isSaved: true, deletedAt: null },
        orderBy: { updatedAt: "desc" },
        take: REPORT_MAX_STRATEGIES,
        select: { name: true, settings: true },
      });
      if (strategies.length === 0) {
        summary.skipped += 1;
        continue;
      }

      const lines: StrategyReportLine[] = [];
      for (const strategy of strategies) {
        let metrics: StrategyReportLine["metrics"] = null;
        try {
          metrics = await runStrategy(strategy.settings);
        } catch (error) {
          console.error(`[StrategyReport] 재계산 실패 userId=${user.id}:`, error);
        }
        lines.push({ name: strategy.name, metrics });
      }
      if (lines.every((l) => l.metrics == null)) {
        throw new Error("모든 저장 전략의 재계산이 실패했습니다");
      }

      await send(
        user.email,
        `[널스탁] ${periodKey} 저장 전략 재계산 결과`,
        buildStrategyReportText(user.name, periodKey, lines, siteUrl())
      );
      summary.sent += 1;
    } catch (error) {
      // 보내지 못했으면 선점을 되돌려 다음 실행(다음 날)에 다시 시도한다.
      await prisma.user
        .updateMany({
          where: { id: user.id, strategyReportLastSentKey: periodKey },
          data: { strategyReportLastSentKey: user.strategyReportLastSentKey },
        })
        .catch(() => {});
      summary.failed += 1;
      console.error(`[StrategyReport] 발송 실패 userId=${user.id}:`, error);
    }
  }

  return summary;
}
