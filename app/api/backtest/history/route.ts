import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
} from "@/lib/get-user";

function formatItem(item: any) {
  return {
    id: item.id,
    timestamp: item.createdAt.getTime(),
    strategyName: item.strategyName,
    universe: item.universe,
    conditions: JSON.parse(item.conditions),
    metrics: JSON.parse(item.metrics),
    result: item.result ? JSON.parse(item.result) : undefined,
  };
}

// 저장 목록: 로그인 사용자가 자신의 목록에 담은 기록만 반환한다(UserBacktestHistory 조인).
// 비인증/테스트(userId=null)는 레거시 전역(isVisible) 조회로 폴백한다.
export async function GET() {
  try {
    const { userId } = await getOwnershipContext();

    if (userId == null) {
      const history = await prisma.backtestHistory.findMany({
        where: { isVisible: true },
        orderBy: { createdAt: "desc" },
        take: 50,
      });
      return NextResponse.json(history.map(formatItem));
    }

    const links = await prisma.userBacktestHistory.findMany({
      where: { userId },
      orderBy: { savedAt: "desc" },
      take: 50,
      include: { BacktestHistory: true },
    });
    return NextResponse.json(
      links.map((link) => formatItem(link.BacktestHistory))
    );
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch backtest history:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

// 저장 버튼 클릭 시 호출
// cacheKey 가 있으면 기존 숨김 레코드를 isVisible=true 로 업데이트,
// 없거나 레코드가 없으면 새로 생성한 뒤,
// 로그인 사용자의 "내 목록"(UserBacktestHistory)에 연결한다.
// isAutoSave=true 인 경우: 기존 레코드에 이미 이름이 있으면 이름을 덮어쓰지 않음
export async function POST(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const body = await request.json();
    const { strategyName, prompt, universe, conditions, metrics, result, cacheKey, isAutoSave } = body;

    let saved: any = null;

    if (cacheKey) {
      const existing = await prisma.backtestHistory.findUnique({ where: { cacheKey } });
      if (existing) {
        const nextResult =
          isAutoSave
            ? existing.result ?? (result ? JSON.stringify(result) : existing.result)
            : (result ? JSON.stringify(result) : existing.result);

        saved = await prisma.backtestHistory.update({
          where: { cacheKey },
          data: {
            // 자동 저장 시 기존에 사용자가 지정한 이름이 있으면 유지
            strategyName: isAutoSave && existing.strategyName ? existing.strategyName : strategyName,
            // 프롬프트 스냅샷은 비어 있을 때만 보완(기존 값 보존)
            prompt: existing.prompt ?? (prompt || null),
            universe,
            conditions: JSON.stringify(conditions),
            metrics: JSON.stringify(metrics),
            // 자동 저장이어도 기존 상세 결과가 비어 있으면 전달된 result로 보완한다.
            result: nextResult,
            isVisible: true,
          },
        });
      }
    }

    // cacheKey 없거나 레코드 없을 때 새 레코드 생성
    if (!saved) {
      saved = await prisma.backtestHistory.create({
        data: {
          strategyName,
          prompt: prompt || null,
          universe,
          conditions: JSON.stringify(conditions),
          metrics: JSON.stringify(metrics),
          result: result ? JSON.stringify(result) : null,
          cacheKey: cacheKey ?? null,
          isVisible: true,
        },
      });
    }

    // 로그인 사용자의 "내 목록"에 연결(이미 있으면 유지)
    if (userId != null) {
      await prisma.userBacktestHistory.upsert({
        where: { userId_backtestHistoryId: { userId, backtestHistoryId: saved.id } },
        create: { userId, backtestHistoryId: saved.id },
        update: {},
      });
    }

    return NextResponse.json(formatItem(saved));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to save backtest history:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}

// 목록에서 제거: 사용자의 연결(UserBacktestHistory)만 끊고 공유 결과는 DB에 보존한다.
// 비인증/테스트(userId=null)는 레거시 동작(isVisible=false 토글)로 폴백한다.
export async function DELETE(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    const { searchParams } = new URL(request.url);
    const id = searchParams.get("id");

    if (userId == null) {
      if (id) {
        await prisma.backtestHistory.update({ where: { id }, data: { isVisible: false } });
      } else {
        await prisma.backtestHistory.updateMany({ data: { isVisible: false } });
      }
      return NextResponse.json({ success: true });
    }

    if (id) {
      await prisma.userBacktestHistory.deleteMany({
        where: { userId, backtestHistoryId: id },
      });
    } else {
      await prisma.userBacktestHistory.deleteMany({ where: { userId } });
    }
    return NextResponse.json({ success: true });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to delete backtest history:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
