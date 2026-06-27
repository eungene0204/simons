import { NextResponse } from "next/server";
import { getOwnershipContext, isUnauthorizedAccessError } from "@/lib/get-user";
import { startAccountStrategy } from "@/lib/server/strategy-start";

// POST: 전략 자동 실행 시작
// 핵심 로직은 lib/server/strategy-start 에 있고, 이 라우트는 브라우저 호출용 얇은 래퍼다.
export async function POST(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const result = await startAccountStrategy({ accountId: params.id, userId });

    if (!result.ok) {
      return NextResponse.json({ error: result.error }, { status: result.status });
    }

    const { ok, state, ...rest } = result;
    return NextResponse.json({ ...state, ...rest });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Strategy start error:", error);
    return NextResponse.json(
      { error: "전략 자동 실행 시작에 실패했습니다." },
      { status: 500 }
    );
  }
}
