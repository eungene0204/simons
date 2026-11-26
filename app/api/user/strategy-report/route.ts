import { NextResponse } from "next/server";
import { getOwnershipContext, isUnauthorizedAccessError } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { isGuestEmail } from "@/lib/server/guestAccounts";
import { isMailerConfigured } from "@/lib/server/mailer";
import { REPORT_PLANS } from "@/lib/server/strategyReport";

// 저장 전략 월간 재검증 리포트 수신 설정(2026-11-26).
// 유료 플랜(PRO·PREMIUM)만 켤 수 있다. 게스트 계정은 실제 메일함이 없어 켤 수 없다.

const PAID = new Set<string>(REPORT_PLANS);

async function loadUser(userId: number) {
  return prisma.user.findUnique({
    where: { id: userId },
    select: { email: true, planTier: true, strategyReportOptIn: true },
  });
}

function eligible(user: { email: string; planTier: string }): boolean {
  // 메일 발송 계정(SMTP)이 없으면 받을 수 없으므로 켤 수 없다(토글도 숨는다).
  return isMailerConfigured() && PAID.has(user.planTier) && !isGuestEmail(user.email);
}

export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    if (userId == null) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
    const user = await loadUser(userId);
    if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
    return NextResponse.json({ optIn: user.strategyReportOptIn, eligible: eligible(user) });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
    }
    console.error("Failed to read strategy report setting:", error);
    return NextResponse.json({ error: "설정을 불러오지 못했습니다." }, { status: 500 });
  }
}

export async function PUT(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    if (userId == null) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
    const body = await request.json().catch(() => null);
    if (typeof body?.optIn !== "boolean") {
      return NextResponse.json({ error: "설정 값이 올바르지 않습니다." }, { status: 400 });
    }
    const user = await loadUser(userId);
    if (!user) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
    // 끄기는 플랜과 무관하게 언제나 허용한다(플랜을 내린 뒤에도 해제할 수 있어야 한다).
    if (body.optIn && !eligible(user)) {
      return NextResponse.json(
        { error: "저장 전략 월간 리포트는 Pro·Premium 플랜에서 이용할 수 있습니다." },
        { status: 403 }
      );
    }
    await prisma.user.update({ where: { id: userId }, data: { strategyReportOptIn: body.optIn } });
    return NextResponse.json({ optIn: body.optIn, eligible: eligible(user) });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
    }
    console.error("Failed to update strategy report setting:", error);
    return NextResponse.json({ error: "설정을 저장하지 못했습니다." }, { status: 500 });
  }
}
