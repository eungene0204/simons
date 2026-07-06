import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
} from "@/lib/get-user";

export const dynamic = "force-dynamic";

// 목록 표시용 경량 행 (전체 result JSON 제외 — 불러오기 시 /[id]로 조회)
function formatListItem(item: {
  id: string;
  modelType: string;
  strategyName: string;
  prompt: string | null;
  cacheKey: string | null;
  settings: string;
  summary: string | null;
  createdAt: Date;
}) {
  return {
    id: item.id,
    modelType: item.modelType,
    strategyName: item.strategyName,
    prompt: item.prompt ?? undefined,
    cacheKey: item.cacheKey ?? undefined,
    settings: item.settings ? JSON.parse(item.settings) : undefined,
    summary: item.summary ? JSON.parse(item.summary) : undefined,
    createdAt: item.createdAt.getTime(),
  };
}

// 저장된 검증 결과 목록 — 로그인 사용자 본인 것만. 비인증(userId=null)은 userId IS NULL 행으로 폴백.
export async function GET(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const { searchParams } = new URL(request.url);
    const modelType = searchParams.get("modelType") ?? undefined;

    const items = await prisma.savedValidation.findMany({
      where: {
        userId: userId ?? null,
        ...(modelType ? { modelType } : {}),
      },
      orderBy: { createdAt: "desc" },
      take: 100,
      select: {
        id: true,
        modelType: true,
        strategyName: true,
        prompt: true,
        cacheKey: true,
        settings: true,
        summary: true,
        createdAt: true,
      },
    });
    return NextResponse.json(items.map(formatListItem));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to list saved validations:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

// 검증 결과 저장 — 워크포워드/몬테카를로 결과 스냅샷을 그대로 보관한다.
export async function POST(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const body = await request.json();
    const { modelType, strategyName, prompt, cacheKey, settings, result, summary } = body ?? {};

    if (modelType !== "walkForward" && modelType !== "monteCarlo") {
      return NextResponse.json({ error: "invalid modelType" }, { status: 400 });
    }
    if (result == null) {
      return NextResponse.json({ error: "missing result" }, { status: 400 });
    }

    const saved = await prisma.savedValidation.create({
      data: {
        userId: userId ?? null,
        modelType,
        strategyName: (strategyName || "이름 없는 전략").toString().slice(0, 200),
        prompt: prompt ? String(prompt) : null,
        cacheKey: cacheKey ? String(cacheKey) : null,
        settings: JSON.stringify(settings ?? {}),
        result: JSON.stringify(result),
        summary: summary != null ? JSON.stringify(summary) : null,
      },
    });
    return NextResponse.json({ id: saved.id, createdAt: saved.createdAt.getTime() });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to save validation:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

// 저장 목록에서 제거 — 본인 소유 행만 삭제한다.
export async function DELETE(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const { searchParams } = new URL(request.url);
    const id = searchParams.get("id");
    if (!id) {
      return NextResponse.json({ error: "missing id" }, { status: 400 });
    }
    await prisma.savedValidation.deleteMany({ where: { id, userId: userId ?? null } });
    return NextResponse.json({ success: true });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to delete saved validation:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
