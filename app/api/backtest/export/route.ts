import { NextResponse } from "next/server";
import { getOwnershipContext, isUnauthorizedAccessError } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getUserPlan } from "@/lib/server/planLimits";
import {
  buildExportFile,
  isExportFormat,
  type BacktestExportPayload,
} from "@/lib/backtest-export";

// 결과 다운로드는 Pro / Premium 전용 기능이다. 서버에서도 반드시 플랜을 검증해
// 무료·비로그인·차단 사용자가 직접 API를 호출해도 파일이 생성되지 않게 한다.
const DOWNLOAD_ALLOWED_PLANS = new Set(["PRO", "PREMIUM"]);

function isValidPayload(value: unknown): value is BacktestExportPayload {
  if (!value || typeof value !== "object") return false;
  const p = value as Record<string, unknown>;
  return (
    !!p.metadata &&
    typeof p.metadata === "object" &&
    Array.isArray(p.stockAnalysis) &&
    Array.isArray(p.tradeHistory)
  );
}

export async function POST(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    if (userId == null) {
      return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
    }

    const plan = await getUserPlan(prisma, userId);
    if (!DOWNLOAD_ALLOWED_PLANS.has(plan.planId)) {
      return NextResponse.json(
        { error: "결과 다운로드는 Pro 이상 플랜에서 사용할 수 있습니다." },
        { status: 403 }
      );
    }

    const body = await request.json().catch(() => null);
    const format = body?.format;
    if (!isExportFormat(format)) {
      return NextResponse.json({ error: "지원하지 않는 형식입니다." }, { status: 400 });
    }
    if (!isValidPayload(body?.payload)) {
      return NextResponse.json({ error: "내보낼 백테스트 데이터가 없습니다." }, { status: 400 });
    }

    const file = buildExportFile(body.payload, format);

    return new NextResponse(file.content, {
      status: 200,
      headers: {
        "Content-Type": file.mimeType,
        "Content-Disposition": `attachment; filename="${encodeURIComponent(file.fileName)}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
    }
    console.error("Failed to export backtest result:", error);
    return NextResponse.json({ error: "다운로드 파일 생성에 실패했습니다." }, { status: 500 });
  }
}
