import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
} from "@/lib/get-user";

export const dynamic = "force-dynamic";

// 저장된 검증 결과 단건 조회(전체 result JSON 포함) — 불러오기 시 사용.
export async function GET(_request: Request, { params }: { params: { id: string } }) {
  try {
    const { userId } = await getOwnershipContext();
    const item = await prisma.savedValidation.findFirst({
      where: { id: params.id, userId: userId ?? null },
    });
    if (!item) {
      return NextResponse.json({ error: "Not Found" }, { status: 404 });
    }
    return NextResponse.json({
      id: item.id,
      modelType: item.modelType,
      strategyName: item.strategyName,
      prompt: item.prompt ?? undefined,
      cacheKey: item.cacheKey ?? undefined,
      settings: item.settings ? JSON.parse(item.settings) : undefined,
      result: JSON.parse(item.result),
      summary: item.summary ? JSON.parse(item.summary) : undefined,
      createdAt: item.createdAt.getTime(),
    });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch saved validation:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
