import { describe, expect, it, vi } from "vitest";
import {
  buildStrategyReportText,
  extractSseResult,
  processMonthlyStrategyReports,
  toReportMetrics,
} from "@/lib/server/strategyReport";

vi.mock("@/lib/server/backend", () => ({ fetchBackend: vi.fn() }));
vi.mock("@/lib/server/mailer", () => ({ sendStrategyReportEmail: vi.fn(), isMailerConfigured: () => false }));

const NOW = new Date("2026-12-01T00:00:00Z"); // KST 2026-12-01 09:00
const METRICS = { startDate: "2021-12-01", endDate: "2026-11-30", totalReturn: 41.2, cagr: 7.15, maxDrawdown: -18.3, trades: 53 };

function makePrisma(opts: { users?: any[]; strategies?: any[]; claimCount?: number } = {}) {
  return {
    user: {
      findMany: vi.fn().mockResolvedValue(
        opts.users ?? [{ id: 1, email: "a@example.com", name: "홍길동", strategyReportLastSentKey: "2026-11" }]
      ),
      updateMany: vi.fn().mockResolvedValue({ count: opts.claimCount ?? 1 }),
    },
    strategy: {
      findMany: vi.fn().mockResolvedValue(opts.strategies ?? [{ name: "저PER", settings: "{}" }]),
    },
  } as any;
}

describe("strategyReport — 엔진 결과 추출", () => {
  it("SSE 본문에서 result 이벤트를 꺼낸다", () => {
    const body =
      'data: {"type":"status","message":"x"}\n\n' +
      'data: {"type":"result","data":{"cagr":7.1,"dates":["2021-01-04","2025-12-30"]}}\n\n' +
      "data: [DONE]\n\n";
    expect(extractSseResult(body)).toEqual({ cagr: 7.1, dates: ["2021-01-04", "2025-12-30"] });
  });

  it("error 이벤트면 null", () => {
    expect(extractSseResult('data: {"type":"error","message":"x"}\n\n')).toBeNull();
  });

  it("수치는 엔진 단위(%) 그대로, 기간은 첫·마지막 날짜", () => {
    expect(toReportMetrics({ totalReturn: 10, cagr: 2, maxDrawdown: -5, trades: 3, dates: ["a", "b", "c"] })).toEqual({
      startDate: "a", endDate: "c", totalReturn: 10, cagr: 2, maxDrawdown: -5, trades: 3,
    });
  });
});

describe("strategyReport — 메일 본문", () => {
  const text = buildStrategyReportText("홍길동", "2026-12", [
    { name: "저PER", metrics: METRICS },
    { name: "모멘텀", metrics: null },
  ], "https://www.nullstock.im");

  it("사실 수치와 면책·수신 해제 안내를 담는다", () => {
    expect(text).toContain("누적 수익률 +41.20% · CAGR +7.15% · 최대 낙폭 -18.30%");
    expect(text).toContain("거래 53회");
    expect(text).toContain("이번 달은 계산하지 못했습니다");
    expect(text).toContain("미래 수익을 보장하지 않습니다");
    expect(text).toContain("수신을 끄려면");
  });

  // 규제 안전 원칙 — 우열·추천·전망·행동 제안 표현이 섞이면 안 된다.
  it("추천·우열·전망 표현을 쓰지 않는다", () => {
    for (const banned of ["추천", "유망", "더 우수", "좋은 전략", "권장", "매수하", "매도하", "기대됩니다", "가장 좋"]) {
      expect(text).not.toContain(banned);
    }
  });
});

describe("strategyReport — 월간 발송", () => {
  it("선점 후 저장 전략을 다시 계산해 한 번 보낸다", async () => {
    const prisma = makePrisma();
    const run = vi.fn().mockResolvedValue(METRICS);
    const send = vi.fn().mockResolvedValue(undefined);
    const summary = await processMonthlyStrategyReports(prisma, NOW, run, send, () => true);
    expect(summary).toEqual({ sent: 1, skipped: 0, failed: 0 });
    expect(prisma.user.updateMany).toHaveBeenCalledWith({
      where: { id: 1, strategyReportLastSentKey: "2026-11" },
      data: { strategyReportLastSentKey: "2026-12" },
    });
    expect(send).toHaveBeenCalledWith("a@example.com", "[널스탁] 2026-12 저장 전략 재계산 결과", expect.any(String));
    // 수신 동의·유료·활성·이번 달 미발송만 조회한다
    expect(prisma.user.findMany.mock.calls[0][0].where).toMatchObject({
      strategyReportOptIn: true,
      planTier: { in: ["PRO", "PREMIUM"] },
      status: "ACTIVE",
    });
  });

  it("다른 프로세스가 먼저 선점했으면 보내지 않는다", async () => {
    const prisma = makePrisma({ claimCount: 0 });
    const send = vi.fn();
    const summary = await processMonthlyStrategyReports(prisma, NOW, vi.fn(), send, () => true);
    expect(summary.skipped).toBe(1);
    expect(send).not.toHaveBeenCalled();
  });

  it("발송이 실패하면 선점을 되돌려 다음 날 재시도한다", async () => {
    const prisma = makePrisma();
    const send = vi.fn().mockRejectedValue(new Error("smtp"));
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const summary = await processMonthlyStrategyReports(prisma, NOW, vi.fn().mockResolvedValue(METRICS), send, () => true);
    spy.mockRestore();
    expect(summary.failed).toBe(1);
    expect(prisma.user.updateMany).toHaveBeenLastCalledWith({
      where: { id: 1, strategyReportLastSentKey: "2026-12" },
      data: { strategyReportLastSentKey: "2026-11" },
    });
  });

  it("모든 전략 재계산이 실패하면 빈 리포트를 보내지 않는다", async () => {
    const prisma = makePrisma();
    const send = vi.fn();
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const summary = await processMonthlyStrategyReports(prisma, NOW, vi.fn().mockResolvedValue(null), send, () => true);
    spy.mockRestore();
    expect(summary.failed).toBe(1);
    expect(send).not.toHaveBeenCalled();
  });

  it("게스트 계정은 건너뛴다", async () => {
    const prisma = makePrisma({ users: [{ id: 2, email: "g1@guest.nullstock.im", name: "g", strategyReportLastSentKey: null }] });
    const send = vi.fn();
    const summary = await processMonthlyStrategyReports(prisma, NOW, vi.fn(), send, () => true);
    expect(summary.skipped).toBe(1);
    expect(prisma.user.updateMany).not.toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
  });

  it("메일 발송 계정이 없으면 백테스트도 발송도 하지 않는다", async () => {
    const prisma = makePrisma();
    const run = vi.fn();
    const summary = await processMonthlyStrategyReports(prisma, NOW, run, vi.fn(), () => false);
    expect(summary).toEqual({ sent: 0, skipped: 0, failed: 0 });
    expect(prisma.user.findMany).not.toHaveBeenCalled();
    expect(run).not.toHaveBeenCalled();
  });
});
