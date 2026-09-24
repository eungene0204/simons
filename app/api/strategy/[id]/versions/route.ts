import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";
import { listStrategyVersions, lineageKeyFor } from "@/lib/server/strategyVersions";

/** 이 전략(같은 이름 계보)의 버전 이력. */
export async function GET(_req: Request, { params }: { params: { id: string } }) {
  try {
    const { userId } = await getOwnershipContext();
    const strategy = await prisma.strategy.findFirst({
      where: withOwnership({ id: params.id }, userId),
      select: { id: true, name: true },
    });
    if (!strategy) {
      return NextResponse.json({ error: "Strategy not found" }, { status: 404 });
    }
    const versions = await listStrategyVersions(userId, strategy.name, strategy.id);
    return NextResponse.json({ strategyId: strategy.id, name: strategy.name, versions });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to list strategy versions:", error);
    return NextResponse.json({ error: "Failed to list strategy versions" }, { status: 500 });
  }
}

/**
 * 되돌리기 — 지정한 버전의 설정을 **현재 전략으로 다시 저장**한다.
 * 과거 행을 고치지 않고 그 설정으로 새 저장을 만든다(되돌린 것도 하나의 버전으로 남는다).
 */
export async function POST(req: Request, { params }: { params: { id: string } }) {
  try {
    const { userId } = await getOwnershipContext();
    const body = (await req.json()) as { versionId?: string };
    if (!body?.versionId) {
      return NextResponse.json({ error: "versionId is required" }, { status: 400 });
    }
    const strategy = await prisma.strategy.findFirst({
      where: withOwnership({ id: params.id }, userId),
      select: { id: true, name: true },
    });
    if (!strategy) {
      return NextResponse.json({ error: "Strategy not found" }, { status: 404 });
    }
    const version = await prisma.strategyVersion.findFirst({
      where: { id: body.versionId, lineageKey: lineageKeyFor(userId, strategy.name) },
      select: { settings: true, version: true },
    });
    if (!version) {
      return NextResponse.json({ error: "Version not found" }, { status: 404 });
    }
    // 설정 본문만 돌려준다 — 저장은 기존 저장 경로(POST /api/strategy)가 한 번만 담당한다
    // (플랜 한도·전략 유형 추론·버전 기록이 그 경로에 있고, 사본을 만들면 규칙이 갈린다).
    let settings: unknown = null;
    try {
      settings = JSON.parse(version.settings);
    } catch {
      return NextResponse.json({ error: "Stored version is unreadable" }, { status: 500 });
    }
    return NextResponse.json({ settings, version: version.version });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to restore strategy version:", error);
    return NextResponse.json({ error: "Failed to restore strategy version" }, { status: 500 });
  }
}
